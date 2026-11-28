import json
from pathlib import Path

from apiguard.classifier import CATEGORIES, UNCLASSIFIED, accuracy, apply, classify

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
