"""Manage APIGuard's disposable Task Management API stack."""

import argparse
import json
import os
import secrets
import subprocess
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv

from apiguard.openapi import load_spec, save_snapshot

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
ENV = ROOT / ".env"
BASE = "http://127.0.0.1:8012"
SUITE = REPO / "suites" / "tasks" / "smoke"


def compose(*args, capture=False):
    if not ENV.exists():
        raise SystemExit("Run manage.py start first.")
    # Keep other projects' database and JWT settings out of Compose interpolation.
    return subprocess.run(
        [
            "docker",
            "compose",
            "-p",
            "apiguard-tasks",
            "--env-file",
            str(ENV),
            "-f",
            str(ROOT / "upstream" / "docker-compose.yml"),
            "-f",
            str(ROOT / "compose.override.yaml"),
            *args,
        ],
        env={**os.environ, **dotenv_values(ENV)},
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def start():
    if not ENV.exists():
        with ENV.open("x", encoding="utf-8") as stream:
            stream.write(
                "POSTGRES_USER=taskapi\nPOSTGRES_DB=taskapi_test_db\n"
                f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
                f"JWT_SECRET_KEY={secrets.token_hex(32)}\n"
            )
    compose("up", "-d", "--build", "--wait", "--wait-timeout", "120", "api")


def snapshot():
    spec = load_spec(BASE + "/openapi.json", 10)
    if spec.document["info"]["title"] != "Task Management API" or (
        "get" not in spec.document["paths"].get("/api/v1/users/me", {})
    ):
        raise SystemExit("Port 8012 did not serve the expected task-management API.")
    digest = save_snapshot(spec, SUITE)
    (SUITE / "suite.json").write_text(
        json.dumps({"suite_id": "smoke", "spec_sha256": digest}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved Task Management smoke-suite specification {digest}")


def reset():
    load_dotenv(REPO / ".env", override=False)
    email = os.environ.get("TASKS_MEMBER_EMAIL")
    password = os.environ.get("TASKS_MEMBER_PASSWORD")
    if not email or not password:
        raise SystemExit("Set TASKS_MEMBER_EMAIL and TASKS_MEMBER_PASSWORD before running reset.")
    # Only the named tasks project owns these volumes. Recreate its migrated test
    # database and empty Redis together, including queued jobs and rate counters.
    compose("down", "--volumes")
    compose("up", "-d", "--wait", "--wait-timeout", "120", "api")
    response = httpx.post(
        BASE + "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": "Smoke Member",
            "username": "smoke_member",
        },
        timeout=15,
    )
    if response.status_code != 201:
        raise SystemExit(
            f"Could not seed the test member: registration returned {response.status_code}."
        )


def request_events(lines):
    for line in lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict) or event.get("event") != "request_completed":
            continue
        fields = ("method", "path", "status_code")
        if all(key in event for key in fields):
            yield {key: event[key] for key in fields}


def logs():
    output = compose("logs", "--no-color", "--no-log-prefix", "api", capture=True)
    rows = [
        row
        for row in request_events(output.stdout.splitlines())
        if row["method"] == "GET" and row["path"] == "/api/v1/users/me"
    ]
    for row in rows:
        print(json.dumps(row))
    if not {200, 401}.issubset({row["status_code"] for row in rows}):
        raise SystemExit("Expected profile reads with HTTP 200 and 401. Run the smoke suite first.")


def stop():
    compose("down")


if __name__ == "__main__":
    actions = {"start": start, "snapshot": snapshot, "reset": reset, "logs": logs, "stop": stop}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
