import json
import sys
import threading
from http.server import ThreadingHTTPServer

import httpx
import pytest

from apiguard import ui

CONFIG = {
    "name": "shop",
    "base_url": "http://127.0.0.1:9",
    "spec_location": "http://127.0.0.1:9/openapi.json",
}


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    suite = tmp_path / "suites" / "shop" / "20260101-000000"
    suite.mkdir(parents=True)
    (suite / "suite.json").write_text(
        json.dumps(
            {
                "suite_id": "20260101-000000",
                "tags": ["Products"],
                "operations": ["GET /"],
                "counts": {"valid": 1},
                "ai_usage": {"cost_usd": 0.1},
            }
        )
    )
    (suite / "tests.json").write_text(json.dumps([{"id": "t1", "type": "happy_path"}]))
    for run_id, label, outcome in [
        ("20260101-000001", "original", "passed"),
        ("20260101-000002", "F01-x", "failed"),
    ]:
        run = tmp_path / "runs" / "shop" / run_id
        run.mkdir(parents=True)
        (run / "run.json").write_text(
            json.dumps({"run_id": run_id, "label": label, "suite_id": "20260101-000000"})
        )
        (run / "results.json").write_text(
            json.dumps([{"id": "t1", "outcome": outcome, "operation": "GET /"}])
        )
    faults = tmp_path / "apps" / "shop" / "faults"
    faults.mkdir(parents=True)
    (faults / "faults.yaml").write_text("- id: F01-x\n  category: Broken\n  operation: GET /\n")
    space = ui.Workspace(CONFIG, tmp_path)
    monkeypatch.setattr(space, "tags", lambda: [{"name": "Products", "operations": 1}])
    return space


def test_lists_saved_suites_runs_and_versions(workspace):
    assert workspace.suite_list()[0]["types"] == {"happy_path": 1}
    assert [r["label"] for r in workspace.run_list()] == ["F01-x", "original"]
    assert [v["id"] for v in workspace.variants()] == ["original", "F01-x"]


def test_compare_finds_newly_failing_tests(workspace):
    result = workspace.compare("20260101-000001", "20260101-000002")
    assert [r["id"] for r in result["detected"]] == ["t1"]
    assert result["same_suite"] is True


@pytest.mark.parametrize(
    ("action", "params", "message"),
    [
        ("shell", {}, "unknown action"),
        ("generate", {"tags": ["Orders"]}, "choose one or more operation tags"),
        ("variant", {"variant": "F99"}, "unknown application version"),
        ("run", {"suite": "../../etc"}, "invalid ID"),
    ],
)
def test_only_fixed_actions_are_accepted(workspace, action, params, message):
    with pytest.raises(ui.UIError, match=message):
        workspace.start(action, params)


def test_run_removes_the_ai_key_and_labels_the_version(workspace, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(workspace, "running_variant", lambda: "F01-x")
    started = []
    monkeypatch.setattr(workspace, "_execute", lambda job: started.append(job))
    monkeypatch.setattr(ui.threading, "Thread", lambda target, args, daemon: _Now(target, args))
    workspace.start("run", {"suite": "20260101-000000"})
    job = started[0]
    assert job.env["ANTHROPIC_API_KEY"] == ""
    assert job.command[-4:] == ["--suite", "20260101-000000", "--label", "F01-x"]


class _Now:
    def __init__(self, target, args):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_task_output_is_collected(workspace):
    job = ui.Job("run", "t", [sys.executable, "-c", "print('hello'); raise SystemExit(1)"], {})
    workspace._execute(job)
    assert job.log[-1] == "hello"
    assert job.status == "done"  # A run that has failing tests still completed.


def test_server_refuses_other_hosts(workspace):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui.make_handler(workspace, 0))
    port = server.server_address[1]
    server.RequestHandlerClass = ui.make_handler(workspace, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{port}"
        assert httpx.get(f"{url}/").status_code == 200
        ok = httpx.get(f"{url}/api/run?id=20260101-000001")
        assert ok.json()["run"]["label"] == "original"
        assert httpx.get(f"{url}/api/state", headers={"Host": "evil.test"}).status_code == 403
        cross = httpx.post(
            f"{url}/api/start", json={"action": "run"}, headers={"Origin": "http://evil.test"}
        )
        assert cross.status_code == 403
        assert httpx.post(f"{url}/api/start", json={"action": "x"}).status_code == 400
    finally:
        server.shutdown()
        server.server_close()


def test_commands_are_shown_as_typed(tmp_path):
    command = [sys.executable, "-c", ui.CLI, "run", "nexstock", "--suite", "1"]
    assert ui._display(command, tmp_path) == "apiguard run nexstock --suite 1"
    script = [sys.executable, str(tmp_path.resolve() / "scripts" / "e.py")]
    assert ui._display(script, tmp_path) == "python scripts/e.py"
