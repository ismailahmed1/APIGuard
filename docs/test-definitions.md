# Test-definition schema (Method B)

The AI model writes test definitions, not code. APIGuard validates each definition (FR-05), saves the valid ones in `tests.json`, and runs them without the AI model (FR-06). `apiguard build <app>` also converts them to Pytest files.

## Model output

The model answers with JSON that matches `TEST_SCHEMA` in `src/apiguard/generator.py`. Each test has all of these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | A unique ID. Letters, digits, `.`, `_` and `-` only. It starts with the operation group, such as `products-`. |
| `type` | string | `happy_path`, `schema_validation`, `authentication` or `boundary_value`. |
| `description` | string | What the test checks. |
| `method` | string | `GET`, `POST`, `PUT`, `PATCH` or `DELETE`. |
| `path` | string | The path template from the specification, such as `/api/products/{product_id}`. |
| `role` | string | A role from the app configuration, or `anonymous` for no token. |
| `path_params` | list of `{name, value}` | One entry for each path parameter. Values are strings. |
| `query_params` | list of `{name, value}` | Only parameters that the operation declares. Values are strings. |
| `body_json` | string | The request body as a JSON string, or `""` for no body. |
| `expected_status` | integer | A status code that the operation documents. `404` is also accepted for a path with parameters. |

Two markers are expanded or filled later:

- `{{repeat:X:N}}` in a string becomes the character X, N times. Use it for exact string lengths.
- `{{role.email}}` and `{{role.password}}` are filled with credentials from the environment at run time. The saved files never contain the credentials.

## Validation rules

APIGuard excludes a test and records the reason in `excluded.json` when:

- A field is missing or has the wrong type, or the ID is not unique.
- The operation, a parameter or the role is unknown.
- `body_json` is not valid JSON, or the operation does not accept a JSON body.
- An authentication test sends a token, or expects a status other than 401 or 403.
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
