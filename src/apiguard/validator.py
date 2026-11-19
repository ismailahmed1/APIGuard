"""Check generated test definitions against the specification before they are saved (FR-05)."""

import json
import re

from jsonschema import Draft202012Validator

TEST_TYPES = ("happy_path", "schema_validation", "authentication", "boundary_value")
MUTATING_METHODS = ("POST", "PUT", "PATCH", "DELETE")
ANONYMOUS = "anonymous"
FIELDS = {
    "id": str,
    "type": str,
    "description": str,
    "method": str,
    "path": str,
    "role": str,
    "path_params": list,
    "query_params": list,
    "body_json": str,
    "expected_status": int,
}


class InvalidTest(Exception):
    """The reason that a generated test cannot be saved."""


def validate_tests(raw_tests, operations, roles):
    """Return (valid tests in runner format, excluded tests with reasons)."""
    by_key = {(operation.method, operation.path): operation for operation in operations}
    valid, excluded, seen = [], [], set()
    for raw in raw_tests:
        try:
            test = _validate(raw, by_key, roles)
            if test["id"] in seen:
                raise InvalidTest(f"duplicate test id '{test['id']}'")
            seen.add(test["id"])
            valid.append(test)
        except InvalidTest as exc:
            excluded.append({"test": raw, "reason": str(exc)})
    return valid, excluded


def _validate(raw, by_key, roles):
    if not isinstance(raw, dict):
        raise InvalidTest("test is not an object")
    for field, kind in FIELDS.items():
        if field not in raw:
            raise InvalidTest(f"missing required field '{field}'")
        if not isinstance(raw[field], kind) or (kind is int and isinstance(raw[field], bool)):
            raise InvalidTest(f"field '{field}' must be a {kind.__name__}")

    if not re.fullmatch(r"[A-Za-z0-9_.-]+", raw["id"]):
        raise InvalidTest("test id may only contain letters, digits, '.', '_' and '-'")
    if raw["type"] not in TEST_TYPES:
        raise InvalidTest(f"unsupported test type '{raw['type']}'")
    method = raw["method"].upper()
    operation = by_key.get((method, raw["path"]))
    if operation is None:
        raise InvalidTest(f"no operation {method} {raw['path']} in the specification")
    if raw["role"] != ANONYMOUS and raw["role"] not in roles:
        raise InvalidTest(f"unknown role '{raw['role']}'")

    path_params = _pairs(raw["path_params"], "path_params")
    query_params = _pairs(raw["query_params"], "query_params")
    declared = {p.location: set() for p in operation.parameters}
    for parameter in operation.parameters:
        declared[parameter.location].add(parameter.name)
    expected_path = declared.get("path", set())
    if set(path_params) != expected_path:
        missing = sorted(expected_path - set(path_params))
        unknown = sorted(set(path_params) - expected_path)
        raise InvalidTest(
            f"missing path parameter '{missing[0]}'"
            if missing
            else f"unknown path parameter '{unknown[0]}'"
        )
    unknown_query = sorted(set(query_params) - declared.get("query", set()))
    if unknown_query:
        raise InvalidTest(f"unknown query parameter '{unknown_query[0]}'")

    body = _body(raw["body_json"], operation, raw["type"])

    status = raw["expected_status"]
    if raw["type"] == "authentication":
        if not operation.requires_auth:
            raise InvalidTest("authentication test for an operation that does not require a token")
        if raw["role"] != ANONYMOUS or status not in (401, 403):
            raise InvalidTest("authentication tests must send no token and expect 401 or 403")
    else:
        if operation.requires_auth and raw["role"] == ANONYMOUS:
            raise InvalidTest("operation requires a token; use a role or an authentication test")
        documented = str(status) in operation.responses or "default" in operation.responses
        # FastAPI rarely documents 404, but a missing resource is a normal expected result.
        if not documented and not (status == 404 and expected_path):
            raise InvalidTest(f"expected status {status} is not documented for this operation")
        # The expected result must agree with the documented schema. This catches miscounted
        # values, such as a "256-character" string with 250 characters.
        rejection = raw["type"] in ("schema_validation", "boundary_value") and status == 422
        success = raw["type"] in ("happy_path", "boundary_value") and 200 <= status < 300
        if rejection or success:
            matches = _inputs_match_schema(operation, path_params, query_params, body)
            if rejection and matches:
                raise InvalidTest(
                    "expects 422, but every input matches the documented schema "
                    "(check the values against the limits)"
                )
            if success and not matches:
                raise InvalidTest(
                    f"expects {status}, but an input breaks the documented schema "
                    "(check the values against the limits)"
                )

    return {
        "id": raw["id"],
        "type": raw["type"],
        "description": raw["description"],
        "method": method,
        "path": raw["path"],
        "role": raw["role"],
        "path_params": path_params,
        "query_params": query_params,
        "body": body,
        "expected_status": status,
    }


def _pairs(items, field):
    result = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str):
            raise InvalidTest(f"each entry in '{field}' needs a name and a value")
        if not isinstance(item.get("value"), str) or not item["value"]:
            raise InvalidTest(f"'{field}' entry '{item['name']}' needs a nonempty value")
        result[item["name"]] = item["value"]
    return result


def _body(body_json, operation, test_type):
    """Return the parsed JSON body, or None when the test sends no body."""
    if not body_json.strip():
        if operation.request_body and operation.request_body.required and test_type == "happy_path":
            raise InvalidTest("happy-path test is missing the required request body")
        return None
    if operation.request_body is None:
        raise InvalidTest("operation does not accept a request body")
    if "application/json" not in operation.request_body.content:
        formats = ", ".join(operation.request_body.content) or "none"
        raise InvalidTest(f"unsupported request format (operation accepts: {formats})")
    try:
        return _expand(json.loads(body_json))
    except json.JSONDecodeError as exc:
        raise InvalidTest(f"request body is not valid JSON: {exc.msg}") from exc


REPEAT = re.compile(r"\{\{repeat:(.):(\d{1,5})\}\}")
PLACEHOLDER = re.compile(r"\{\{[a-z_]+\.(email|password)\}\}")
SAMPLE = {"email": "user@example.com", "password": "Sample-Password-1"}


def _expand(value):
    """Replace {{repeat:X:N}} markers: the model miscounts long strings that it types out."""
    if isinstance(value, str):
        return REPEAT.sub(lambda m: m.group(1) * int(m.group(2)), value)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def _sample(value):
    """Credential placeholders are filled at run time; check them as typical values."""
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: SAMPLE[m.group(1)], value)
    if isinstance(value, list):
        return [_sample(item) for item in value]
    if isinstance(value, dict):
        return {key: _sample(item) for key, item in value.items()}
    return value


def _matches(schema, value):
    validator = Draft202012Validator(
        schema or {}, format_checker=Draft202012Validator.FORMAT_CHECKER
    )
    return validator.is_valid(value)


def _parameter_value(text):
    """Parameter values arrive as text; read '3' as a number, as the API would."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _inputs_match_schema(operation, path_params, query_params, body):
    """True when the test sends no input that the specification forbids."""
    values = {"path": path_params, "query": query_params}
    for parameter in operation.parameters:
        given = values.get(parameter.location, {})
        if parameter.name not in given:
            if parameter.required and parameter.location in values:
                return False
            continue
        if not _matches(parameter.schema, _parameter_value(given[parameter.name])):
            return False
    if operation.request_body is None:
        return True
    if body is None:
        return not operation.request_body.required
    return _matches(operation.request_body.content.get("application/json"), _sample(body))
