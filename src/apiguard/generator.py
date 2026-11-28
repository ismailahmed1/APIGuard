"""Generate a test suite with the AI model as structured test definitions (Method B)."""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from apiguard.ai import LimitReached
from apiguard.coverage import coverage, missing_cells
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
- `checks` compare values in a success response with expected values. `path` uses the field names
  of the documented response schema, with [N] for a list index and [*] for every list element, for
  example "data.name" or "data[*].category_id". `equals_json` is the expected value as JSON, for
  example "\\"Electronics\\"" or "2". Add checks wherever the application context tells you the
  correct value. Use an empty list when a test has no checks.
- `steps` are used only by stateful_workflow tests; use an empty list for other tests.

Test types:
- happy_path: a valid request by a permitted role; expect the documented success status. Check the
  values that the application context gives, and check that filters and query parameters work.
- schema_validation: a request body or parameter with a missing required field, a wrong type or an
  invalid value; expect 422.
- authentication: a request without a token to an operation that requires one; role "anonymous",
  expect 401.
- authorization: a request by a logged-in role that the operation does not allow (see
  `allowed_roles`); expect 403.
- boundary_value: values at or just past a documented limit (minimum length, maximum length,
  greater than zero); expect success inside the limit and 422 outside it.
- fuzz: unusual input that a robust API rejects without a crash, such as very long strings,
  unicode, negative or huge numbers, nulls, or wrong JSON types; expect a documented 4xx status.
- stateful_workflow: the main request changes data, then `steps` read the data back or change it
  again and check the result. A step can use a value from an earlier response: {{r0.data.id}} is
  data.id of the main request's response, {{r1.data.id}} of the first step's response. Write the
  marker as the whole value to keep its type. For example: create a product, read it with
  {{r0.data.id}} and check its name; or delete a product and expect 404 when you read it again.

Write one happy_path test for every operation, one authentication test for every protected
operation, one authorization test for every operation with `allowed_roles`, schema_validation, fuzz
and boundary_value tests where the operation has inputs or constraints, and one stateful_workflow
test for every protected operation that changes data. Give each test a short description of what it
checks. Start every test id with the prefix that the request gives you."""

PAIRS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["name", "value"],
        "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
    },
}

CHECKS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "equals_json"],
        "properties": {"path": {"type": "string"}, "equals_json": {"type": "string"}},
    },
}

REQUEST_FIELDS = {
    "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
    "path": {"type": "string"},
    "role": {"type": "string"},
    "path_params": PAIRS_SCHEMA,
    "query_params": PAIRS_SCHEMA,
    "body_json": {"type": "string"},
    "expected_status": {"type": "integer"},
    "checks": CHECKS_SCHEMA,
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
    "checks": CHECKS_SCHEMA,
    "steps": {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": list(REQUEST_FIELDS),
            "properties": REQUEST_FIELDS,
        },
    },
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


def group_operations(selected, tags):
    """Group the operations by their first selected tag; each group is one model request."""
    groups = {}
    for operation in selected:
        group = next((t for t in operation.tags if not tags or t.lower() in _lower(tags)), "other")
        groups.setdefault(group, []).append(operation)
    return groups


def group_prefix(group):
    return re.sub(r"[^a-z0-9]+", "-", group.lower()).strip("-") + "-"


def describe_operation(operation, permissions=None):
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
        # The success response schemas give the field names for checks and {{rN...}} markers.
        "success_responses": {
            status: content.get("application/json")
            for status, content in operation.responses.items()
            if status.startswith("2")
            and isinstance(content, dict)
            and content.get("application/json")
        },
        **(
            {"allowed_roles": permissions[f"{operation.method} {operation.path}"]}
            if permissions and f"{operation.method} {operation.path}" in permissions
            else {}
        ),
    }


def generate_suite(
    app_name, spec, operations, tags, ai, context, roles, suites_dir, permissions=None
):
    """Generate, validate and save a suite. Returns (suite directory, suite metadata).

    A second request for each group asks for the applicable test types that have no valid test
    after the first request.
    """
    permissions = permissions or {}
    selected = select_operations(operations, tags)
    groups = group_operations(selected, tags)

    system = SYSTEM_PROMPT + "\n\nApplication context:\n" + context.strip()
    system += f"\n\nRoles: {', '.join(roles)} (or {ANONYMOUS})."
    raw_tests, stopped_reason = [], None
    start = time.monotonic()
    for group, members in groups.items():
        prefix = group_prefix(group)
        described = json.dumps([describe_operation(op, permissions) for op in members], indent=1)
        prompt = (
            f"Write tests for these {group} operations. Start every test id with '{prefix}'.\n\n"
            + described
        )
        try:
            answer = ai.generate_json(system, prompt, TEST_SCHEMA)
            group_tests = list(answer.get("tests", []))
            raw_tests.extend(group_tests)
            valid, excluded = validate_tests(group_tests, members, roles)
            missing = missing_cells(coverage(valid, members, permissions, roles))
            if missing:
                reasons = [
                    f"- {(item['test'] or {}).get('id', '?')}: {item['reason']}"
                    for item in excluded
                    if isinstance(item["test"], dict)
                ][:20]
                prompt = (
                    f"Some applicable tests for these {group} operations are missing or invalid. "
                    f"Write tests only for these operation and test type pairs. Start every test "
                    f"id with '{prefix}gap-'.\n\n"
                    + "\n".join(f"- {key}: {test_type}" for key, test_type in missing)
                    + (
                        "\n\nAPIGuard rejected these tests:\n" + "\n".join(reasons)
                        if reasons
                        else ""
                    )
                    + "\n\nOperations:\n"
                    + described
                )
                answer = ai.generate_json(system, prompt, TEST_SCHEMA)
                raw_tests.extend(answer.get("tests", []))
        except LimitReached as exc:
            stopped_reason = str(exc)
            break
    seconds = time.monotonic() - start

    valid, excluded = validate_tests(raw_tests, selected, roles)
    missing = missing_cells(coverage(valid, selected, permissions, roles))
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
        "coverage_missing": [f"{key}: {test_type}" for key, test_type in missing],
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
