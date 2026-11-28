"""Run a saved suite against the application without the AI model (FR-06)."""

import base64
import binascii
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
from apiguard.validator import ANONYMOUS, RESPONSE_REF, changes_data

PLACEHOLDER = re.compile(r"\{\{(\w+)\.(email|password)\}\}")
JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
EXCERPT_CHARS = 300
# Log in again when a token expires within this time.
REFRESH_MARGIN_SECONDS = 30
# Keys that APIGuard reads from the environment, which must never appear in its output.
SECRET_VARIABLES = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")


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


def run_suite(config, metadata, tests, operations, runs_dir, label=None, reset=True, ai=None):
    """Run the tests and save the results. Returns (run directory, summary, results)."""
    timeouts = config["timeouts"]
    by_key = {(op.method, op.path): op for op in operations}
    session = _Session(config)
    deadline = time.monotonic() + timeouts["run_seconds"]
    started = datetime.now(UTC)
    start = time.monotonic()

    # Reads run first. Each change-making test after the first starts from fresh seed data,
    # so every test sees the same starting data in every run (FR-08, NFR-01).
    ordered = sorted(tests, key=changes_data)
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
            if reset and dirty and changes_data(test):
                session.reset()
                resets += 1
            results.append(classifier.apply(_run_test(test, by_key, session)))
            dirty = dirty or changes_data(test)

    # Secrets are removed before any result is sent to the AI model (FR-10, NFR-04).
    redacted = [session.redact(result) for result in results]
    ai_note = classifier.classify_with_ai(redacted, ai) if ai else None
    summary = _summary(redacted)
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
        "ai_model_used": bool(ai and ai.usage.calls),
        "ai_usage": ai.usage.as_dict(ai.model) if ai else None,
        "ai_note": ai_note,
        **summary,
    }
    (directory / "results.json").write_text(json.dumps(redacted, indent=2) + "\n", "utf-8")
    (directory / "run.json").write_text(json.dumps(run, indent=2) + "\n", "utf-8")
    (Path(runs_dir) / config["name"] / "LATEST").write_text(run_id + "\n", "utf-8")
    return directory, run, redacted


def _run_test(test, by_key, session):
    """Run the request of a test, then each workflow step. The first problem ends the test."""
    started = time.monotonic()
    request = _saved_request(test)
    requests = [test, *test.get("steps", [])]
    responses, actual = [], None
    for number, step in enumerate(requests):
        prefix = f"step {number}: " if number else ""
        try:
            response, problem = _send_step(step, by_key, session, responses)
        except _TestProblem as exc:
            return _result(test, "error", exc.category, prefix + str(exc), request, started, actual)
        actual = {"status": response.status_code, "body_excerpt": response.text[:EXCERPT_CHARS]}
        if number:
            actual["step"] = number
        if problem:
            return _result(test, "failed", None, prefix + problem, request, started, actual)
        responses.append(_json(response))
    return _result(test, "passed", None, None, request, started, actual)


def _saved_request(test):
    request = {
        "method": test["method"],
        "path": test["path"],
        "path_params": test["path_params"],
        "query": test["query_params"],
        "body": test["body"],  # Saved with placeholders, never with real credentials.
    }
    if test.get("steps"):
        request["steps"] = [
            {key: step[key] for key in ("method", "path", "path_params", "query_params", "body")}
            for step in test["steps"]
        ]
    return request


def _send_step(step, by_key, session, responses):
    """Send one request. Returns (response, problem); problem is None when the step passes."""
    operation = by_key.get((step["method"], step["path"]))
    if operation is None:
        raise _TestProblem("generated_test_error", "operation is no longer in the specification")
    headers = {}
    if step["role"] != ANONYMOUS:
        headers["Authorization"] = f"Bearer {session.token(step['role'])}"
    path = step["path"]
    for name, value in step["path_params"].items():
        value = str(_resolve(value, responses))
        path = path.replace("{" + name + "}", quote(session.fill(value), safe=""))
    query = {
        name: str(_resolve(session.fill(value), responses))
        for name, value in step["query_params"].items()
    }
    body = _resolve(session.fill(step["body"]), responses)
    response = session.send(step["method"], path, query, body, headers)

    expected = step["expected_status"]
    if response.status_code != expected:
        if response.status_code >= 500:
            return response, f"server error {response.status_code} (expected {expected})"
        return response, f"unexpected status {response.status_code} (expected {expected})"
    problem = _schema_problem(operation, response)
    if problem:
        return response, problem
    for check in step.get("checks", []):
        problem = _check_problem(_json(response), check)
        if problem:
            return response, problem
    return response, None


def _json(response):
    try:
        return response.json()
    except ValueError:
        return None


def _resolve(value, responses):
    """Replace {{rN.path}} with a value from an earlier response of the same test."""
    if isinstance(value, str):
        whole = RESPONSE_REF.fullmatch(value)
        if whole:  # Keep the type, so that an ID stays a number in a request body.
            return _lookup(responses, whole)
        return RESPONSE_REF.sub(lambda m: str(_lookup(responses, m)), value)
    if isinstance(value, list):
        return [_resolve(item, responses) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, responses) for key, item in value.items()}
    return value


def _lookup(responses, match):
    number = int(match.group(1))
    values = _values(responses[number] if number < len(responses) else None, match.group(2))
    if len(values) != 1:
        raise _TestProblem(
            "generated_test_error", f"{match.group(0)} is not a single value in the response"
        )
    return values[0]


def _values(document, path):
    """Values at a response path such as data.items[0].id or data[*].category_id."""
    values = [document]
    for part in re.findall(r"\[\*\]|\[\d+\]|[^.\[\]]+", path):
        found = []
        for value in values:
            if part == "[*]" and isinstance(value, list):
                found.extend(value)
            elif part.startswith("[") and isinstance(value, list):
                index = int(part[1:-1])
                found.extend(value[index : index + 1])
            elif isinstance(value, dict) and part in value:
                found.append(value[part])
        values = found
    return values


def _check_problem(document, check):
    values = _values(document, check["path"])
    if not values:
        return f"response value at {check['path']} is missing"
    for value in values:
        if value != check["equals"]:
            shown = json.dumps(value)[:60]
            return (
                f"response value at {check['path']} is {shown} "
                f"(expected {json.dumps(check['equals'])[:60]})"
            )
    return None


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
        self.expiry = {}
        self.secrets = set()
        # Register known secrets now, so that output is clean even if a test leaks one.
        variables = list(SECRET_VARIABLES)
        for settings in self.auth.get("roles", {}).values():
            variables.append(settings.get("password_env"))
        self.secrets.update(v for v in (os.environ.get(n or "") for n in variables) if v)

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
        expiry = self.expiry.get(role)
        if expiry is not None and time.time() >= expiry - REFRESH_MARGIN_SECONDS:
            del self.tokens[role]  # The token has expired, or soon will; log in again.
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
            self.expiry[role] = _expiry(token)
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


def _expiry(token):
    """Return the 'exp' time of a JWT, or None when the token has no readable expiry."""
    try:
        payload = token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, binascii.Error):
        return None
    expiry = claims.get("exp") if isinstance(claims, dict) else None
    if isinstance(expiry, bool) or not isinstance(expiry, (int, float)):
        return None
    return expiry
