"""Record the evaluation data of each run with no manual steps (FR-13)."""

import json
from pathlib import Path

METRICS_DIR = "eval/metrics"
# Outcomes of tests that ran to a pass or fail result without a manual fix.
EXECUTED = ("passed", "failed")


def run_metrics(metadata, run, results, operations):
    """Return the metrics of one run of a saved suite."""
    all_operations = {f"{op.method} {op.path}" for op in operations}
    tested = {r["operation"] for r in results} & all_operations
    counts = metadata.get("counts", {})
    generated = counts.get("generated", len(results))
    executed = sum(r["outcome"] in EXECUTED for r in results)
    usage = metadata.get("ai_usage") or {}
    return {
        "run_id": run["run_id"],
        "app": run["app"],
        "label": run.get("label"),
        "suite_id": run["suite_id"],
        "generation_method": metadata.get("generation_method"),
        "started_at": run.get("started_at"),
        "generation_seconds": metadata.get("generation_seconds"),
        "run_seconds": run["seconds"],
        "requests": run["requests"],
        "ai_calls": usage.get("calls"),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cost_usd": usage.get("cost_usd"),
        "tests_generated": generated,
        "tests_valid": counts.get("valid", len(results)),
        "tests_executed": executed,
        "operations": len(all_operations),
        "operations_tested": len(tested),
        "endpoint_coverage": _rate(len(tested), len(all_operations)),
        "executable_test_rate": _rate(executed, generated),
        "outcomes": run["outcomes"],
    }


def record_metrics(metrics, metrics_dir=METRICS_DIR):
    """Add the metrics as one JSON line to eval/metrics/<app>.jsonl. Returns the file path."""
    path = Path(metrics_dir) / f"{metrics['app']}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(metrics) + "\n")
    return path


def _rate(part, whole):
    return round(part / whole, 4) if whole else None
