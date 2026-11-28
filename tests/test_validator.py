import pytest
from shop_spec import SHOP, raw_test

from apiguard.operations import extract_operations
from apiguard.validator import validate_tests

OPERATIONS = extract_operations(SHOP)
ROLES = ["admin", "manager"]


def validate(*tests):
    return validate_tests(list(tests), OPERATIONS, ROLES)


def test_valid_test_is_converted_to_runner_format():
    valid, excluded = validate(raw_test())
    assert excluded == []
    assert valid == [
        {
            "id": "products-001",
            "type": "happy_path",
            "description": "Admin creates a product",
            "method": "POST",
            "path": "/api/products",
            "role": "admin",
            "path_params": {},
            "query_params": {},
            "body": {"name": "Lamp", "price": 9.5},
            "expected_status": 201,
            "checks": [],
            "steps": [],
        }
    ]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"path": "/api/orders"}, "no operation POST /api/orders in the specification"),
        ({"type": "load_test"}, "unsupported test type 'load_test'"),
        ({"role": "owner"}, "unknown role 'owner'"),
        ({"id": "has space"}, "test id may only contain"),
        ({"expected_status": "201"}, "field 'expected_status' must be a int"),
        ({"body_json": '{"name": '}, "request body is not valid JSON"),
        ({"body_json": ""}, "happy-path test is missing the required request body"),
        ({"expected_status": 400}, "expected status 400 is not documented"),
        ({"role": "anonymous"}, "operation requires a token; use a role or an authentication test"),
        (
            {"type": "authentication", "role": "admin", "expected_status": 401},
            "authentication tests must send no token and expect 401 or 403",
        ),
        (
            {"query_params": [{"name": "debug", "value": "1"}]},
            "unknown query parameter 'debug'",
        ),
        (
            {"path_params": [{"name": "product_id", "value": "1"}]},
            "unknown path parameter 'product_id'",
        ),
    ],
)
def test_invalid_tests_are_excluded_with_a_reason(changes, reason):
    valid, excluded = validate(raw_test(**changes))
    assert valid == []
    assert reason in excluded[0]["reason"]


def test_missing_field():
    test = raw_test()
    del test["body_json"]
    _, excluded = validate(test)
    assert excluded[0]["reason"] == "missing required field 'body_json'"


def test_path_parameters_and_unknown_resources():
    delete = raw_test(
        id="products-002",
        method="DELETE",
        path="/api/products/{product_id}",
        body_json="",
        expected_status=404,
        path_params=[{"name": "product_id", "value": "999"}],
    )
    valid, excluded = validate(delete, {**delete, "id": "products-003", "path_params": []})
    assert [t["path_params"] for t in valid] == [{"product_id": "999"}]
    assert excluded[0]["reason"] == "missing path parameter 'product_id'"


def test_authentication_test_rules():
    anonymous = raw_test(type="authentication", role="anonymous", expected_status=401)
    unprotected = raw_test(
        id="auth-001",
        type="authentication",
        role="anonymous",
        method="POST",
        path="/api/auth/login",
        body_json='{"email": "a@b.c", "password": "x"}',
        expected_status=401,
    )
    valid, excluded = validate(anonymous, unprotected)
    assert [t["id"] for t in valid] == ["products-001"]
    assert "does not require a token" in excluded[0]["reason"]


def test_unsupported_request_format():
    upload = raw_test(
        id="other-001", method="POST", path="/api/upload", body_json="{}", expected_status=200
    )
    _, excluded = validate(upload)
    assert excluded[0]["reason"] == (
        "unsupported request format (operation accepts: multipart/form-data)"
    )


def test_duplicate_ids_keep_the_first_test():
    valid, excluded = validate(raw_test(), raw_test(description="again"))
    assert len(valid) == 1
    assert excluded[0]["reason"] == "duplicate test id 'products-001'"


@pytest.mark.parametrize(
    ("body_json", "kept"),
    [
        ('{"name": "", "price": 1}', True),  # Below minLength.
        ('{"name": "Lamp", "price": 0}', True),  # Not above exclusiveMinimum.
        ('{"price": 1}', True),  # Missing a required field.
        ('{"name": "Lamp", "price": 1}', False),  # Nothing the specification forbids.
    ],
)
def test_rejection_tests_must_break_the_schema(body_json, kept):
    test = raw_test(type="boundary_value", body_json=body_json, expected_status=422)
    valid, excluded = validate(test)
    assert bool(valid) is kept
    if not kept:
        assert excluded[0]["reason"].startswith("expects 422, but every input matches")


def test_invalid_path_parameter_is_a_reason_for_422():
    delete = raw_test(
        type="schema_validation",
        method="DELETE",
        path="/api/products/{product_id}",
        body_json="",
        expected_status=422,
        path_params=[{"name": "product_id", "value": "abc"}],
    )
    valid, _ = validate(delete)
    assert len(valid) == 1


def test_success_tests_must_match_the_schema():
    valid, excluded = validate(raw_test(body_json='{"name": "", "price": 1}'))
    assert valid == []
    assert excluded[0]["reason"].startswith("expects 201, but an input breaks")


def test_repeat_markers_give_exact_lengths():
    test = raw_test(type="boundary_value", body_json='{"name": "x{{repeat:a:300}}y", "price": 1}')
    valid, _ = validate(test)
    assert valid[0]["body"]["name"] == "x" + "a" * 300 + "y"


def test_credential_placeholders_count_as_valid_values():
    login = raw_test(
        id="auth-001",
        path="/api/auth/login",
        role="anonymous",
        body_json='{"email": "{{admin.email}}", "password": "{{admin.password}}"}',
        expected_status=200,
    )
    valid, excluded = validate(login)
    assert excluded == []
    assert valid[0]["body"]["email"] == "{{admin.email}}"


def step(**changes):
    request = {
        "method": "DELETE",
        "path": "/api/products/{product_id}",
        "role": "admin",
        "path_params": [{"name": "product_id", "value": "{{r0.id}}"}],
        "query_params": [],
        "body_json": "",
        "expected_status": 200,
        "checks": [],
    }
    request.update(changes)
    return request


def test_workflow_steps_use_earlier_responses():
    workflow = raw_test(
        id="products-flow",
        type="stateful_workflow",
        checks=[{"path": "id", "equals_json": "7"}],
        steps=[step()],
    )
    (test,), excluded = validate(workflow)
    assert excluded == []
    assert test["checks"] == [{"path": "id", "equals": 7}]
    assert test["steps"][0]["path_params"] == {"product_id": "{{r0.id}}"}


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"type": "stateful_workflow", "steps": []}, "needs one or more steps"),
        ({"steps": [step()]}, "only stateful workflow tests can have steps"),
        (
            {
                "type": "stateful_workflow",
                "steps": [step(path_params=[{"name": "product_id", "value": "{{r1.id}}"}])],
            },
            "step 1: {{r1.id}} names a response that does not exist yet",
        ),
        (
            {"body_json": '{"name": "{{r0.name}}", "price": 1}'},
            "{{r0.name}} names a response that does not exist yet",
        ),
        ({"checks": [{"path": "data..id", "equals_json": "1"}]}, "is not valid"),
        ({"checks": [{"path": "id", "equals_json": "not json"}]}, "needs a JSON value"),
        (
            {
                "type": "schema_validation",
                "body_json": '{"name": ""}',
                "expected_status": 422,
                "checks": [{"path": "id", "equals_json": "1"}],
            },
            "checks need a success status",
        ),
        ({"type": "authorization", "role": "anonymous", "expected_status": 403}, "must use a role"),
        ({"type": "authorization", "role": "manager", "expected_status": 401}, "must expect 403"),
        ({"type": "fuzz", "expected_status": 201}, "must expect a 4xx rejection"),
    ],
)
def test_new_test_type_rules(changes, reason):
    _, excluded = validate(raw_test(**changes))
    assert reason in excluded[0]["reason"]


def test_authorization_and_fuzz_tests_are_kept():
    authorization = raw_test(id="a", type="authorization", role="manager", expected_status=403)
    fuzz = raw_test(id="f", type="fuzz", body_json='{"name": 5, "price": "x"}', expected_status=422)
    valid, excluded = validate(authorization, fuzz)
    assert excluded == []
    assert [t["type"] for t in valid] == ["authorization", "fuzz"]


def test_repeat_markers_are_expanded_in_checks():
    check = {"path": "name", "equals_json": '"{{repeat:a:5}}"'}
    (test,), _ = validate(raw_test(checks=[check]))
    assert test["checks"] == [{"path": "name", "equals": "aaaaa"}]
