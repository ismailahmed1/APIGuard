"""Format generated suites for the CLI."""


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
