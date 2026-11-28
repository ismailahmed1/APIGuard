"""Generate a test suite with the AI model as Pytest files (Method A)."""

import ast
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from apiguard.ai import LimitReached
from apiguard.builder import CONFTEST, collect
from apiguard.generator import (
    describe_operation,
    group_operations,
    group_prefix,
    select_operations,
)
from apiguard.openapi import save_snapshot
from apiguard.validator import ANONYMOUS

SYSTEM_PROMPT = """You are APIGuard's test writer. You write Pytest files for a FastAPI application \
from its OpenAPI operations. APIGuard saves your files and runs them later without you.

Each test function takes the shared `api` fixture. Do not import httpx or requests, and do not
define fixtures. The fixture gives these methods:

- api.check(method, path, role, expected_status, path_params=None, query_params=None, body=None,
  test_id="...", test_type="...") sends one request. It fails the test when the status code is not
  expected_status or the response does not match its documented schema. Use it for most tests.
- api.request(role, method, path, params=None, json=None) sends a request and returns an httpx
  response, for tests that use a value from one response in the next request. `path` is the real
  path, for example f"/api/products/{product_id}".

Rules:
- `path` in api.check is the path template from the specification; give its values in path_params.
  Write all parameter values as strings.
- `role` is one of the roles in the application context, or "anonymous" for no token.
- Each test runs on freshly reset seed data before its first change. Never depend on another test.
- Use real identifiers and values from the application context.
- Write credentials only as the placeholders {{role.email}} and {{role.password}}.
- Write happy-path tests for every operation, an authentication test (role "anonymous", expect 401)
  for every protected operation, and schema-validation and boundary-value tests (expect 422 outside
  a documented limit) where the operation has inputs with constraints.
- Start every test function name with the prefix that the request gives you.

Answer with one complete Python file."""

FILE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code"],
    "properties": {"code": {"type": "string"}},
}


def check_file(code):
    """Return the reason that a generated file cannot be saved, or None."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"syntax error on line {exc.lineno}: {exc.msg}"
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    if not tests:
        return "the file has no test functions"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [alias.name for alias in node.names]
            module = getattr(node, "module", None) or names[0]
            if module.split(".")[0] not in ("json", "re", "pytest"):
                return f"the file imports '{module}'; use only the api fixture"
    return None


def generate_pytest_suite(app_name, spec, operations, tags, ai, context, roles, suites_dir):
    """Generate, check and save Pytest files. Returns (suite directory, suite metadata)."""
    selected = select_operations(operations, tags)
    system = SYSTEM_PROMPT + "\n\nApplication context:\n" + context.strip()
    system += f"\n\nRoles: {', '.join(roles)} (or {ANONYMOUS})."
    files, rejected, stopped_reason = {}, [], None
    start = time.monotonic()
    for group, members in group_operations(selected, tags).items():
        prefix = "test_" + group_prefix(group).replace("-", "_")
        prompt = (
            f"Write the Pytest file for these {group} operations. Start every test function "
            f"name with '{prefix}'.\n\n"
            + json.dumps([describe_operation(op) for op in members], indent=1)
        )
        try:
            answer = ai.generate_json(system, prompt, FILE_SCHEMA)
        except LimitReached as exc:
            stopped_reason = str(exc)
            break
        name = "test_" + re.sub(r"\W+", "_", group.lower()).strip("_") + ".py"
        code = answer.get("code", "")
        reason = check_file(code)
        if reason:
            rejected.append({"file": name, "reason": reason, "code": code})
        else:
            files[name] = code
    seconds = time.monotonic() - start

    suite_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    directory = Path(suites_dir) / app_name / suite_id
    digest = save_snapshot(spec, directory)
    pytest_dir = directory / "pytest"
    pytest_dir.mkdir(parents=True, exist_ok=True)
    (pytest_dir / "conftest.py").write_text(CONFTEST, encoding="utf-8")
    for name, code in files.items():
        (pytest_dir / name).write_text(code, encoding="utf-8")
    collected = collect(pytest_dir) if files else {"files_collected": 0, "tests_collected": 0}
    metadata = {
        "suite_id": suite_id,
        "app": app_name,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generation_method": "pytest-direct",
        "model": ai.model,
        "effort": ai.effort,
        "tags": list(tags),
        "operations": [f"{op.method} {op.path}" for op in selected],
        "counts": {
            "files_generated": len(files) + len(rejected),
            "files_saved": len(files),
            "files_rejected": len(rejected),
            "files_that_run": collected["files_collected"],
            "tests_collected": collected["tests_collected"],
        },
        "generation_seconds": round(seconds, 1),
        "ai_usage": ai.usage.as_dict(ai.model),
        "spec_sha256": digest,
        "stopped_reason": stopped_reason,
    }
    (directory / "rejected.json").write_text(json.dumps(rejected, indent=2) + "\n", "utf-8")
    (directory / "suite.json").write_text(json.dumps(metadata, indent=2) + "\n", "utf-8")
    return directory, metadata
