"""Run APIGuard test definitions from Pytest files (FR-04, FR-06).

Generated Pytest files use the shared `api` fixture in their conftest.py. The fixture gives the
base URL, the tokens of each role and the time limits from the app configuration. It needs no AI
model.
"""

import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

from apiguard.config import load_config
from apiguard.openapi import load_spec
from apiguard.operations import extract_operations
from apiguard.runner import _run_test, _Session
from apiguard.validator import MUTATING_METHODS


class Api:
    """Send one test request and check its status code and response schema."""

    def __init__(self, config, operations, reset=True):
        self.session = _Session(config)
        self.by_key = {(op.method, op.path): op for op in operations}
        self.reset = reset
        self.dirty = False
        self.client = httpx.Client(
            base_url=config["base_url"],
            timeout=config["timeouts"]["request_seconds"],
            limits=httpx.Limits(max_keepalive_connections=0),
        )
        self.session.client = self.client

    def check(
        self,
        method,
        path,
        role,
        expected_status,
        path_params=None,
        query_params=None,
        body=None,
        test_id="test",
        test_type="happy_path",
    ):
        # Each change-making test after the first starts from fresh seed data (FR-08).
        if self.reset and self.dirty and method in MUTATING_METHODS:
            self.session.reset()
        self.dirty = self.dirty or method in MUTATING_METHODS
        test = {
            "id": test_id,
            "type": test_type,
            "description": test_id,
            "method": method,
            "path": path,
            "role": role,
            "path_params": path_params or {},
            "query_params": query_params or {},
            "body": body,
            "expected_status": expected_status,
        }
        result = self.session.redact(_run_test(test, self.by_key, self.session))
        if result["outcome"] != "passed":
            pytest.fail(f"{result['category']}: {result['detail']}", pytrace=False)
        return result

    def close(self):
        self.client.close()


def open_api(suite_dir):
    """Make the Api for a suite directory. Environment variables can change the settings:

    APIGUARD_CONFIG: the app configuration file (default: configs/<app>.yaml).
    APIGUARD_BASE_URL: the app address, for example on a Docker network.
    APIGUARD_NO_RESET=1: do not reset the test data.
    APIGUARD_IN_DOCKER=1: use the `docker_run` address and reset command of the configuration.
    """
    # Credentials come from the environment or an untracked .env file, as for the CLI. In the
    # runner container, they come only from the environment, and the AI key is not available.
    if os.environ.get("APIGUARD_IN_DOCKER") != "1":
        load_dotenv(Path(".env"), override=False)
    suite_dir = Path(suite_dir)
    app = suite_dir.parent.name
    config = load_config(os.environ.get("APIGUARD_CONFIG", f"configs/{app}.yaml"))
    if os.environ.get("APIGUARD_IN_DOCKER") == "1":
        # Inside the runner container, use the addresses on the app's Docker network.
        settings = config.get("docker_run", {})
        config["base_url"] = settings.get("base_url", config["base_url"])
        config["reset"] = {"command": settings.get("reset_command")}
    if os.environ.get("APIGUARD_BASE_URL"):
        config["base_url"] = os.environ["APIGUARD_BASE_URL"]
    snapshot = load_spec(str(suite_dir / "openapi.yaml"), config["timeouts"]["request_seconds"])
    reset = os.environ.get("APIGUARD_NO_RESET") != "1"
    api = Api(config, extract_operations(snapshot.document), reset=reset)
    if reset:
        api.session.reset()
    return api
