import asyncio
import io
import json
import runpy
from pathlib import Path

import httpx

RequestLog = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "apps/nexstock/apiguard_logging.py")
)["RequestLog"]
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI3In0.c2lnbmF0dXJl"
PASSWORD = "admin-Secret-1"


async def nexstock(scope, receive, send):
    """A small stand-in for NexStock: login checks the password, other paths answer 200."""
    status = 200
    if scope["path"] == "/api/auth/login":
        body = json.loads((await receive())["body"])
        status = 200 if body["password"] == PASSWORD else 401
    elif scope["path"] == "/crash":
        raise RuntimeError("crash")
    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


def decode(token):
    if token != TOKEN:
        raise ValueError("invalid token")
    return {"sub": 7, "role": "Admin", "exp": 0}


def requests(*calls):
    stream = io.StringIO()
    app = RequestLog(nexstock, decode, stream=stream)

    async def send_all():
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://nexstock") as client:
            for method, path, kwargs in calls:
                await client.request(method, path, **kwargs)

    asyncio.run(send_all())
    return stream.getvalue(), [json.loads(line) for line in stream.getvalue().splitlines()]


def test_each_request_is_logged_with_user_and_role():
    _, events = requests(
        ("GET", "/api/products", {"headers": {"Authorization": f"Bearer {TOKEN}"}}),
        ("GET", "/api/products", {}),
        ("GET", "/api/products", {"headers": {"Authorization": "Bearer forged"}}),
    )
    assert [e["event"] for e in events] == ["request"] * 3
    first = events[0]
    assert {k: first[k] for k in ("source", "method", "path", "status", "user", "role")} == {
        "source": "apiguard",
        "method": "GET",
        "path": "/api/products",
        "status": 200,
        "user": "7",
        "role": "Admin",
    }
    assert first["ip"] == "127.0.0.1"
    assert first["time"].endswith("+00:00")
    assert (events[1]["user"], events[2]["user"]) == (None, None)


def test_login_success_and_failure_are_logged_without_secrets():
    text, events = requests(
        ("POST", "/api/auth/login", {"json": {"email": "a@n.test", "password": PASSWORD}}),
        ("POST", "/api/auth/login", {"json": {"email": "a@n.test", "password": "wrong-pass"}}),
        ("GET", "/api/auth/me", {"headers": {"Authorization": f"Bearer {TOKEN}"}}),
    )
    logins = [e for e in events if e["event"].startswith("login")]
    assert [(e["event"], e["status"], e["user"]) for e in logins] == [
        ("login_success", 200, "a@n.test"),
        ("login_failure", 401, "a@n.test"),
    ]
    for secret in (PASSWORD, "wrong-pass", TOKEN):
        assert secret not in text


def test_unhandled_error_is_logged_as_500():
    _, events = requests(("GET", "/crash", {}))
    assert events[0]["status"] == 500
