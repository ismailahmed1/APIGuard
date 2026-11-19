"""Generate a test suite with the AI model as structured test definitions (Method B)."""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from apiguard.ai import LimitReached
from apiguard.openapi import save_snapshot
from apiguard.validator import ANONYMOUS, TEST_TYPES, validate_tests

SYSTEM_PROMPT = """You are APIGuard's test designer. You write API test definitions for a FastAPI \
application from its OpenAPI operations. APIGuard validates your definitions, saves them and runs \
them later without you, so every test must be complete and self-contained.

Rules:
- Each test runs alone on freshly reset seed data. Never depend on another test's changes.
- Use only the operations, parameters and fields that you are given.
- Use real identifiers and values from the application context, so that happy-path requests can
  succeed.
- `expected_status` must be a status code documented for the operation. You may also expect 404 for
  a path that names a resource that does not exist.
- Write values as strings in `path_params` and `query_params`. Write the request body as a JSON
  string in `body_json`, or use an empty string when the test sends no body.
- `role` is one of the roles in the application context, or "anonymous" for no token.
- For a string of an exact length, write {{repeat:X:N}} inside the string, for example
  "{{repeat:a:255}}" for 255 letters a. Never type long strings out; APIGuard expands the marker.

Test types:
- happy_path: a valid request by a permitted role; expect the documented success status.
- schema_validation: a request body or parameter with a missing required field, a wrong type or an
  invalid value; expect 422.
- authentication: a request without a token to an operation that requires one; role "anonymous",
  expect 401.
- boundary_value: values at or just past a documented limit (minimum length, maximum length,
  greater than zero); expect success inside the limit and 422 outside it.

Write one happy_path test for every operation, one authentication test for every protected
operation, and schema_validation and boundary_value tests where the operation has inputs with
constraints. Give each test a short description of what it checks. Start every test id with the
prefix that the request gives you."""

PAIRS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "value"],
        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
    },
}

TEST_FIELDS = {
    "id": {"type": "string"},
    "type": {"type": "string", "enum": list(TEST_TYPES)},
    "description": {"type": "string"},
    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
    "path": {"type": "string"},
    "role": {"type": "string"},
    "path_params": PAIRS_SCHEMA,
    "query_params": PAIRS_SCHEMA,
    "body_json": {"type": "string"},
    "expected_status": {"type": "integer"},
}

TEST_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tests"],
    "properties": {
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(TEST_FIELDS),
                "properties": TEST_FIELDS,
            },
        }
    },
}


def select_operations(operations, tags):
    """Return the operations with any of the tags, in spec order; no tags selects every one."""
    if not tags:
        return list(operations)
    wanted = {tag.lower() for tag in tags}
    return [op for op in operations if wanted & {tag.lower() for tag in op.tags}]


def describe_operation(operation):
    """A compact description of an operation for the prompt."""
    body = None
    if operation.request_body:
        body = {
            "required": operation.request_body.required,
            "content": operation.request_body.content,
        }
    return {
        "method": operation.method,
        "path": operation.path,
        "summary": operation.summary,
        "requires_token": operation.requires_auth,
        "parameters": [
            {"name": p.name, "in": p.location, "required": p.required, "schema": p.schema}
            for p in operation.parameters
        ],
        "request_body": body,
        "documented_statuses": list(operation.responses),
    }


def generate_suite(app_name, spec, operations, tags, ai, context, roles, suites_dir):
    """Generate, validate and save a suite. Returns (suite directory, suite metadata)."""
    selected = select_operations(operations, tags)
    groups = {}
    for operation in selected:
        group = next((t for t in operation.tags if not tags or t.lower() in _lower(tags)), "other")
        groups.setdefault(group, []).append(operation)

    system = SYSTEM_PROMPT + "\n\nApplication context:\n" + context.strip()
    system += f"\n\nRoles: {', '.join(roles)} (or {ANONYMOUS})."
    raw_tests, stopped_reason = [], None
    start = time.monotonic()
    for group, group_operations in groups.items():
        prefix = re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-") + "-"
        prompt = (
            f"Write tests for these {group} operations. Start every test id with '{prefix}'.\n\n"
            + json.dumps([describe_operation(op) for op in group_operations], indent=1)
        )
        try:
            answer = ai.generate_json(system, prompt, TEST_SCHEMA)
        except LimitReached as exc:
            stopped_reason = str(exc)
            break
        raw_tests.extend(answer.get("tests", []))
    seconds = time.monotonic() - start

    valid, excluded = validate_tests(raw_tests, selected, roles)
    suite_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    directory = Path(suites_dir) / app_name / suite_id
    digest = save_snapshot(spec, directory)
    metadata = {
        "suite_id": suite_id,
        "app": app_name,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "generation_method": "structured-definitions",
        "model": ai.model,
        "effort": ai.effort,
        "tags": list(tags),
        "operations": [f"{op.method} {op.path}" for op in selected],
        "counts": {"generated": len(raw_tests), "valid": len(valid), "excluded": len(excluded)},
        "generation_seconds": round(seconds, 1),
        "ai_usage": ai.usage.as_dict(ai.model),
        "spec_sha256": digest,
        "stopped_reason": stopped_reason,
    }
    _write_json(directory / "tests.json", valid)
    _write_json(directory / "excluded.json", excluded)
    _write_json(directory / "suite.json", metadata)
    (Path(suites_dir) / app_name / "LATEST").write_text(suite_id + "\n", encoding="utf-8")
    return directory, metadata


def _lower(tags):
    return {tag.lower() for tag in tags}


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
