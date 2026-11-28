"""Send known normal and suspicious requests to NexStock, then check the monitoring rules.

Each suspicious step must trigger its rule. The normal step must trigger no rule.
Start NexStock and set the NexStock credentials in .env first. Run from the repository root:

    python scripts/make_security_events.py
"""

import os
import sys
import time
from datetime import UTC, datetime, timedelta

import httpx
from dotenv import load_dotenv

from apiguard.config import load_config
from apiguard.monitor import apply_rules, collect_logs, load_rules, parse_events

WRONG_PASSWORD = "not-the-password-0001"


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    return response.json()["data"]["access_token"] if response.status_code == 200 else None


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def normal(client, admin, manager):
    """Typical use: two logins and a few reads. No rule must match."""
    tokens = [login(client, *admin), login(client, *manager)]
    for token in tokens:
        for path in ("/api/products", "/api/categories"):
            client.get(path, headers=bearer(token))


def failed_logins(client, admin, manager):
    for _ in range(6):
        login(client, admin[0], WRONG_PASSWORD)


def no_token(client, admin, manager):
    for _ in range(12):
        client.get("/api/products")


def forbidden(client, admin, manager):
    token = login(client, *manager)
    for _ in range(4):
        client.delete("/api/categories/1", headers=bearer(token))


def server_errors(client, admin, manager):
    token = login(client, *admin)
    for _ in range(10):  # NexStock v1 answers 500 for every authenticated inventory request.
        client.get("/api/inventory", headers=bearer(token))


def flood(client, admin, manager):
    for _ in range(310):
        client.get("/")


# Each step and the rules that it must trigger.
STEPS = [
    (normal, set()),
    (failed_logins, {"MON-01"}),
    (no_token, {"MON-02"}),
    (forbidden, {"MON-03"}),
    (server_errors, {"MON-04"}),
    (flood, {"MON-05"}),
]


def main():
    load_dotenv(".env", override=False)
    config = load_config("configs/nexstock.yaml")
    rules = load_rules(config["monitor"]["rules"])
    admin = (os.environ["NEXSTOCK_ADMIN_EMAIL"], os.environ["NEXSTOCK_ADMIN_PASSWORD"])
    manager = (os.environ["NEXSTOCK_MANAGER_EMAIL"], os.environ["NEXSTOCK_MANAGER_PASSWORD"])

    spans = []
    # A fresh connection per request: NexStock closes the connection after a server error.
    limits = httpx.Limits(max_keepalive_connections=0)
    with httpx.Client(base_url=config["base_url"], timeout=10, limits=limits) as client:
        for step, expected in STEPS:
            start = datetime.now(UTC)
            step(client, admin, manager)
            time.sleep(1)  # Let the container write its last log line.
            spans.append((step.__name__, expected, start, datetime.now(UTC)))

    lines = collect_logs(config, spans[0][2] - timedelta(seconds=1), spans[-1][3])
    failures = 0
    for name, expected, start, end in spans:
        found = {m["rule"]["id"] for m in apply_rules(parse_events(lines, start, end), rules)}
        ok = found == expected
        failures += not ok
        expected_text = ", ".join(sorted(expected)) or "none"
        found_text = ", ".join(sorted(found)) or "none"
        print(
            f"{'PASS' if ok else 'FAIL'}  {name:14} expected {expected_text:8} found {found_text}"
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
