import pytest

from apiguard.stability import changed_outcomes, flaky_tests, validation_report


def test_consistent_results_can_arrive_in_a_different_order():
    first = [{"id": "A", "outcome": "passed"}, {"id": "B", "outcome": "failed"}]
    assert changed_outcomes(first, list(reversed(first))) == []


def test_flags_a_test_that_changes_its_answer():
    first = [{"id": "A", "outcome": "passed"}, {"id": "B", "outcome": "passed"}]
    second = [{"id": "A", "outcome": "failed"}, {"id": "B", "outcome": "passed"}]
    assert changed_outcomes(first, second) == ["A"]


def test_reports_an_incomplete_run():
    with pytest.raises(ValueError, match="different tests"):
        changed_outcomes([{"id": "A", "outcome": "passed"}], [])


def run(**outcomes):
    return [{"id": test_id, "outcome": outcome} for test_id, outcome in outcomes.items()]


def test_flaky_tests_across_many_runs():
    runs = [run(A="passed", B="passed"), run(A="passed", B="passed"), run(A="passed", B="failed")]
    assert flaky_tests(runs) == ["B"]


def test_validation_report_lists_saved_rejected_and_flaky_tests():
    excluded = [
        {"test": {"id": "bad-json"}, "reason": "request body is not valid JSON"},
        {"test": "not an object", "reason": "test is not an object"},
    ]
    runs = [run(A="passed", B="failed"), run(A="passed", B="passed")]
    report = validation_report({"suite_id": "s1"}, excluded, runs)
    assert report["saved"] == ["A", "B"]
    assert report["rejected"] == [
        {"id": "bad-json", "reason": "request body is not valid JSON"},
        {"id": None, "reason": "test is not an object"},
    ]
    assert report["flaky"] == [{"id": "B", "outcomes": ["failed", "passed"]}]
