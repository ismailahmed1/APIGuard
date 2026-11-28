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
from apiguard.builder import build_pytest, collect
from apiguard.config import ConfigError, load_config
from apiguard.docker_run import run_in_docker
from apiguard.generator import generate_suite
from apiguard.metrics import record_metrics, run_metrics
from apiguard.monitor import MonitorError, monitor_run
from apiguard.openapi import SpecError, get_response, load_spec
from apiguard.operations import extract_operations
from apiguard.reporting import (
    build_report,
    compare_runs,
    format_alerts,
    format_run,
    format_suite,
    format_validation,
    report_json,
    report_markdown,
    table,
)
from apiguard.runner import RunError, get_token, load_suite, reset_app, run_suite
from apiguard.stability import validation_report

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
    run.add_argument(
        "--ai-classify",
        action="store_true",
        help="Send failures that no rule classifies to the AI model.",
    )

    validate = command(
        "validate", "Run a saved suite more than one time and flag tests with different results."
    )
    validate.add_argument("--suite", help="Suite ID (default: the latest suite).")
    validate.add_argument("--runs", type=int, default=3, help="Number of runs (default: 3).")
    run.add_argument(
        "--docker",
        action="store_true",
        help="Run the suite's Pytest files in a container on the app's Docker network.",
    )
    build = command("build", "Convert a saved suite to Pytest files.")
    build.add_argument("--suite", help="Suite ID (default: the latest suite).")
    report = command("report", "Show the report of a saved run.")
    report.add_argument("--run", help="Run ID (default: the latest run).")
    report.add_argument(
        "--export",
        action="store_true",
        help="Also save the report as report.md and report.json in the run directory.",
    )
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
    if args.docker:
        return run_docker(config, args)
    try:
        suite_dir, metadata, tests = load_suite(SUITES_DIR, config["name"], args.suite)
        # The suite's own snapshot describes the operations that its tests were written for.
        snapshot = load_spec(str(suite_dir / "openapi.yaml"), config["timeouts"]["request_seconds"])
        operations = extract_operations(snapshot.document)
        directory, run, results = run_suite(
            config,
            metadata,
            tests,
            operations,
            RUNS_DIR,
            args.label,
            reset=not args.no_reset,
            ai=classification_ai(config) if args.ai_classify else None,
        )
    except (RunError, SpecError) as exc:
        raise Failure(f"Run error: {exc}", 1) from exc
    print(format_run(run, results))
    metrics = run_metrics(metadata, run, results, operations)
    path = record_metrics(metrics)
    print(
        f"\nMetrics: endpoint coverage {_percent(metrics['endpoint_coverage'])}, "
        f"executable tests {_percent(metrics['executable_test_rate'])}; saved to {path}"
    )
    if config.get("monitor"):
        since = datetime.fromisoformat(run["started_at"])
        try:
            record, alerts = monitor_run(config, since, datetime.now(UTC), directory)
        except MonitorError as exc:
            print(f"\nSecurity monitor: {exc}", file=sys.stderr)
        else:
            print(f"\nSecurity monitor: {record['events']} log events, {len(alerts)} alerts")
            print("\n".join("  " + line for line in format_alerts(alerts)))
    return 0 if run["outcomes"].get("passed", 0) == run["total"] else 1


def _percent(rate):
    return "n/a" if rate is None else f"{rate:.0%}"


def classification_ai(config):
    """The AI client for failures that no rule classifies; it uses the generation settings."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise Failure("Configuration error: ANTHROPIC_API_KEY is not set.", 2)
    settings = {**config.get("generation", {}), **config.get("classification", {})}
    return AIClient(
        settings.get("model", DEFAULT_MODEL),
        settings.get("limits", {}),
        effort=settings.get("effort", "low"),
    )


def cmd_validate(args):
    if args.runs < 2:
        raise Failure("Error: --runs must be 2 or more.", 2)
    config = load_app(args.app)
    try:
        suite_dir, metadata, tests = load_suite(SUITES_DIR, config["name"], args.suite)
        snapshot = load_spec(str(suite_dir / "openapi.yaml"), config["timeouts"]["request_seconds"])
        operations = extract_operations(snapshot.document)
        runs = []
        for number in range(1, args.runs + 1):
            # Each run starts from the same seed data (FR-08).
            _, run, results = run_suite(
                config, metadata, tests, operations, RUNS_DIR, f"validate-{number}"
            )
            print(f"Run {number} of {args.runs}: {run['run_id']}")
            runs.append(results)
        excluded = json.loads((suite_dir / "excluded.json").read_text(encoding="utf-8"))
    except (RunError, SpecError) as exc:
        raise Failure(f"Run error: {exc}", 1) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise Failure(f"Error: cannot read the excluded tests of {suite_dir}.", 2) from exc
    report = validation_report(metadata, excluded, runs)
    path = suite_dir / "validation.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(format_validation(report))
    print(f"\nSaved to {path}")
    return 1 if report["flaky"] else 0


def run_docker(config, args):
    try:
        suite_dir, _, tests = load_suite(SUITES_DIR, config["name"], args.suite)
        if not (suite_dir / "pytest" / "conftest.py").exists():
            build_pytest(suite_dir, tests)
        directory, summary = run_in_docker(config, suite_dir, RUNS_DIR, args.label)
    except RunError as exc:
        raise Failure(f"Run error: {exc}", 1) from exc
    outcomes = summary["outcomes"]
    print(
        f"Docker run {summary['run_id']}: suite {summary['suite']}, {summary['total']} tests, "
        f"{summary['seconds']} s, no AI model used"
    )
    print("  ".join(f"{name} {outcomes.get(name, 0)}" for name in ("passed", "failed", "error")))
    if summary["timed_out"]:
        print("The run time limit stopped the container.")
    print(f"Saved to {directory}")
    return 0 if summary["total"] and outcomes.get("passed", 0) == summary["total"] else 1


def cmd_build(args):
    config = load_app(args.app)
    try:
        suite_dir, metadata, tests = load_suite(SUITES_DIR, config["name"], args.suite)
    except RunError as exc:
        raise Failure(f"Error: {exc}", 2) from exc
    paths = build_pytest(suite_dir, tests)
    result = {"files_written": len(paths), "tests_written": len(tests), **collect(paths[0].parent)}
    metadata["pytest_build"] = result
    (suite_dir / "suite.json").write_text(json.dumps(metadata, indent=2) + "\n", "utf-8")
    print(
        f"Wrote {len(tests)} tests in {len(paths)} files to {suite_dir / 'pytest'}. "
        f"Pytest collects {result['tests_collected']} tests in {result['files_collected']} files."
    )
    print(f"Run them with: python -m pytest {suite_dir / 'pytest'}")
    return 0 if result["collect_exit_code"] == 0 else 1


def cmd_report(args):
    config = load_app(args.app)
    run, results = read_run(config["name"], args.run)
    directory = Path(RUNS_DIR) / config["name"] / run["run_id"]
    try:
        alerts = json.loads((directory / "alerts.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        alerts = None  # The security monitor did not run for this run.
    print(format_run(run, results))
    print("\nSecurity alerts:")
    if alerts is None:
        print("  The security monitor did not run.")
    else:
        print("\n".join("  " + line for line in format_alerts(alerts)) or "  No alerts.")
    if args.export:
        report = build_report(run, results, alerts)
        (directory / "report.md").write_text(report_markdown(report), encoding="utf-8")
        (directory / "report.json").write_text(report_json(report), encoding="utf-8")
        print(f"\nSaved {directory / 'report.md'} and {directory / 'report.json'}")
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
    "validate": cmd_validate,
    "build": cmd_build,
    "report": cmd_report,
    "compare": cmd_compare,
    "baseline": cmd_baseline,
    "ui": cmd_ui,
}


if __name__ == "__main__":
    raise SystemExit(main())
