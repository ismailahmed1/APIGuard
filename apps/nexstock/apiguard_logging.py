"""Write one JSON log line for each NexStock request and login, for the security monitor (FR-11).

The container starts NexStock through this module:

    uvicorn --factory apiguard_logging:create_app

Each line has "source": "apiguard", so the monitor can skip other output. The lines contain no
passwords and no tokens (NFR-04): the user and role come from the verified token, and a login line
gives only the email address or user name. Other apps can use RequestLog with their own login path,
login field and token decoder.
"""

import json
import sys
from datetime import UTC, datetime

LOGIN_PATH = "/api/auth/login"


class RequestLog:
    """ASGI middleware. `decode` returns the claims of a valid token, or raises an exception."""

    def __init__(self, app, decode, login_path=LOGIN_PATH, stream=None, user_field="email"):
        self.app = app
        self.decode = decode
        self.login_path = login_path
        self.user_field = user_field
        self.stream = stream or sys.stdout

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        login = scope["method"] == "POST" and scope["path"] == self.login_path
        body = bytearray()
        status = {"code": 500}  # An exception before the response is a server error.

        async def receive_body():
            message = await receive()
            if login and message["type"] == "http.request":
                body.extend(message.get("body", b""))
            return message

        async def send_status(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive_body if login else receive, send_status)
        finally:
            user, role = self._user(scope)
            event = {
                "source": "apiguard",
                "event": "request",
                "time": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "method": scope["method"],
                "path": scope["path"],
                "status": status["code"],
                "user": user,
                "role": role,
                "ip": (scope.get("client") or [None])[0],
            }
            self._write(event)
            if login:
                success = 200 <= status["code"] < 300
                self._write(
                    {
                        **event,
                        "event": "login_success" if success else "login_failure",
                        "user": _login_name(bytes(body), self.user_field),
                    }
                )

    def _user(self, scope):
        headers = dict(scope.get("headers") or [])
        value = headers.get(b"authorization", b"").decode("latin-1")
        scheme, _, token = value.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None, None
        try:
            claims = self.decode(token)
        except Exception:  # noqa: BLE001 - an invalid or expired token: log as anonymous.
            return None, None
        return _text(claims.get("sub")), _text(claims.get("role"))

    def _write(self, event):
        self.stream.write(json.dumps(event) + "\n")
        self.stream.flush()


def _login_name(body, field):
    try:
        value = json.loads(body).get(field)
    except (ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _text(value):
    return None if value is None else str(value)


def create_app():
    from app.core.security import decode_access_token
    from app.main import app

    return RequestLog(app, decode_access_token)
