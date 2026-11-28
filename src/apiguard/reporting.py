"""Format run results, failure categories and run comparisons for the CLI."""

import json
import re

from apiguard.validator import TEST_TYPES

JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")

CATEGORY_LABELS = {
    "api_failure": "API failure",
    "test_error": "Generated-test error",
    "configuration_error": "Configuration error",
    "infrastructure_error": "Infrastructure error",
}


def table(rows):
    """Left-align columns; the last column is not padded."""
    widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]) - 1)]
    return [
        "  ".join([*(str(cell).ljust(w) for cell, w in zip(row, widths)), str(row[-1])])
        for row in rows
    ]


def format_suite(metadata, excluded):
    usage = metadata["ai_usage"]
    counts = metadata["counts"]
    cost = f"${usage['cost_usd']:.2f}" if usage.get("cost_usd") is not None else "unknown cost"
    lines = [
        (
            f"Saved suite {metadata['suite_id']}: {counts['valid']} valid tests for "
            f"{len(metadata['operations'])} operations ({counts['excluded']} excluded)"
        ),
        (
            f"AI model {metadata['model']}: {usage['calls']} calls, {usage['input_tokens']} input "
            f"and {usage['output_tokens']} output tokens, {cost}, {metadata['generation_seconds']} s"
        ),
    ]
    if metadata.get("stopped_reason"):
        lines.append(f"Generation stopped early: {metadata['stopped_reason']}")
    if excluded:
        lines += ["", "Excluded tests:"]
        for item in excluded:
            test = item["test"] if isinstance(item["test"], dict) else {}
            lines.append(f"  {test.get('id', '?')}: {item['reason']}")
    return "\n".join(lines)


def format_run(run, results):
    outcomes = run["outcomes"]
    label = f" [{run['label']}]" if run.get("label") else ""
    lines = [
        (
            f"Run {run['run_id']}{label}: suite {run['suite_id']}, {run['total']} tests, "
            f"{run['requests']} requests, {run['seconds']} s, no AI model used"
        ),
        "  ".join(f"{name} {outcomes.get(name, 0)}" for name in ("passed", "failed", "error"))
        + (f"  not run {outcomes['not_run']}" if outcomes.get("not_run") else ""),
        "",
    ]
    rows = [("TEST TYPE", "PASSED", "TOTAL")]
    for test_type in TEST_TYPES:
        of_type = [r for r in results if r["type"] == test_type]
        if of_type:
            passed = sum(r["outcome"] == "passed" for r in of_type)
            rows.append((test_type, passed, len(of_type)))
    lines += table(rows)

    problems = [r for r in results if r["outcome"] != "passed"]
    for category, label_text in CATEGORY_LABELS.items():
        in_category = [r for r in problems if r["category"] == category]
        if not in_category:
            continue
        lines += ["", f"{label_text}s ({len(in_category)}):"]
        rows = [(r["id"], r["operation"], r["role"], r["detail"]) for r in in_category]
        lines += ["  " + line for line in table(rows)]
    return "\n".join(lines)


def format_alerts(alerts):
    """One line for each security alert."""
    if not alerts:
        return []
    rows = [("TIME", "SEVERITY", "RULE", "GROUP", "EVENTS")]
    for alert in alerts:
        group = f"{alert['group_by']}={alert['group']}" if alert.get("group_by") else "-"
        rows.append(
            (
                alert["time"],
                alert["severity"],
                f"{alert['rule']} {alert['name']}",
                group,
                alert["event_count"],
            )
        )
    return table(rows)


def compare_runs(base, base_results, run, results):
    """Tests that pass in the base run and fail in the other run reveal a new fault."""
    before = {r["id"]: r for r in base_results}
    newly_failing = [
        r
        for r in results
        if r["outcome"] != "passed" and before.get(r["id"], {}).get("outcome") == "passed"
    ]
    still_failing = [
        r
        for r in results
        if r["outcome"] != "passed" and before.get(r["id"], {}).get("outcome") != "passed"
    ]
    name = run.get("label") or run["run_id"]
    lines = [f"Compared run {run['run_id']} ({name}) with base run {base['run_id']}:"]
    if newly_failing:
        lines.append(f"DETECTED: {len(newly_failing)} tests pass on the base run and fail here.")
        rows = [(r["id"], r["type"], r["operation"], r["detail"]) for r in newly_failing]
        lines += ["  " + line for line in table(rows)]
    else:
        lines.append("NOT DETECTED: no test changed from passed to failed.")
    if still_failing:
        lines.append(f"{len(still_failing)} tests also fail on the base run (existing defects).")
    return "\n".join(lines), bool(newly_failing)


def build_report(run, results, alerts):
    """One report with the totals, the failures by category and the security alerts."""
    failures = [r for r in results if r["outcome"] != "passed"]
    by_category = {}
    for result in failures:
        by_category.setdefault(result["category"] or "unclassified", []).append(result)
    by_type = {}
    for result in results:
        counts = by_type.setdefault(result["type"], {"passed": 0, "total": 0})
        counts["total"] += 1
        counts["passed"] += result["outcome"] == "passed"
    return {
        "run_id": run["run_id"],
        "app": run["app"],
        "label": run.get("label"),
        "suite_id": run["suite_id"],
        "started_at": run.get("started_at"),
        "totals": {
            "tests": run["total"],
            "outcomes": run["outcomes"],
            "requests": run["requests"],
            "seconds": run["seconds"],
            "by_type": by_type,
        },
        "failures": {
            category: [
                {
                    "id": r["id"],
                    "type": r["type"],
                    "operation": r["operation"],
                    "role": r["role"],
                    "expected": r.get("expected"),
                    "actual": r.get("actual"),
                    "detail": r["detail"],
                    "classified_by": r.get("classified_by"),
                    "rule": r.get("rule"),
                }
                for r in items
            ]
            for category, items in sorted(
                by_category.items(), key=lambda kv: _category_order(kv[0])
            )
        },
        "alerts": alerts,
    }


def _category_order(category):
    order = list(CATEGORY_LABELS)
    return order.index(category) if category in order else len(order)


def report_json(report):
    return _clean(json.dumps(report, indent=2) + "\n")


def report_markdown(report):
    totals = report["totals"]
    outcomes = totals["outcomes"]
    label = f" ({report['label']})" if report.get("label") else ""
    lines = [
        f"# APIGuard report: {report['app']} run {report['run_id']}{label}",
        "",
        f"Suite `{report['suite_id']}`, started {report['started_at']}.",
        "",
        "## Totals",
        "",
        "| Tests | Passed | Failed | Error | Not run | Requests | Seconds |",
        "|---|---|---|---|---|---|---|",
        (
            f"| {totals['tests']} | {outcomes.get('passed', 0)} | {outcomes.get('failed', 0)} "
            f"| {outcomes.get('error', 0)} | {outcomes.get('not_run', 0)} | {totals['requests']} "
            f"| {totals['seconds']} |"
        ),
        "",
        "| Test type | Passed | Total |",
        "|---|---|---|",
        *(f"| {name} | {c['passed']} | {c['total']} |" for name, c in totals["by_type"].items()),
        "",
        "## Failures by category",
        "",
    ]
    if not report["failures"]:
        lines.append("No failures.")
    for category, items in report["failures"].items():
        lines += [
            f"### {CATEGORY_LABELS.get(category, category)} ({len(items)})",
            "",
            "| Test | Operation | Role | Detail |",
            "|---|---|---|---|",
            *(
                f"| {_cell(r['id'])} | {_cell(r['operation'])} | {r['role']} | {_cell(r['detail'])} |"
                for r in items
            ),
            "",
        ]
    lines += ["## Security alerts", ""]
    if report["alerts"] is None:
        lines.append("The security monitor did not run.")
    elif not report["alerts"]:
        lines.append("No alerts.")
    else:
        lines += ["| Time | Severity | Rule | Group | Events |", "|---|---|---|---|---|"]
        for alert in report["alerts"]:
            group = f"{alert['group_by']}={alert['group']}" if alert.get("group_by") else "-"
            lines.append(
                f"| {alert['time']} | {alert['severity']} | {alert['rule']} {alert['name']} "
                f"| {_cell(group)} | {alert['event_count']} |"
            )
    return _clean("\n".join(lines) + "\n")


def _cell(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _clean(text):
    """The saved results are already redacted; this removes any token that remains (NFR-04)."""
    return JWT.sub("[REDACTED-TOKEN]", text)
