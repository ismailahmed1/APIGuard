import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from apiguard import __version__
from apiguard.ai import AIClient, AIError
from apiguard.baseline import BaselineError, compare_baselines, run_baseline
from apiguard.config import ConfigError, load_config
from apiguard.generator import generate_suite
from apiguard.monitor import MonitorError, monitor_run
from apiguard.openapi import SpecError, get_response, load_spec
from apiguard.operations import extract_operations
from apiguard.reporting import compare_runs, format_run, format_suite, table
from apiguard.runner import RunError, get_token, load_suite, reset_app, run_suite

MEDIA_LABELS = {
    "application/json": "json",
    "application/x-www-form-urlencoded": "form",
    "multipart/form-data": "multipart",
}
SUITES_DIR = "suites"
RUNS_DIR = "runs"
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
    run = command("run", "Run a saved test suite without the AI model.")
    run.add_argument("--suite", help="Suite ID (default: the latest suite).")
    run.add_argument("--label", help="Label for this run, such as a seeded fault ID.")
    run.add_argument("--no-reset", action="store_true", help="Do not reset the test data.")
    report = command("report", "Show the report of a saved run.")
    report.add_argument("--run", help="Run ID (default: the latest run).")
    compare = command("compare", "Find tests that pass in a base run and fail in another run.")
    compare.add_argument("base", help="Base run ID or label, usually the original app.")
    compare.add_argument("other", help="Run ID or label to compare, usually a seeded fault.")
    compare.add_argument(
        "--schemathesis", action="store_true", help="Compare Schemathesis runs instead."
    )
    baseline = command("baseline", "Run the Schemathesis baseline on the same operations.")
    baseline.add_argument("--tag", action="append", default=[], help="Only this operation tag.")
    baseline.add_argument("--label", help="Label for this run, such as a seeded fault ID.")

    ui = command("ui", "Open a local web UI for generating, running and comparing suites.")
    ui.add_argument("--port", type=int, default=8765, help="Local port (default: 8765).")
    ui.add_argument("--no-browser", action="store_true", help="Do not open a browser.")

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


def cmd_run(args):
    config = load_app(args.app)
    try:
        suite_dir, metadata, tests = load_suite(SUITES_DIR, config["name"], args.suite)
        # The suite's own snapshot describes the operations that its tests were written for.
        snapshot = load_spec(str(suite_dir / "openapi.yaml"), config["timeouts"]["request_seconds"])
        operations = extract_operations(snapshot.document)
        directory, run, results = run_suite(
            config, metadata, tests, operations, RUNS_DIR, args.label, reset=not args.no_reset
        )
    except (RunError, SpecError) as exc:
        raise Failure(f"Run error: {exc}", 1) from exc
    print(format_run(run, results))
    if config.get("monitor"):
        since = datetime.fromisoformat(run["started_at"])
        try:
            record, _ = monitor_run(config, since, datetime.now(UTC), directory)
        except MonitorError as exc:
            print(f"\nSecurity monitor: {exc}", file=sys.stderr)
        else:
            rules = ", ".join(sorted({m["rule"] for m in record["matches"]})) or "none"
            print(f"\nSecurity monitor: {record['events']} log events, rules matched: {rules}")
    return 0 if run["outcomes"].get("passed", 0) == run["total"] else 1


def cmd_report(args):
    config = load_app(args.app)
    run, results = read_run(config["name"], args.run)
    print(format_run(run, results))
    return 0


def cmd_compare(args):
    config = load_app(args.app)
    if args.schemathesis or args.base.startswith("baseline-") or args.other.startswith("baseline-"):
        base, other = (
            read_baseline(config["name"], args.base),
            read_baseline(config["name"], args.other),
        )
        new = compare_baselines(base, other)
        name = other.get("label") or other["run_id"]
        print(f"Compared Schemathesis run {other['run_id']} ({name}) with {base['run_id']}:")
        if new:
            print(f"DETECTED: {len(new)} new failed checks.")
            print("\n".join("  " + line for line in table([("OPERATION", "CHECK"), *new])))
        else:
            print("NOT DETECTED: no new failed checks.")
        return 0
    base, base_results = read_run(config["name"], args.base)
    other, other_results = read_run(config["name"], args.other)
    text, _ = compare_runs(base, base_results, other, other_results)
    print(text)
    return 0


def cmd_baseline(args):
    config = load_app(args.app)
    try:
        # The same starting data as an APIGuard run.
        reset_app(config)
        token = get_token(config, config.get("baseline", {}).get("role", "admin"))
        directory, summary = run_baseline(config, args.tag, token, RUNS_DIR, args.label)
    except (RunError, BaselineError) as exc:
        raise Failure(f"Baseline error: {exc}", 1) from exc
    failing = {op: checks for op, checks in summary["failures"].items() if checks}
    label = f" [{summary['label']}]" if summary.get("label") else ""
    print(
        f"Schemathesis run {summary['run_id']}{label}: {summary['operations_tested']} operations, "
        f"{len(failing)} with failures, {summary['seconds']} s"
    )
    if failing:
        rows = [("OPERATION", "FAILED CHECKS")]
        rows += [(op, ", ".join(checks)) for op, checks in failing.items()]
        print("\n".join("  " + line for line in table(rows)))
    print(f"Saved to {directory}")
    return 0


def resolve_run(app_name, name, baseline=False):
    """Accept a run ID, or a label such as 'original' for the latest run with that label."""
    root = Path(RUNS_DIR) / app_name
    if (root / name).is_dir():
        return name
    summary = "summary.json" if baseline else "run.json"
    pattern = "baseline-*" if baseline else "[0-9]*"
    for directory in sorted(root.glob(pattern), reverse=True):
        try:
            if json.loads((directory / summary).read_text(encoding="utf-8")).get("label") == name:
                return directory.name
        except (OSError, json.JSONDecodeError):
            continue
    return name


def read_run(app_name, run_id):
    root = Path(RUNS_DIR) / app_name
    try:
        run_id = run_id or (root / "LATEST").read_text(encoding="utf-8").strip()
        run_id = resolve_run(app_name, run_id)
        run = json.loads((root / run_id / "run.json").read_text(encoding="utf-8"))
        results = json.loads((root / run_id / "results.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Failure(f"Error: cannot read run {run_id or 'LATEST'} in {root}.", 2) from exc
    return run, results


def read_baseline(app_name, run_id):
    run_id = resolve_run(app_name, run_id, baseline=True)
    path = Path(RUNS_DIR) / app_name / run_id / "summary.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Failure(f"Error: cannot read Schemathesis run {run_id}.", 2) from exc


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


def cmd_ui(args):
    from apiguard.ui import serve

    return serve(load_app(args.app), args.port, open_browser=not args.no_browser)


COMMANDS = {
    "check": cmd_check,
    "spec": cmd_spec,
    "generate": cmd_generate,
    "run": cmd_run,
    "report": cmd_report,
    "compare": cmd_compare,
    "baseline": cmd_baseline,
    "ui": cmd_ui,
}


if __name__ == "__main__":
    raise SystemExit(main())
