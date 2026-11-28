"""Classify each failed test into one FR-10 category with fixed rules."""

import json
from pathlib import Path

# The eight FR-10 categories, in report order.
CATEGORIES = {
    "unexpected_status": "Unexpected status code",
    "response_schema_mismatch": "Response-schema mismatch",
    "input_validation": "Input-validation failure",
    "auth_failure": "Authentication or authorization failure",
    "business_logic": "Business-logic or state failure",
    "generated_test_error": "Generated-test error",
    "configuration_error": "Configuration error",
    "infrastructure_error": "Infrastructure error",
}
UNCLASSIFIED = "unclassified"
# Problems that the runner finds before the API answers; it sets these categories itself.
RUNNER_CATEGORIES = ("generated_test_error", "configuration_error", "infrastructure_error")


def _status(result):
    return (result.get("actual") or {}).get("status")


def _expected(result):
    return (result.get("expected") or {}).get("status")


def _success(status):
    return status is not None and 200 <= status < 300


# Each rule is (rule ID, category, test). The first rule that matches gives the category.
RULES = [
    ("INF-1", "infrastructure_error", lambda r: _status(r) in (502, 503, 504)),
    (
        "SCH-1",
        "response_schema_mismatch",
        lambda r: (r.get("detail") or "").startswith(
            ("response does not match", "response is not")
        ),
    ),
    (
        "AUTH-1",
        "auth_failure",
        lambda r: r["type"] in ("authentication", "authorization") and _success(_status(r)),
    ),
    (
        "AUTH-2",
        "auth_failure",
        lambda r: r["role"] != "anonymous" and _success(_expected(r)) and _status(r) in (401, 403),
    ),
    ("VAL-1", "input_validation", lambda r: _expected(r) == 422 and _success(_status(r))),
    ("VAL-2", "input_validation", lambda r: _success(_expected(r)) and _status(r) == 422),
    ("BIZ-1", "business_logic", lambda r: r["type"] == "stateful_workflow"),
    ("BIZ-2", "business_logic", lambda r: _success(_expected(r)) and _status(r) in (404, 409)),
    (
        "STA-1",
        "unexpected_status",
        lambda r: _status(r) is not None and _status(r) != _expected(r),
    ),
]


def classify(result):
    """Return (category, rule ID) for a result; (None, None) for a passed test."""
    if result["outcome"] == "passed":
        return None, None
    if result.get("category") in RUNNER_CATEGORIES:
        return result["category"], "RUN-1"
    for rule_id, category, matches in RULES:
        if matches(result):
            return category, rule_id
    return UNCLASSIFIED, None


def apply(result):
    """Set the category, the rule and the classifier of a result, and return the result."""
    category, rule_id = classify(result)
    result["category"] = category
    result["rule"] = rule_id
    result["classified_by"] = "rule" if category not in (None, UNCLASSIFIED) else None
    return result


def accuracy(path):
    """Classify a labelled set of known failures. Returns (correct, total, wrong cases)."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    wrong = []
    for case in cases:
        category, _ = classify(case["result"])
        if category != case["expected_category"]:
            wrong.append(
                {"name": case["name"], "expected": case["expected_category"], "got": category}
            )
    return len(cases) - len(wrong), len(cases), wrong


AI_SYSTEM = """You classify failed API tests for APIGuard. For each failure, select the one \
category that best explains it. Use only the categories that you are given. Base your answer on the \
operation, the request, the expected result, the actual result and the detail."""


def classify_with_ai(results, ai):
    """Send only the unclassified failures to the AI model. Results must be redacted first.

    Returns a short note for the run record, or None when no failure needed the model.
    """
    from apiguard.ai import AIError  # Runs without the AI model never import the SDK client.

    pending = {r["id"]: r for r in results if r["category"] == UNCLASSIFIED}
    if not pending:
        return None
    failures = [
        {
            "id": r["id"],
            "test_type": r["type"],
            "operation": r["operation"],
            "role": r["role"],
            "request": r.get("request"),
            "expected": r.get("expected"),
            "actual": r.get("actual"),
            "detail": r.get("detail"),
        }
        for r in pending.values()
    ]
    prompt = (
        "Categories:\n"
        + "\n".join(f"- {key}: {label}" for key, label in CATEGORIES.items())
        + "\n\nFailures:\n"
        + json.dumps(failures, indent=1)
    )
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["classifications"],
        "properties": {
            "classifications": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["id", "category"],
                    "properties": {
                        "id": {"type": "string"},
                        "category": {"type": "string", "enum": list(CATEGORIES)},
                    },
                },
            }
        },
    }
    try:
        answer = ai.generate_json(AI_SYSTEM, prompt, schema, max_tokens=4000)
    except AIError as exc:
        return f"AI classification stopped: {exc}"
    for item in answer.get("classifications", []):
        result = pending.get(item.get("id"))
        # Accept only the eight categories, and only for a failure that was sent.
        if result is None or item.get("category") not in CATEGORIES:
            continue
        result["category"] = item["category"]
        result["classified_by"] = "ai"
    return None
