import argparse
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

from apiguard import __version__
from apiguard.ai import AIClient, AIError
from apiguard.config import ConfigError, load_config
from apiguard.generator import generate_suite
from apiguard.openapi import SpecError, get_response, load_spec
from apiguard.operations import extract_operations
from apiguard.reporting import format_suite, table

MEDIA_LABELS = {
    "application/json": "json",
    "application/x-www-form-urlencoded": "form",
    "multipart/form-data": "multipart",
}
SUITES_DIR = "suites"
DEFAULT_MODEL = "claude-opus-5-5"


class Failure(Exception):
    """Stop a command with a message and an exit code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and run reusable API tests.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    def command(name, help_text):
        sub = commands.add_parser(name, help=help_text)
        sub.add_argument("app", help="Application name, such as nexstock.")
        return sub

    command("check", "Check configuration, connectivity and the OpenAPI specification.")
    command("spec", "Show a summary of the operations in the OpenAPI specification.")
    generate = command("generate", "Generate and save a test suite with the AI model.")
    generate.add_argument("--tag", action="append", default=[], help="Only this operation tag.")
    for name in ("run", "report"):
        command(name, "Not implemented yet.")
    args = parser.parse_args(argv)
    # Credentials and the AI key come from the environment or an untracked .env file.
    load_dotenv(Path(".env"), override=False)
    try:
        return COMMANDS[args.command](args)
    except Failure as exc:
        print(exc, file=sys.stderr)
        return exc.code


def load_app(name):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise Failure("Error: invalid application name.", 2)
    try:
        return load_config(Path("configs") / f"{name}.yaml")
    except ConfigError as exc:
        raise Failure(f"Configuration error: {exc}", 2) from exc


def fetch_spec(config, check_base_url=False):
    location = config["spec_location"]
    timeout = config["timeouts"]["request_seconds"]
    try:
        spec = load_spec(location, timeout)
        # A remote spec already proves connectivity; local files do not.
        if check_base_url and "://" not in location:
            get_response(config["base_url"], timeout)
        return spec, extract_operations(spec.document)
    except SpecError as exc:
        raise Failure(f"Specification error: {exc}", 2) from exc
    except httpx.TimeoutException as exc:
        raise Failure("Connection error: the request timed out.", 1) from exc
    except httpx.HTTPStatusError as exc:
        raise Failure(
            f"Connection error: server returned HTTP {exc.response.status_code}.", 1
        ) from exc
    except httpx.RequestError as exc:
        raise Failure(
            "Connection error: could not reach the application. "
            "Check that it is running and the configured address is correct.",
            1,
        ) from exc


def cmd_check(args):
    config = load_app(args.app)
    fetch_spec(config, check_base_url=True)
    print(f"OK: {config['name']} is reachable and its OpenAPI specification is valid.")
    return 0


def cmd_spec(args):
    config = load_app(args.app)
    spec, operations = fetch_spec(config)
    print(format_summary(config["name"], spec.document.get("openapi"), operations))
    return 0


def cmd_generate(args):
    config = load_app(args.app)
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise Failure("Configuration error: ANTHROPIC_API_KEY is not set.", 2)
    settings = config.get("generation", {})
    context = ""
    if settings.get("context_file"):
        try:
            context = Path(settings["context_file"]).read_text(encoding="utf-8")
        except OSError as exc:
            raise Failure(
                f"Configuration error: cannot read {settings['context_file']}.", 2
            ) from exc
    spec, operations = fetch_spec(config)
    roles = list(config["auth"].get("roles", {}))
    ai = AIClient(
        settings.get("model", DEFAULT_MODEL),
        settings.get("limits", {}),
        effort=settings.get("effort", "medium"),
    )
    print(f"Generating tests with {ai.model} for tags: {', '.join(args.tag) or 'all'} ...")
    try:
        directory, metadata = generate_suite(
            config["name"], spec, operations, args.tag, ai, context, roles, SUITES_DIR
        )
    except AIError as exc:
        raise Failure(f"AI error: {exc}.", 1) from exc
    excluded = json.loads((directory / "excluded.json").read_text(encoding="utf-8"))
    print(format_suite(metadata, excluded))
    print(f"\nSaved to {directory}")
    return 0 if metadata["counts"]["valid"] else 1


def format_summary(name, version, operations):
    """Format operations as a plain-text table; a trailing * marks a required input."""
    protected = sum(operation.requires_auth for operation in operations)
    rows = [("METHOD", "PATH", "AUTH", "PARAMETERS", "BODY", "RESPONSES")]
    for operation in operations:
        rows.append(
            (
                operation.method,
                operation.path,
                _auth_label(operation),
                ", ".join(
                    f"{p.location}:{p.name}{'*' if p.required else ''}"
                    for p in operation.parameters
                )
                or "-",
                _body_label(operation.request_body),
                ", ".join(operation.responses) or "-",
            )
        )
    header = (
        f"{name}: {len(operations)} operations, {protected} require authentication"
        + f" (OpenAPI {version})"
    )
    return "\n".join([header, "", *table(rows)])


def _auth_label(operation):
    if not operation.security_schemes:
        return "none"
    schemes = "|".join(operation.security_schemes)
    return schemes if operation.requires_auth else f"optional:{schemes}"


def _body_label(body):
    if body is None:
        return "-"
    labels = []
    for media_type, schema in body.content.items():
        title = schema.get("title") if isinstance(schema, dict) else None
        kind = MEDIA_LABELS.get(media_type, media_type)
        labels.append(f"{title} ({kind})" if title else kind)
    return (", ".join(labels) or "empty") + ("*" if body.required else "")


def cmd_placeholder(args):
    raise Failure(f"Error: '{args.command}' is not implemented yet.", 2)


COMMANDS = {
    "check": cmd_check,
    "spec": cmd_spec,
    "generate": cmd_generate,
    "run": cmd_placeholder,
    "report": cmd_placeholder,
}


if __name__ == "__main__":
    raise SystemExit(main())
