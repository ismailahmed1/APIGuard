import argparse
import re
import sys
from pathlib import Path

import httpx

from apiguard import __version__
from apiguard.config import ConfigError, load_config
from apiguard.openapi import SpecError, get_response, load_spec
from apiguard.operations import extract_operations

MEDIA_LABELS = {
    "application/json": "json",
    "application/x-www-form-urlencoded": "form",
    "multipart/form-data": "multipart",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and run reusable API tests.")
    parser.add_argument("--version", action="version", version=__version__)

    commands = parser.add_subparsers(dest="command", required=True)

    check_parser = commands.add_parser(
        "check",
        help="Check configuration, connectivity and the OpenAPI specification.",
    )
    check_parser.add_argument("app", help="Application name, such as nexstock.")

    spec_parser = commands.add_parser(
        "spec",
        help="Show a summary of the operations in the OpenAPI specification.",
    )
    spec_parser.add_argument("app", help="Application name, such as nexstock.")

    for command in ("generate", "run", "report"):
        command_parser = commands.add_parser(
            command,
            help="Not implemented yet.",
        )
        command_parser.add_argument("app")

    args = parser.parse_args(argv)

    if args.command not in ("check", "spec"):
        print(f"Error: '{args.command}' is not implemented yet.", file=sys.stderr)
        return 2

    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.app):
        print("Error: invalid application name.", file=sys.stderr)
        return 2

    config_path = Path("configs") / f"{args.app}.yaml"

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    location = config["spec_location"]
    timeout = config["timeouts"]["request_seconds"]

    try:
        spec = load_spec(location, timeout)
        # A remote spec already proves connectivity; local files do not.
        if args.command == "check" and "://" not in location:
            get_response(config["base_url"], timeout)
        operations = extract_operations(spec.document) if args.command == "spec" else None
    except SpecError as exc:
        print(f"Specification error: {exc}", file=sys.stderr)
        return 2
    except httpx.TimeoutException:
        print("Connection error: the request timed out.", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(
            f"Connection error: server returned HTTP {exc.response.status_code}.",
            file=sys.stderr,
        )
        return 1
    except httpx.RequestError:
        print(
            "Connection error: could not reach the application. "
            "Check that it is running and the configured address is correct.",
            file=sys.stderr,
        )
        return 1

    if args.command == "spec":
        print(format_summary(config["name"], spec.document.get("openapi"), operations))
        return 0

    print(f"OK: {config['name']} is reachable and its OpenAPI specification is valid.")
    return 0


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
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]) - 1)]
    lines = [
        f"{name}: {len(operations)} operations, {protected} require authentication"
        + f" (OpenAPI {version})",
        "",
    ]
    for row in rows:
        cells = [cell.ljust(width) for cell, width in zip(row, widths)]
        lines.append("  ".join([*cells, row[-1]]))
    return "\n".join(lines)


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


if __name__ == "__main__":
    raise SystemExit(main())
