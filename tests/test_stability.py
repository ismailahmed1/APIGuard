import pytest

from apiguard.stability import changed_outcomes


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
