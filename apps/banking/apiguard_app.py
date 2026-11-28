"""Start the FastAPI Banking System for APIGuard.

- Turn off the rate limits. Login allows five requests each minute, so a test run would get
  HTTP 429 answers that depend on timing (NFR-01).
- Write one JSON log line for each request and login (FR-11), as for NexStock.
"""


def create_app():
    from apiguard_logging import RequestLog
    from app.core import limiter
    from app.core.config import setting
    from jose import jwt

    limiter.enabled = False
    from app.main import app

    def decode(token):
        return jwt.decode(
            token,
            setting.SECRET_KEY,
            algorithms=[setting.ALGORITHM],
            options={"verify_iss": False},
        )

    return RequestLog(app, decode, login_path="/api/login", user_field="username")
