"""Run a saved Pytest suite in a container on the app's Docker network (FR-06, NFR-05)."""

import json
import os
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

from apiguard.runner import RunError, reset_app

IMAGE = "apiguard-runner:local"
DOCKERFILE = "docker/runner/Dockerfile"


def run_in_docker(config, suite_dir, runs_dir, label=None):
    """Reset the app, run the suite's Pytest files in the runner container and save a summary."""
    settings = config.get("docker_run")
    if not settings or not settings.get("network"):
        raise RunError(f"no 'docker_run.network' is configured for {config['name']}")
    pytest_dir = Path(suite_dir) / "pytest"
    if not (pytest_dir / "conftest.py").exists():
        raise RunError(f"{suite_dir} has no Pytest files; run 'apiguard build' first")

    started = datetime.now(UTC)
    run_id = "docker-" + started.strftime("%Y%m%d-%H%M%S")
    directory = Path(runs_dir) / config["name"] / run_id
    directory.mkdir(parents=True, exist_ok=True)

    _docker(["build", "--quiet", "--tag", IMAGE, "--file", DOCKERFILE, "."], config)
    reset_app(config)  # Every run starts from the same seed data (FR-08).

    name = f"apiguard-run-{uuid.uuid4().hex[:8]}"
    variables = ["APIGUARD_IN_DOCKER=1", "PYTHONDONTWRITEBYTECODE=1"]
    variables += [f"{key}={value}" for key, value in settings.get("environment", {}).items()]
    command = ["docker", "run", "--rm", "--name", name, "--network", settings["network"]]
    # The project is read-only; only the run directory is writable. The container does not read
    # .env and gets no AI key (FR-06).
    command += ["--volume", f"{Path.cwd()}:/work:ro", "--workdir", "/work"]
    command += ["--volume", f"{directory.resolve()}:/results"]
    if Path(".env").exists():  # Hide the file that holds the AI key.
        empty = directory / "empty.env"
        empty.write_text("", encoding="utf-8")
        command += ["--volume", f"{empty.resolve()}:/work/.env:ro"]
    for variable in variables:
        command += ["--env", variable]
    # Pass credentials by name only, so that the values never appear in a command line.
    for role in config["auth"].get("roles", {}).values():
        for key in ("email_env", "password_env"):
            if role.get(key) and os.environ.get(role[key]):
                command += ["--env", role[key]]
    command += [IMAGE, "python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    command += ["--junitxml=/results/junit.xml", pytest_dir.as_posix()]

    start = time.monotonic()
    timed_out = False
    try:
        # NFR-03: the run time limit stops the container. Each request has its own limit.
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,  # Pytest exits nonzero when a test fails.
            timeout=config["timeouts"]["run_seconds"],
        )
        output = completed.stdout + completed.stderr
    except subprocess.TimeoutExpired as exc:
        subprocess.run(["docker", "kill", name], capture_output=True, check=False)
        timed_out, completed = True, None
        output = (exc.stdout or b"").decode() if isinstance(exc.stdout, bytes) else exc.stdout or ""
    except OSError as exc:
        raise RunError(f"could not start Docker: {exc}") from exc
    seconds = round(time.monotonic() - start, 2)
    (directory / "output.txt").write_text(output, encoding="utf-8")

    summary = {
        "run_id": run_id,
        "app": config["name"],
        "label": label,
        "suite": Path(suite_dir).name,
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": seconds,
        "timed_out": timed_out,
        "exit_code": None if completed is None else completed.returncode,
        "ai_model_used": False,
        **parse_junit(directory / "junit.xml"),
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    return directory, summary


def parse_junit(path):
    """Count the outcomes in a Pytest JUnit report, and list the failed tests."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {"total": 0, "outcomes": {}, "failed_tests": []}
    outcomes, failed = {}, []
    for case in root.iter("testcase"):
        if case.find("failure") is not None:
            outcome = "failed"
            failed.append(case.get("name"))
        elif case.find("error") is not None:
            outcome = "error"
            failed.append(case.get("name"))
        elif case.find("skipped") is not None:
            outcome = "skipped"
        else:
            outcome = "passed"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return {"total": sum(outcomes.values()), "outcomes": outcomes, "failed_tests": failed}


def _docker(arguments, config):
    try:
        subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RunError(f"building the runner image failed: {exc}") from exc
