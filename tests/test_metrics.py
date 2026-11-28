import json

from shop_spec import SHOP

from apiguard.metrics import record_metrics, run_metrics
from apiguard.operations import extract_operations

OPERATIONS = extract_operations(SHOP)
METADATA = {
    "generation_method": "structured-definitions",
    "generation_seconds": 12.5,
    "counts": {"generated": 4, "valid": 3, "excluded": 1},
    "ai_usage": {"calls": 2, "input_tokens": 100, "output_tokens": 50, "cost_usd": 0.01},
}
RUN = {
    "run_id": "r1",
    "app": "shop",
    "label": "F01",
    "suite_id": "s1",
    "started_at": "2026-11-28T12:00:00+00:00",
    "seconds": 2.5,
    "requests": 4,
    "outcomes": {"passed": 1, "failed": 1, "error": 1},
}


def result(operation, outcome):
    return {"operation": operation, "outcome": outcome}


def test_run_metrics():
    results = [
        result("GET /api/products", "passed"),
        result("GET /api/products", "failed"),
        result("POST /api/products", "error"),
    ]
    metrics = run_metrics(METADATA, RUN, results, OPERATIONS)
    assert metrics["generation_seconds"] == 12.5
    assert (metrics["run_seconds"], metrics["requests"]) == (2.5, 4)
    assert (metrics["ai_calls"], metrics["output_tokens"], metrics["cost_usd"]) == (2, 50, 0.01)
    assert metrics["operations_tested"] == 2
    assert metrics["endpoint_coverage"] == round(2 / len(OPERATIONS), 4)
    # Two of the four generated tests ran to a result: one was excluded, one had an error.
    assert metrics["executable_test_rate"] == 0.5


def test_operations_missing_from_the_spec_do_not_count_as_covered():
    metrics = run_metrics(METADATA, RUN, [result("GET /api/old", "error")], OPERATIONS)
    assert metrics["operations_tested"] == 0


def test_each_run_adds_one_line(tmp_path):
    metrics = run_metrics(METADATA, RUN, [result("GET /api/products", "passed")], OPERATIONS)
    path = record_metrics(metrics, tmp_path / "metrics")
    record_metrics({**metrics, "run_id": "r2"}, tmp_path / "metrics")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert path.name == "shop.jsonl"
    assert [line["run_id"] for line in lines] == ["r1", "r2"]
