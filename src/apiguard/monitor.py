"""Collect application logs and apply security rules to them (FR-11)."""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import yaml

DEFAULT_RULES = "configs/monitor/rules.yaml"
RULE_FIELDS = ("id", "name", "severity", "match", "threshold", "window_seconds")
JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
SECRET_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
MAX_ALERT_LINES = 20


class MonitorError(Exception):
    """A problem with the log command or the rules."""


def load_rules(path=DEFAULT_RULES):
    try:
        rules = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise MonitorError(f"cannot read the monitoring rules in {path}") from exc
    if not isinstance(rules, list):
        raise MonitorError("the monitoring rules must be a list")
    for rule in rules:
        missing = [f for f in RULE_FIELDS if not isinstance(rule, dict) or f not in rule]
        if missing:
            raise MonitorError(f"rule {rule.get('id', '?')} is missing '{missing[0]}'")
        if not isinstance(rule["match"], dict):
            raise MonitorError(f"rule {rule['id']}: 'match' must contain named conditions")
    return rules


def collect_logs(config, since, until):
    """Return the application log lines between two UTC times."""
    command = config.get("monitor", {}).get("logs_command")
    if not command:
        raise MonitorError(f"no 'monitor.logs_command' is configured for {config['name']}")
    # Docker log times have whole seconds; parse_events applies the exact limits.
    command = [*command, "--since", _stamp(since), "--until", _stamp(until + timedelta(seconds=1))]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=config["timeouts"]["run_seconds"],
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MonitorError(f"collecting the application logs failed: {exc}") from exc
    return completed.stdout.splitlines()


def parse_events(lines, since=None, until=None):
    """Read the JSON lines that the application writes for APIGuard into one event format."""
    events = []
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
            moment = datetime.fromisoformat(event["time"])
        except (ValueError, KeyError, TypeError):
            continue
        if not isinstance(event, dict) or event.get("source") != "apiguard":
            continue
        if (since and moment < since) or (until and moment > until):
            continue
        events.append({**event, "line": line[start:]})
    return sorted(events, key=lambda e: e["time"])


def apply_rules(events, rules):
    """Return each rule match: the rule, the group value and the events that caused it."""
    matches = []
    for rule in rules:
        groups = {}
        for event in events:
            if all(
                _meets(event.get(field), condition) for field, condition in rule["match"].items()
            ):
                key = event.get(rule.get("group_by")) if rule.get("group_by") else None
                groups.setdefault(key, []).append(event)
        for key, group in groups.items():
            window = []
            for event in group:
                moment = datetime.fromisoformat(event["time"])
                window = [
                    e
                    for e in window
                    if (moment - datetime.fromisoformat(e["time"])).total_seconds()
                    <= rule["window_seconds"]
                ]
                window.append(event)
                if len(window) >= rule["threshold"]:
                    matches.append({"rule": rule, "group": key, "events": window})
                    window = []  # Start a new count after each match.
    return matches


def _meets(value, condition):
    if isinstance(condition, list):
        return value in condition
    if isinstance(condition, dict):
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        return value >= condition.get("gte", value) and value <= condition.get("lte", value)
    return value == condition


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_alerts(config, matches):
    """Make one alert for each rule match (FR-12). Merge repeated matches of one rule and group.

    A match that starts within the rule's window after the previous match ends joins its alert.
    """
    alerts = []
    ordered = sorted(
        matches, key=lambda m: (m["rule"]["id"], str(m["group"]), m["events"][0]["time"])
    )
    for match in ordered:
        rule, events = match["rule"], match["events"]
        last = alerts[-1] if alerts else None
        if (
            last
            and last["rule"] == rule["id"]
            and last["group"] == match["group"]
            and _seconds(last["last_seen"], events[0]["time"]) <= rule["window_seconds"]
        ):
            last["matches"] += 1
            last["event_count"] += len(events)
            last["last_seen"] = events[-1]["time"]
            last["log_lines"] = (last["log_lines"] + [e["line"] for e in events])[:MAX_ALERT_LINES]
            continue
        alerts.append(
            {
                "rule": rule["id"],
                "name": rule["name"],
                "app": config["name"],
                "severity": rule["severity"],
                "time": events[0]["time"],
                "last_seen": events[-1]["time"],
                "group_by": rule.get("group_by"),
                "group": match["group"],
                "matches": 1,
                "event_count": len(events),
                "log_lines": [e["line"] for e in events][:MAX_ALERT_LINES],
            }
        )
    alerts.sort(key=lambda a: a["time"])
    secrets = _secrets(config)
    for alert in alerts:
        alert["log_lines"] = [_redact(text, secrets) for text in alert["log_lines"]]
    return alerts


def _seconds(earlier, later):
    return (datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds()


def _secrets(config):
    variables = list(SECRET_VARIABLES)
    for settings in config.get("auth", {}).get("roles", {}).values():
        variables.append(settings.get("password_env"))
    return {value for value in (os.environ.get(name or "") for name in variables) if value}


def _redact(text, secrets):
    """Remove passwords, keys and tokens from a log line (NFR-04)."""
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    return JWT.sub("[REDACTED-TOKEN]", text)


def monitor_run(config, since, until, directory):
    """Apply the rules to the logs of one run. Save the matches and the alerts with the run."""
    settings = config.get("monitor", {})
    rules = load_rules(settings.get("rules", DEFAULT_RULES))
    events = parse_events(collect_logs(config, since, until), since, until)
    matches = apply_rules(events, rules)
    alerts = make_alerts(config, matches)
    record = {
        "since": since.isoformat(timespec="seconds"),
        "until": until.isoformat(timespec="seconds"),
        "events": len(events),
        "matches": [
            {
                "rule": m["rule"]["id"],
                "name": m["rule"]["name"],
                "group": m["group"],
                "count": len(m["events"]),
                "first": m["events"][0]["time"],
                "last": m["events"][-1]["time"],
            }
            for m in matches
        ],
    }
    directory = Path(directory)
    (directory / "monitor.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    (directory / "alerts.json").write_text(json.dumps(alerts, indent=2) + "\n", encoding="utf-8")
    return record, alerts
