import subprocess
import sys

import httpx
import pytest
import yaml

from apiguard.cli import main


def test_version_command():
    result = subprocess.run(
        [sys.executable, "-m", "apiguard.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"


@pytest.fixture
def configured_project(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()

    config = {
        "name": "nexstock",
        "base_url": "http://127.0.0.1:8000",
        "spec_location": "http://127.0.0.1:8000/openapi.json",
        "timeouts": {
            "request_seconds": 10,
            "run_seconds": 120,
        },
        "auth": {},
        "reset": {},
    }

    (config_dir / "nexstock.yaml").write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return config


def test_check_success(configured_project, monkeypatch, capsys):
    def fake_get(url, **kwargs):
        assert url == "http://127.0.0.1:8000/openapi.json"
        assert kwargs["timeout"] == 10
        return httpx.Response(
            200,
            json={
                "openapi": "3.1.0",
                "info": {"title": "Test API", "version": "1.0.0"},
                "paths": {},
            },
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("apiguard.cli.httpx.get", fake_get)

    assert main(["check", "nexstock"]) == 0
    assert "OK: nexstock is reachable" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("error_class", "message"),
    [
        (httpx.ConnectError, "could not reach"),
        (httpx.ReadTimeout, "timed out"),
    ],
)
def test_connection_errors(configured_project, monkeypatch, capsys, error_class, message):
    def fake_get(url, **kwargs):
        raise error_class(
            "Simulated network failure",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("apiguard.cli.httpx.get", fake_get)

    assert main(["check", "nexstock"]) == 1
    assert message in capsys.readouterr().err


def test_http_error(configured_project, monkeypatch, capsys):
    def fake_get(url, **kwargs):
        return httpx.Response(
            503,
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr("apiguard.cli.httpx.get", fake_get)

    assert main(["check", "nexstock"]) == 1
    assert "HTTP 503" in capsys.readouterr().err


def test_missing_config_stops_before_request(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid configuration should prevent network requests.")

    monkeypatch.setattr("apiguard.cli.httpx.get", unexpected_request)

    assert main(["check", "nexstock"]) == 2
    assert "Configuration error" in capsys.readouterr().err


def test_invalid_remote_spec(configured_project, monkeypatch, capsys):
    def fake_get(url, **kwargs):
        return httpx.Response(200, json={"openapi": "3.1.0"}, request=httpx.Request("GET", url))

    monkeypatch.setattr("apiguard.openapi.httpx.get", fake_get)
    assert main(["check", "nexstock"]) == 2
    assert "Specification error" in capsys.readouterr().err


@pytest.mark.parametrize("status", [200, 503])
def test_local_spec_checks_base_url(configured_project, tmp_path, monkeypatch, capsys, status):
    configured_project["spec_location"] = "openapi.yaml"
    (tmp_path / "configs" / "nexstock.yaml").write_text(
        yaml.safe_dump(configured_project), encoding="utf-8"
    )
    (tmp_path / "openapi.yaml").write_text(
        yaml.safe_dump(
            {
                "openapi": "3.1.0",
                "info": {"title": "Local API", "version": "1.0.0"},
                "paths": {},
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        assert kwargs["timeout"] == 10
        return httpx.Response(status, request=httpx.Request("GET", url))

    monkeypatch.setattr("apiguard.openapi.httpx.get", fake_get)
    assert main(["check", "nexstock"]) == (0 if status == 200 else 1)
    assert calls == [configured_project["base_url"]]
    output = capsys.readouterr()
    assert ("specification is valid" in output.out) if status == 200 else ("HTTP 503" in output.err)


def test_missing_local_spec_prevents_network(configured_project, tmp_path, monkeypatch, capsys):
    configured_project["spec_location"] = "missing.yaml"
    (tmp_path / "configs" / "nexstock.yaml").write_text(
        yaml.safe_dump(configured_project), encoding="utf-8"
    )

    def unexpected_request(*args, **kwargs):
        pytest.fail("Invalid local specs should stop before connectivity checks.")

    monkeypatch.setattr("apiguard.openapi.httpx.get", unexpected_request)
    assert main(["check", "nexstock"]) == 2
    assert "Cannot read specification" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["generate", "run", "report"])
def test_placeholder_commands(command, capsys):
    assert main([command, "nexstock"]) == 2
    assert "not implemented" in capsys.readouterr().err


def test_invalid_app_name(capsys):
    assert main(["check", "../outside"]) == 2
    assert "invalid application name" in capsys.readouterr().err
