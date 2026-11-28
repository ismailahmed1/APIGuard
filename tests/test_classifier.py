import json
from pathlib import Path

from test_generation import FakeAnthropic

from apiguard.ai import AIClient
from apiguard.classifier import (
    CATEGORIES,
    UNCLASSIFIED,
    accuracy,
    apply,
    classify,
    classify_with_ai,
)

KNOWN = Path(__file__).resolve().parents[1] / "eval" / "known_failures.json"


def result(outcome="failed", status=500, expected=200, test_type="happy_path", detail=""):
    return {
        "type": test_type,
        "role": "admin",
        "expected": {"status": expected},
        "actual": {"status": status} if status else None,
        "outcome": outcome,
        "category": None,
        "detail": detail,
    }


def test_each_known_failure_gets_the_correct_category():
    correct, total, wrong = accuracy(KNOWN)
    assert wrong == []
    assert correct == total


def test_labelled_set_covers_every_category():
    labels = {case["expected_category"] for case in json.loads(KNOWN.read_text())}
    assert labels == set(CATEGORIES)


def test_passed_test_has_no_category():
    assert classify(result(outcome="passed", status=200)) == (None, None)


def test_failure_that_no_rule_matches_is_unclassified():
    unmatched = apply(result(status=None, detail="no response"))
    assert unmatched["category"] == UNCLASSIFIED
    assert unmatched["rule"] is None
    assert unmatched["classified_by"] is None


def test_rule_is_recorded():
    matched = apply(result(status=200, expected=422, test_type="schema_validation"))
    assert (matched["category"], matched["rule"], matched["classified_by"]) == (
        "input_validation",
        "VAL-1",
        "rule",
    )


def unclassified(test_id):
    return {
        "id": test_id,
        "type": "happy_path",
        "operation": "GET /api/products",
        "role": "admin",
        "request": {"method": "GET", "path": "/api/products"},
        "expected": {"status": 200},
        "actual": None,
        "outcome": "failed",
        "category": UNCLASSIFIED,
        "rule": None,
        "classified_by": None,
        "detail": "no response",
    }


def ai_with(*answers):
    fake = FakeAnthropic([(json.dumps({"classifications": list(answers)}), "end_turn")])
    return AIClient("claude-opus-5-5", {}, client=fake), fake


def test_ai_classifies_only_unclassified_failures():
    ruled = apply(result(status=200, expected=422, test_type="schema_validation"))
    ruled["id"] = "ruled"
    results = [ruled, unclassified("open")]
    ai, fake = ai_with({"id": "open", "category": "infrastructure_error"})
    assert classify_with_ai(results, ai) is None
    assert (results[1]["category"], results[1]["classified_by"]) == ("infrastructure_error", "ai")
    assert ruled["classified_by"] == "rule"
    prompt = fake.requests[0]["messages"][0]["content"]
    assert '"open"' in prompt
    assert '"ruled"' not in prompt


def test_ai_answers_outside_the_categories_are_ignored():
    results = [unclassified("open")]
    ai, _ = ai_with(
        {"id": "open", "category": "made_up"}, {"id": "other", "category": "auth_failure"}
    )
    classify_with_ai(results, ai)
    assert results[0]["category"] == UNCLASSIFIED
    assert results[0]["classified_by"] is None


def test_no_model_call_when_every_failure_is_classified():
    ai, fake = ai_with()
    assert classify_with_ai([apply(result(status=500))], ai) is None
    assert fake.requests == []


def test_ai_error_leaves_failures_unclassified():
    ai = AIClient("claude-opus-5-5", {"max_calls": 0}, client=FakeAnthropic([]))
    results = [unclassified("open")]
    note = classify_with_ai(results, ai)
    assert note.startswith("AI classification stopped")
    assert results[0]["category"] == UNCLASSIFIED
