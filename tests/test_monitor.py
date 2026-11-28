import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from apiguard.monitor import (
    MonitorError,
    apply_rules,
    collect_logs,
    load_rules,
    make_alerts,
    monitor_run,
    parse_events,
)

START = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)
RULES = load_rules()


def line(seconds, event="request", status=200, ip="10.0.0.1", user=None, path="/api/products"):
    record = {
        "source": "apiguard",
        "event": event,
        "time": (START + timedelta(seconds=seconds)).isoformat(timespec="milliseconds"),
        "method": "GET",
        "path": path,
        "status": status,
        "user": user,
        "role": None,
        "ip": ip,
    }
    return "api-1  | " + json.dumps(record)


def found(lines):
    return sorted({m["rule"]["id"] for m in apply_rules(parse_events(lines), RULES)})


def test_parse_keeps_only_apiguard_events_in_the_time_span():
    lines = [
        "INFO:     Uvicorn running on http://0.0.0.0:8000",
        '{"source": "other", "time": "2026-11-28T12:00:00+00:00"}',
        "{not json",
        line(5),
        line(1),
        line(100),
    ]
    events = parse_events(lines, START, START + timedelta(seconds=60))
    assert [e["time"][17:19] for e in events] == ["01", "05"]
    assert events[0]["line"].startswith('{"source": "apiguard"')


@pytest.mark.parametrize(
    ("lines", "rules"),
    [
        ([line(i, "login_failure") for i in range(5)], ["MON-01"]),
        ([line(i, status=401) for i in range(10)], ["MON-02"]),
        ([line(i, status=403, user="2") for i in range(3)], ["MON-03"]),
        ([line(i, status=500) for i in range(10)], ["MON-04"]),
        ([line(i / 100) for i in range(300)], ["MON-05"]),
    ],
)
def test_each_suspicious_event_triggers_its_rule(lines, rules):
    assert found(lines) == rules


def test_normal_activity_triggers_no_rule():
    lines = [line(i, status=200, user="1") for i in range(50)]
    lines += [line(i, "login_success", user="a@n.test") for i in range(3)]
    lines += [line(i, "login_failure") for i in range(2)]
    assert found(lines) == []


def test_events_outside_the_window_do_not_count():
    assert found([line(i * 30, "login_failure") for i in range(5)]) == []


def test_groups_are_counted_separately():
    lines = [line(i, "login_failure", ip=f"10.0.0.{i % 2}") for i in range(8)]
    assert found(lines) == []


def test_rules_need_all_fields(tmp_path):
    path = tmp_path / "rules.yaml"
    path.write_text("- id: X\n  name: x\n")
    with pytest.raises(MonitorError, match="missing 'severity'"):
        load_rules(path)


def config():
    return {
        "name": "shop",
        "timeouts": {"run_seconds": 60},
        "monitor": {"logs_command": ["docker", "compose", "logs", "api"]},
    }


def test_collect_logs_uses_the_run_time_span(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="a\nb\n")

    monkeypatch.setattr("apiguard.monitor.subprocess.run", fake_run)
    assert collect_logs(config(), START, START + timedelta(seconds=30)) == ["a", "b"]
    assert calls[0][-4:] == ["--since", "2026-11-28T12:00:00Z", "--until", "2026-11-28T12:00:31Z"]


def test_collect_logs_reports_a_failed_command(monkeypatch):
    def fake_run(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("apiguard.monitor.subprocess.run", fake_run)
    with pytest.raises(MonitorError, match="collecting the application logs failed"):
        collect_logs(config(), START, START)


def test_monitor_run_saves_the_matches(monkeypatch, tmp_path):
    output = "\n".join(line(i, "login_failure") for i in range(5))
    monkeypatch.setattr(
        "apiguard.monitor.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=output),
    )
    record, _ = monitor_run(config(), START, START + timedelta(seconds=60), tmp_path)
    saved = json.loads((tmp_path / "monitor.json").read_text())
    assert saved == record
    assert record["events"] == 5
    assert [(m["rule"], m["group"], m["count"]) for m in record["matches"]] == [
        ("MON-01", "10.0.0.1", 5)
    ]


def alerts_for(lines, settings=None):
    return make_alerts(settings or config(), apply_rules(parse_events(lines), RULES))


def test_alert_has_all_fr12_fields():
    (alert,) = alerts_for([line(i, "login_failure") for i in range(5)])
    assert alert["rule"] == "MON-01"
    assert alert["name"] == "Repeated failed logins"
    assert alert["app"] == "shop"
    assert alert["severity"] == "high"
    assert alert["time"] == "2026-11-28T12:00:00.000+00:00"
    assert (alert["group_by"], alert["group"]) == ("ip", "10.0.0.1")
    assert len(alert["log_lines"]) == 5
    assert all(text.startswith('{"source": "apiguard"') for text in alert["log_lines"])


def test_repeated_matches_in_one_window_make_one_alert():
    (alert,) = alerts_for([line(i, "login_failure") for i in range(15)])
    assert (alert["matches"], alert["event_count"]) == (3, 15)
    assert alert["last_seen"] == "2026-11-28T12:00:14.000+00:00"


def test_matches_far_apart_make_separate_alerts():
    lines = [line(i, "login_failure") for i in range(5)]
    lines += [line(600 + i, "login_failure") for i in range(5)]
    assert [a["time"][11:19] for a in alerts_for(lines)] == ["12:00:00", "12:10:00"]


def test_alert_log_lines_contain_no_secrets(monkeypatch):
    monkeypatch.setenv("SHOP_ADMIN_PASSWORD", "Sup3r-Secret!")
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
    settings = {**config(), "auth": {"roles": {"admin": {"password_env": "SHOP_ADMIN_PASSWORD"}}}}
    lines = [line(i, "login_failure", user=f"Sup3r-Secret! {token}") for i in range(5)]
    text = json.dumps(alerts_for(lines, settings))
    assert "Sup3r-Secret!" not in text
    assert token not in text
    assert "[REDACTED]" in text
    assert "[REDACTED-TOKEN]" in text


def test_monitor_run_saves_the_alerts(monkeypatch, tmp_path):
    output = "\n".join(line(i, status=403, user="2") for i in range(3))
    monkeypatch.setattr(
        "apiguard.monitor.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, stdout=output),
    )
    _, alerts = monitor_run(config(), START, START + timedelta(seconds=60), tmp_path)
    assert json.loads((tmp_path / "alerts.json").read_text()) == alerts
    assert [a["rule"] for a in alerts] == ["MON-03"]
