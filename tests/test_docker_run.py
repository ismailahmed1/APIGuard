import subprocess

import pytest

from apiguard.docker_run import parse_junit, run_in_docker
from apiguard.runner import RunError

JUNIT = """<?xml version="1.0"?>
<testsuites><testsuite>
<testcase name="test_ok"/>
<testcase name="test_slow"><failure message="infrastructure_error: request timed out"/></testcase>
<testcase name="test_bad"><failure message="unexpected_status"/></testcase>
<testcase name="test_after"/>
</testsuite></testsuites>
"""


def config():
    return {
        "name": "shop",
        "timeouts": {"request_seconds": 5, "run_seconds": 60},
        "auth": {"roles": {"admin": {"email_env": "SHOP_EMAIL", "password_env": "SHOP_PASSWORD"}}},
        "reset": {"command": ["reset-shop"]},
        "docker_run": {
            "network": "shop_default",
            "base_url": "http://api:8000",
            "environment": {"PGPASSWORD": "local"},
        },
    }


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHOP_EMAIL", "admin@shop.test")
    monkeypatch.setenv("SHOP_PASSWORD", "Sup3r-Secret!")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-ant-test\n")
    suite = tmp_path / "suites" / "shop" / "s1"
    (suite / "pytest").mkdir(parents=True)
    (suite / "pytest" / "conftest.py").write_text("")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[:2] == ["docker", "run"]:
            results = next(v for v in command if v.endswith(":/results")).rsplit(":", 1)[0]
            (tmp_path / results / "junit.xml").write_text(JUNIT)
            return subprocess.CompletedProcess(command, 1, stdout="2 failed, 2 passed", stderr="")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("apiguard.docker_run.subprocess.run", fake_run)
    monkeypatch.setattr("apiguard.runner.subprocess.run", fake_run)
    return {"suite": suite, "commands": commands}


def test_runs_pytest_on_the_app_network_without_the_ai_key(project):
    directory, summary = run_in_docker(config(), project["suite"], "runs")
    build, reset, run = project["commands"]
    assert build[:2] == ["docker", "build"]
    assert reset == ["reset-shop"]  # The app is reset before the run.
    assert run[run.index("--network") + 1] == "shop_default"
    text = " ".join(run)
    assert "APIGUARD_IN_DOCKER=1" in text
    assert ":/work:ro" in text
    assert "empty.env:/work/.env:ro" in text
    # Credentials are passed by name; the AI key is not passed.
    assert "--env SHOP_PASSWORD " in text + " "
    assert "Sup3r-Secret!" not in text
    assert "ANTHROPIC" not in text
    # A failed or slow test does not stop the others (NFR-02, NFR-03).
    assert summary["outcomes"] == {"passed": 2, "failed": 2}
    assert summary["failed_tests"] == ["test_slow", "test_bad"]
    assert summary["ai_model_used"] is False
    assert (directory / "summary.json").exists()


def test_run_time_limit_stops_the_container(project, monkeypatch):
    calls = []

    def slow(command, **kwargs):
        calls.append(command)
        if command[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output="partial")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("apiguard.docker_run.subprocess.run", slow)
    _, summary = run_in_docker(config(), project["suite"], "runs")
    assert summary["timed_out"] is True
    assert calls[-1][:2] == ["docker", "kill"]


def test_needs_pytest_files_and_a_network(project, tmp_path):
    with pytest.raises(RunError, match="apiguard build"):
        run_in_docker(config(), tmp_path / "missing", "runs")
    settings = {**config(), "docker_run": {}}
    with pytest.raises(RunError, match="docker_run.network"):
        run_in_docker(settings, project["suite"], "runs")


def test_parse_junit_without_a_report(tmp_path):
    assert parse_junit(tmp_path / "none.xml") == {"total": 0, "outcomes": {}, "failed_tests": []}
