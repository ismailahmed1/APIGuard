"""Collect application logs and apply security rules to them (FR-11)."""

import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import yaml

DEFAULT_RULES = "configs/monitor/rules.yaml"
RULE_FIELDS = ("id", "name", "severity", "match", "threshold", "window_seconds")


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


def monitor_run(config, since, until, directory):
    """Apply the rules to the logs of one run, and save the matches in monitor.json."""
    settings = config.get("monitor", {})
    rules = load_rules(settings.get("rules", DEFAULT_RULES))
    events = parse_events(collect_logs(config, since, until), since, until)
    matches = apply_rules(events, rules)
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
    path = Path(directory) / "monitor.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record, matches
