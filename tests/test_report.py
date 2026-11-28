import json

import pytest
import yaml

from apiguard.cli import main

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
RUN = {
    "run_id": "20261128-120000",
    "app": "nexstock",
    "label": None,
    "suite_id": "s1",
    "started_at": "2026-11-28T12:00:00+00:00",
    "seconds": 3.5,
    "requests": 3,
    "total": 2,
    "outcomes": {"passed": 1, "failed": 1},
    "categories": {"unexpected_status": 1},
}
RESULTS = [
    {
        "id": "list",
        "type": "happy_path",
        "operation": "GET /api/products",
        "role": "admin",
        "expected": {"status": 200},
        "actual": {"status": 200, "body_excerpt": "[]"},
        "outcome": "passed",
        "category": None,
        "detail": None,
    },
    {
        "id": "inventory",
        "type": "happy_path",
        "operation": "GET /api/inventory",
        "role": "admin",
        "expected": {"status": 200},
        "actual": {"status": 500, "body_excerpt": f"leaked {TOKEN}"},
        "outcome": "failed",
        "category": "unexpected_status",
        "detail": "server error 500 (expected 200)",
    },
]
ALERTS = [
    {
        "rule": "MON-01",
        "name": "Repeated failed logins",
        "app": "nexstock",
        "severity": "high",
        "time": "2026-11-28T12:00:01.000+00:00",
        "last_seen": "2026-11-28T12:00:05.000+00:00",
        "group_by": "ip",
        "group": "172.18.0.1",
        "matches": 1,
        "event_count": 5,
        "log_lines": ["{}"],
    }
]


@pytest.fixture
def configured_project(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    config = {
        "name": "nexstock",
        "base_url": "http://127.0.0.1:8000",
        "spec_location": "http://127.0.0.1:8000/openapi.json",
        "timeouts": {"request_seconds": 10, "run_seconds": 120},
        "auth": {},
        "reset": {},
    }
    (tmp_path / "configs" / "nexstock.yaml").write_text(yaml.safe_dump(config))
    monkeypatch.chdir(tmp_path)


def save_run(tmp_path, alerts=ALERTS):
    directory = tmp_path / "runs" / "nexstock" / RUN["run_id"]
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(RUN))
    (directory / "results.json").write_text(json.dumps(RESULTS))
    if alerts is not None:
        (directory / "alerts.json").write_text(json.dumps(alerts))
    (tmp_path / "runs" / "nexstock" / "LATEST").write_text(RUN["run_id"])
    return directory


def test_report_has_totals_failures_and_alerts(configured_project, tmp_path, capsys):
    directory = save_run(tmp_path)
    assert main(["report", "nexstock", "--export"]) == 0
    shown = capsys.readouterr().out
    assert "MON-01 Repeated failed logins" in shown

    report = json.loads((directory / "report.json").read_text())
    assert report["totals"]["outcomes"] == {"passed": 1, "failed": 1}
    assert report["totals"]["by_type"] == {"happy_path": {"passed": 1, "total": 2}}
    assert [r["id"] for r in report["failures"]["unexpected_status"]] == ["inventory"]
    assert report["alerts"][0]["rule"] == "MON-01"

    markdown = (directory / "report.md").read_text()
    for heading in ("## Totals", "## Failures by category", "## Security alerts"):
        assert heading in markdown
    assert "| inventory | GET /api/inventory | admin |" in markdown
    assert "MON-01 Repeated failed logins" in markdown

    for text in (shown, markdown, json.dumps(report)):
        assert TOKEN not in text


def test_report_without_monitor_says_so(configured_project, tmp_path, capsys):
    directory = save_run(tmp_path, alerts=None)
    assert main(["report", "nexstock", "--export"]) == 0
    assert "The security monitor did not run." in capsys.readouterr().out
    assert json.loads((directory / "report.json").read_text())["alerts"] is None
    assert "The security monitor did not run." in (directory / "report.md").read_text()
