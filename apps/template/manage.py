"""Start, reset, and inspect APIGuard's local template application."""

import argparse
import secrets
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
BACKUP = "/var/lib/postgresql/apiguard-template-seed.dump"


def compose(*args, capture=False):
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "apiguard-template",
            "--env-file",
            str(ENV_FILE),
            "-f",
            str(ROOT / "upstream" / "compose.yml"),
            "-f",
            str(ROOT / "compose.override.yaml"),
            *args,
        ],
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def start():
    if not ENV_FILE.exists():
        ENV_FILE.write_text(
            "PROJECT_NAME=APIGuard Template\n"
            "FIRST_SUPERUSER=admin@example.com\n"
            f"FIRST_SUPERUSER_PASSWORD={secrets.token_hex(24)}\n"
            f"SECRET_KEY={secrets.token_hex(32)}\n"
            f"POSTGRES_PASSWORD={secrets.token_hex(24)}\n"
            "SMTP_HOST=\nEMAILS_FROM_EMAIL=\n",
            encoding="utf-8",
        )
    compose("up", "--build", "--detach", "--wait", "backend")
    # Save the initial database once. Later starts must preserve the original seed.
    compose(
        "exec",
        "-T",
        "db",
        "sh",
        "-ec",
        f"if [ ! -f {BACKUP} ]; then "
        f"pg_dump -U postgres -d app -Fc -f {BACKUP}.tmp && "
        f"mv {BACKUP}.tmp {BACKUP}; fi",
    )


def reset():
    compose(
        "exec",
        "-T",
        "db",
        "pg_restore",
        "-U",
        "postgres",
        "-d",
        "app",
        "--clean",
        "--if-exists",
        "--single-transaction",
        "--exit-on-error",
        BACKUP,
    )


def check_logs():
    result = compose("logs", "--no-color", "--since", "5m", "backend", capture=True)
    lines = (result.stdout + result.stderr).splitlines()
    matches = [
        line for line in lines if "GET /api/v1/utils/health-check/" in line and "200" in line
    ]
    if not matches:
        raise SystemExit("No successful health-check request found in the last five minutes.")
    print(matches[-1])


if __name__ == "__main__":
    actions = {"start": start, "reset": reset, "logs": check_logs}
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=actions)
    actions[parser.parse_args().action]()
