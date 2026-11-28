"""Run a saved suite against the application without the AI model (FR-06)."""

import json
import os
import re
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

from apiguard import classifier
from apiguard.validator import ANONYMOUS, MUTATING_METHODS

PLACEHOLDER = re.compile(r"\{\{(\w+)\.(email|password)\}\}")
JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
EXCERPT_CHARS = 300


class RunError(Exception):
    """A problem that stops the whole run, such as a missing suite or a failed reset."""


class _TestProblem(Exception):
    """A problem with one test that is not an API failure."""

    def __init__(self, category, detail):
        super().__init__(detail)
        self.category = category


def load_suite(suites_dir, app_name, suite_id=None):
    root = Path(suites_dir) / app_name
    if suite_id is None:
        try:
            suite_id = (root / "LATEST").read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RunError(f"no saved suite for {app_name}; run 'apiguard generate' first") from exc
    directory = root / suite_id
    try:
        metadata = json.loads((directory / "suite.json").read_text(encoding="utf-8"))
        tests = json.loads((directory / "tests.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RunError(f"cannot read suite {suite_id} in {root}") from exc
    return directory, metadata, tests


def reset_app(config):
    """Restore the application's seed data with the configured reset command."""
    _Session(config).reset()


def get_token(config, role):
    """Log in as a configured role, for tools such as the baseline that need a token."""
    session = _Session(config)
    with httpx.Client(
        base_url=config["base_url"], timeout=config["timeouts"]["request_seconds"]
    ) as client:
        session.client = client
        try:
            return session.token(role)
        except _TestProblem as exc:
            raise RunError(str(exc)) from exc


def run_suite(config, metadata, tests, operations, runs_dir, label=None, reset=True):
    """Run the tests and save the results. Returns (run directory, summary, results)."""
    timeouts = config["timeouts"]
    by_key = {(op.method, op.path): op for op in operations}
    session = _Session(config)
    deadline = time.monotonic() + timeouts["run_seconds"]
    started = datetime.now(UTC)
    start = time.monotonic()

    # Reads run first. Each change-making test after the first starts from fresh seed data,
    # so every test sees the same starting data in every run (FR-08, NFR-01).
    ordered = sorted(tests, key=lambda test: test["method"] in MUTATING_METHODS)
    resets, dirty, results = 0, False, []
    if reset:
        session.reset()
        resets += 1

    # A fresh connection per request: after a server error, FastAPI closes the connection, and
    # reusing it would turn the next test's result into a false infrastructure error.
    with httpx.Client(
        base_url=config["base_url"],
        timeout=timeouts["request_seconds"],
        limits=httpx.Limits(max_keepalive_connections=0),
    ) as client:
        session.client = client
        for test in ordered:
            if time.monotonic() > deadline:
                result = _result(test, "not_run", "infrastructure_error", "run time limit")
                results.append(classifier.apply(result))
                continue
            if reset and dirty and test["method"] in MUTATING_METHODS:
                session.reset()
                resets += 1
            results.append(classifier.apply(_run_test(test, by_key, session)))
            dirty = dirty or test["method"] in MUTATING_METHODS

    summary = _summary(results)
    run_id = started.strftime("%Y%m%d-%H%M%S")
    directory = Path(runs_dir) / config["name"] / run_id
    directory.mkdir(parents=True, exist_ok=True)
    run = {
        "run_id": run_id,
        "app": config["name"],
        "app_commit": config.get("app_commit"),
        "label": label,
        "suite_id": metadata["suite_id"],
        "spec_sha256": metadata.get("spec_sha256"),
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": round(time.monotonic() - start, 2),
        "requests": session.requests,
        "resets": resets,
        "ai_model_used": False,
        **summary,
    }
    redacted = [session.redact(result) for result in results]
    (directory / "results.json").write_text(json.dumps(redacted, indent=2) + "\n", "utf-8")
    (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", "utf-8")
    (Path(runs_dir) / config["name"] / "LATEST").write_text(run_id + "\n", "utf-8")
    return directory, run, redacted


def _run_test(test, by_key, session):
    operation = by_key.get((test["method"], test["path"]))
    started = time.monotonic()
    request = {
        "method": test["method"],
        "path": test["path"],
        "path_params": test["path_params"],
        "query": test["query_params"],
        "body": test["body"],  # Saved with placeholders, never with real credentials.
    }
    try:
        if operation is None:
            raise _TestProblem(
                "generated_test_error", "operation is no longer in the specification"
            )
        headers = {}
        if test["role"] != ANONYMOUS:
            headers["Authorization"] = f"Bearer {session.token(test['role'])}"
        path = test["path"]
        for name, value in test["path_params"].items():
            path = path.replace("{" + name + "}", quote(session.fill(value), safe=""))
        query = {name: session.fill(value) for name, value in test["query_params"].items()}
        body = session.fill(test["body"])
        response = session.send(test["method"], path, query, body, headers)
    except _TestProblem as exc:
        return _result(test, "error", exc.category, str(exc), request, started)

    actual = {"status": response.status_code, "body_excerpt": response.text[:EXCERPT_CHARS]}
    expected = test["expected_status"]
    if response.status_code == expected:
        problem = _schema_problem(operation, response)
        if problem:
            return _result(test, "failed", None, problem, request, started, actual)
        return _result(test, "passed", None, None, request, started, actual)
    if response.status_code >= 500:
        detail = f"server error {response.status_code} (expected {expected})"
    else:
        detail = f"unexpected status {response.status_code} (expected {expected})"
    return _result(test, "failed", None, detail, request, started, actual)


def _schema_problem(operation, response):
    """Check a JSON response against its documented schema."""
    schema = operation.responses.get(str(response.status_code), {}).get("application/json")
    if not schema:
        return None
    try:
        document = response.json()
    except ValueError:
        return "response is not JSON although the specification documents a JSON body"
    try:
        errors = sorted(Draft202012Validator(schema).iter_errors(document), key=str)
    except (SchemaError, Unresolvable):
        return None  # The schema cannot be checked here; the status check still applies.
    if errors:
        location = "/".join(str(part) for part in errors[0].absolute_path) or "(root)"
        return f"response does not match its schema at {location}: {errors[0].message}"
    return None


def _result(test, outcome, category, detail, request=None, started=None, actual=None):
    duration = round((time.monotonic() - started) * 1000) if started else 0
    return {
        "id": test["id"],
        "type": test["type"],
        "description": test["description"],
        "operation": f"{test['method']} {test['path']}",
        "role": test["role"],
        "request": request,
        "expected": {"status": test["expected_status"]},
        "actual": actual,
        "outcome": outcome,
        "category": category,
        "detail": detail,
        "duration_ms": duration,
    }


def _summary(results):
    outcomes, categories = {}, {}
    for result in results:
        outcomes[result["outcome"]] = outcomes.get(result["outcome"], 0) + 1
        if result["category"]:
            categories[result["category"]] = categories.get(result["category"], 0) + 1
    return {"total": len(results), "outcomes": outcomes, "categories": categories}


class _Session:
    """Credentials, tokens, resets and requests for one run."""

    def __init__(self, config):
        self.config = config
        self.auth = config["auth"]
        self.client = None
        self.requests = 0
        self.tokens = {}
        self.secrets = set()

    def reset(self):
        command = self.config["reset"].get("command")
        if not command:
            return
        if command[0] == "python":
            command = [sys.executable, *command[1:]]
        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=self.config["timeouts"]["run_seconds"],
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RunError(f"resetting the application data failed: {exc}") from exc

    def credential(self, role, field):
        settings = self.auth.get("roles", {}).get(role)
        if settings is None:
            raise _TestProblem("configuration_error", f"role '{role}' is not configured")
        variable = settings.get(f"{field}_env")
        value = os.environ.get(variable or "")
        if not value:
            raise _TestProblem("configuration_error", f"environment variable {variable} is not set")
        self.secrets.add(value)
        return value

    def fill(self, value):
        """Replace {{role.email}} and {{role.password}} placeholders with real credentials."""
        if isinstance(value, str):
            return PLACEHOLDER.sub(lambda m: self.credential(m.group(1), m.group(2)), value)
        if isinstance(value, list):
            return [self.fill(item) for item in value]
        if isinstance(value, dict):
            return {key: self.fill(item) for key, item in value.items()}
        return value

    def token(self, role):
        if role not in self.tokens:
            field = self.auth.get("username_field", "email")
            body = {
                field: self.credential(role, "email"),
                "password": self.credential(role, "password"),
            }
            response = self.send("POST", self.auth["login_path"], {}, body, {})
            token = response.json() if response.status_code == 200 else None
            for part in self.auth.get("token_path", "access_token").split("."):
                token = token.get(part) if isinstance(token, dict) else None
            if not isinstance(token, str):
                raise _TestProblem(
                    "configuration_error",
                    f"login as '{role}' failed with HTTP {response.status_code}",
                )
            self.tokens[role] = token
            self.secrets.add(token)
        return self.tokens[role]

    def send(self, method, path, query, body, headers):
        self.requests += 1
        try:
            return self.client.request(method, path, params=query, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise _TestProblem("infrastructure_error", "request timed out") from exc
        except httpx.RequestError as exc:
            raise _TestProblem("infrastructure_error", "could not reach the application") from exc

    def redact(self, value):
        """Remove passwords and tokens from anything saved or shown (NFR-04)."""
        if isinstance(value, str):
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return JWT.sub("[REDACTED-TOKEN]", value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {key: self.redact(item) for key, item in value.items()}
        return value
