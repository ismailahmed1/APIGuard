import json
import runpy
from pathlib import Path

events = runpy.run_path(str(Path(__file__).resolve().parents[1] / "apps/tasks/manage.py"))[
    "request_events"
]


def test_task_request_events():
    record = {
        "event": "request_completed",
        "method": "GET",
        "path": "/api/v1/users/me",
        "status_code": 401,
        "duration_ms": 2,
        "request_id": "sample",
    }
    lines = [
        "server started",
        "null",
        '{"event":"request_completed"}',
        json.dumps({**record, "event": "security_event"}),
        json.dumps(record),
    ]
    assert list(events(lines)) == [
        {"method": "GET", "path": "/api/v1/users/me", "status_code": 401}
    ]
