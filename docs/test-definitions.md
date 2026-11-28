# Test-definition schema (Method B)

The AI model writes test definitions, not code. APIGuard validates each definition (FR-05), saves the valid ones in `tests.json`, and runs them without the AI model (FR-06). `apiguard build <app>` also converts them to Pytest files.

## Model output

The model answers with JSON that matches `TEST_SCHEMA` in `src/apiguard/generator.py`. Each test has all of these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | A unique ID. Letters, digits, `.`, `_` and `-` only. It starts with the operation group, such as `products-`. |
| `type` | string | `happy_path`, `schema_validation`, `authentication`, `authorization`, `boundary_value`, `fuzz` or `stateful_workflow`. |
| `description` | string | What the test checks. |
| `method` | string | `GET`, `POST`, `PUT`, `PATCH` or `DELETE`. |
| `path` | string | The path template from the specification, such as `/api/products/{product_id}`. |
| `role` | string | A role from the app configuration, or `anonymous` for no token. |
| `path_params` | list of `{name, value}` | One entry for each path parameter. Values are strings. |
| `query_params` | list of `{name, value}` | Only parameters that the operation declares. Values are strings. |
| `body_json` | string | The request body as a JSON string, or `""` for no body. |
| `expected_status` | integer | A status code that the operation documents. `404` is also accepted for a path with parameters. |
| `checks` | list of `{path, equals_json}` | Values to compare in a success response. `path` is like `data.name`, `data[0].id` or `data[*].category_id` (every element). `equals_json` is the expected value as JSON. |
| `steps` | list of requests | Only for `stateful_workflow`. Each step has `method`, `path`, `role`, `path_params`, `query_params`, `body_json`, `expected_status` and `checks`. |

Two markers are expanded or filled later:

- `{{repeat:X:N}}` in a string becomes the character X, N times. Use it for exact string lengths.
- `{{role.email}}` and `{{role.password}}` are filled with credentials from the environment at run time. The saved files never contain the credentials.
- `{{rN.path}}` in a workflow step is a value from an earlier response of the same test. `r0` is the main request, `r1` the first step. As a whole value, it keeps its type, so an ID stays a number.

## Validation rules

APIGuard excludes a test and records the reason in `excluded.json` when:

- A field is missing or has the wrong type, or the ID is not unique.
- The operation, a parameter or the role is unknown.
- `body_json` is not valid JSON, or the operation does not accept a JSON body.
- An authentication test sends a token, or expects a status other than 401 or 403.
- An authorization test sends no token, or expects a status other than 403.
- A fuzz test expects a status that is not 4xx.
- A workflow test has no steps, another test type has steps, or a `{{rN...}}` marker names a later response.
- A check path is not valid, or a check is on a test that does not expect success.
- The expected status does not agree with the schema. For example, a test expects 422 but every input is valid.

## Saved format

`tests.json` keeps the runner format. The pairs become objects and `body_json` becomes `body`:

```json
{
  "id": "products-get-happy",
  "type": "happy_path",
  "description": "Admin reads an existing product",
  "method": "GET",
  "path": "/api/products/{product_id}",
  "role": "admin",
  "path_params": {"product_id": "1"},
  "query_params": {},
  "body": null,
  "expected_status": 200
}
```

A login test with placeholders and an authentication test:

```json
[
  {
    "id": "auth-login-happy",
    "type": "happy_path",
    "description": "Admin logs in with valid credentials",
    "method": "POST",
    "path": "/api/auth/login",
    "role": "anonymous",
    "path_params": {},
    "query_params": {},
    "body": {"email": "{{admin.email}}", "password": "{{admin.password}}"},
    "expected_status": 200
  },
  {
    "id": "products-list-no-token",
    "type": "authentication",
    "description": "The product list rejects a request without a token",
    "method": "GET",
    "path": "/api/products",
    "role": "anonymous",
    "path_params": {},
    "query_params": {},
    "body": null,
    "expected_status": 401
  }
]
```

## Pytest files

`apiguard build <app> [--suite ID]` writes `pytest/` in the suite directory:

- `conftest.py` gives the shared `api` fixture from `apiguard.pytest_support`. It reads the base URL, the role tokens and the time limits from the app configuration.
- One `test_<group>.py` file for each operation group. Each test calls `api.check(...)`, which checks the status code and the response schema.

Run them with `python -m pytest suites/<app>/<suite-id>/pytest`. Set `APIGUARD_BASE_URL` to use another app address, or `APIGUARD_NO_RESET=1` to keep the current data. The build records `pytest_build` in `suite.json`: the files and tests written and collected.

## Coverage

`apiguard coverage <app> [--suite ID]` shows a table of operations and test types. A cell gives the number of tests, `-` when the type does not apply, or `MISSING`. A type applies as follows:

- `happy_path`: every operation.
- `authentication`: operations that need a token.
- `authorization`: operations in `generation.permissions` that some configured roles may not call.
- `schema_validation` and `fuzz`: operations with parameters or a request body.
- `boundary_value`: operations with a documented limit, such as `maxLength` or `minimum`.
- `stateful_workflow`: operations that need a token and change data.

After the first request for each operation group, `apiguard generate` sends one more request for the applicable cells that still have no valid test. `suite.json` lists the cells that are still empty in `coverage_missing`.
