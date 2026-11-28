"""Format run results, failure categories and run comparisons for the CLI."""

from apiguard.classifier import CATEGORIES, UNCLASSIFIED
from apiguard.validator import TEST_TYPES

CATEGORY_LABELS = {**CATEGORIES, UNCLASSIFIED: "Unclassified failure"}


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
            f"{run['requests']} requests, {run['seconds']} s, "
            + (
                "AI model used for classification"
                if run.get("ai_model_used")
                else "no AI model used"
            )
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
        lines += ["", f"{label_text} ({len(in_category)}):"]
        rows = [
            (r["id"], r["operation"], r["role"], r["detail"], _classified_by(r))
            for r in in_category
        ]
        lines += ["  " + line for line in table(rows)]
    if run.get("ai_note"):
        lines += ["", run["ai_note"]]
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


def _classified_by(result):
    return {"rule": f"rule {result.get('rule')}", "ai": "AI model"}.get(
        result.get("classified_by"), "-"
    )


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
