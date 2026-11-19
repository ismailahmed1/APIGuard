# APIGuard
AI-assisted API testing and security-monitoring platform.

## Project Overview

APIGuard is a Carleton University SYSC 4907 capstone project.

The platform uses AI to generate automated API tests from OpenAPI specifications, execute reusable tests, classify failures, and monitor application logs for suspicious activity.

## Initial Testing Application

Our first testing application is [NexStock](https://github.com/heetdadhania/NexStock), an open-source warehouse management system built with FastAPI.

## Current Implementation

APIGuard currently supports:

- Loading application configuration from YAML.
- Validating required settings, HTTP URLs, and positive timeouts.
- Checking connectivity to the configured application or specification URL.
- Reporting configuration and connection errors with meaningful exit codes.
- Summarizing every operation in the specification with `apiguard spec`.
- Generating test suites with Claude, validating them and saving them with `apiguard generate`.

The `run` and `report` commands are placeholders and are not implemented yet. The `check` command loads and validates self-contained OpenAPI 3.0, 3.1 and 3.2 documents from JSON/YAML files or HTTP/HTTPS URLs.

## Local Setup — Windows PowerShell

Prerequisites:

- Python 3.11
- Git

Run the following commands from the repository root, which contains `pyproject.toml`:

```powershell
py -3.11 --version
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

If `.venv` already exists and uses Python 3.11, skip the environment creation command.

Verify installation:

```powershell
.\.venv\Scripts\apiguard.exe --version
.\.venv\Scripts\apiguard.exe --help
```

These commands use the virtual environment directly; activation is optional.

## Application Configuration

The NexStock configuration is stored in `configs/nexstock.yaml`.

It defines:

- `name`: application identifier.
- `base_url`: application address.
- `spec_location`: OpenAPI specification URL or local file location.
- `timeouts`: positive request and run time limits.
- `auth`: authentication settings and environment-variable names.
- `reset`: the proposed command for restoring test data.

The current `check` command uses the request timeout. Authentication, database resets, and total-run timeout enforcement are not implemented by this command.

Keep actual credentials out of tracked configuration files. `.env.example` lists the environment variables. The CLI reads a git-ignored `.env` file in the current directory; variables that are already set take priority.

## Run NexStock in Docker

Prerequisite: Docker Desktop (Docker Compose v2). From the APIGuard repository root:

```powershell
docker compose -f apps/nexstock/compose.yaml up --detach --wait api
```

This builds NexStock from one pinned commit, starts PostgreSQL, loads the seed data and serves the API at `http://127.0.0.1:8000`. The specification is at `http://127.0.0.1:8000/openapi.json`. Stop and delete the environment with `docker compose -f apps/nexstock/compose.yaml down --volumes`.

Restore the seed data at any time, also while the API is running:

```powershell
docker compose -f apps/nexstock/compose.yaml run --rm reset
```

This is the `reset.command` in `configs/nexstock.yaml`. Every reset restores the same database contents.

How the environment is made reproducible:

- **Pinned commit:** `apps/nexstock/Dockerfile` builds NexStock commit `616e053ebda66294f5d3532dae4b3d752acc6cb0` (v1: 28 operations, 26 require authentication). The later v2 release has 66 operations.
- **Pinned dependencies:** NexStock's `requirements.txt` sets only minimum versions. `apps/nexstock/constraints.txt` fixes every installed version. It keeps `bcrypt` at 4.0.1 because `passlib` 1.7.4 cannot hash passwords with `bcrypt` 5. `DATABASE_URL` names the `psycopg2` driver because SQLAlchemy 2.1 otherwise selects `psycopg` 3, which is not installed.
- **Fixed seed data:** NexStock's seed scripts use random values and the current time, so running them twice gives different data. `apps/nexstock/seed.sql` is a database dump made once from those scripts by `apps/nexstock/make_seed.sh`. The reset service drops the `public` schema and loads this dump. Run `make_seed.sh` (from a POSIX shell such as Git Bash) only when the pinned commit changes, and commit the new `seed.sql`.

The seeded Admin and Manager accounts are defined in NexStock's `backend/scripts/seed_users.py`. Put their email addresses and passwords in the environment variables listed in `.env.example`.

NexStock v1 has known defects, which APIGuard should detect: `GET /api/auth/me` and `GET /api/inventory` return HTTP 500 for every authenticated request.

## Check NexStock Connectivity

Start the NexStock environment as described above, then run from the APIGuard repository root:

```powershell
.\.venv\Scripts\apiguard.exe check nexstock
$LASTEXITCODE
```

The default configuration requests:

```text
http://127.0.0.1:8000/openapi.json
```

After successful connectivity and specification validation, the command prints:

```text
OK: nexstock is reachable and its OpenAPI specification is valid.
```

If `spec_location` points to a local file, the command validates that file first, then checks `base_url`. Relative paths resolve from the working directory; run commands from the repository root. A remote specification is downloaded once, using the configured request timeout and following redirects.

| Exit code | Meaning |
|---|---|
| `0` | Connectivity and specification validation succeeded |
| `1` | Network failure, timeout, or HTTP error |
| `2` | Configuration, specification or command-input error, or an unimplemented command |

A connection error is expected when NexStock is not running. Validation errors include JSON Pointer locations, such as `#/info/title`.

### Specification snapshots and current limits

`apiguard.openapi.load_spec(location, timeout)` returns a validated document and its original bytes. `save_snapshot(spec, suite_directory)` writes those bytes to `openapi.yaml` and their SHA-256 digest to `openapi.sha256`. JSON input also uses the `.yaml` extension because JSON is valid YAML. The digest covers the exact saved bytes, including whitespace and comments.

Use a separate directory for each suite version. The snapshot helper replaces the two snapshot files when called again for the same directory. It does not make the two writes atomic. The future generator must call it when saving each suite; `check` does not create a suite or snapshot.

Internal references (`#/components/...`) are supported. External references to other files or URLs are explicitly rejected in this first implementation, so validation cannot make additional uncontrolled requests and snapshots remain self-contained. Swagger 2.0, recursive YAML aliases, and non-JSON YAML values are unsupported. This limit can be revisited during reference-resolution work in issue #8.

Validation uses `openapi-spec-validator` rather than a hand-written partial OpenAPI validator. Tests use mocked requests and temporary files; no live service is required.

## Summarize NexStock Operations

```powershell
.\.venv\Scripts\apiguard.exe spec nexstock
```

The command loads and validates the specification in the same way as `check`, then prints one row for each operation. Example output for a small test specification:

```text
nexstock: 4 operations, 2 require authentication (OpenAPI 3.1.0)

METHOD  PATH                        AUTH                           PARAMETERS                        BODY           RESPONSES
POST    /api/auth/login             none                           -                                 Login (form)*  200, 422
GET     /api/products/{product_id}  OAuth2PasswordBearer           path:product_id*, query:verbose*  -              200
DELETE  /api/products/{product_id}  OAuth2PasswordBearer           path:product_id*, query:verbose   -              204
GET     /api/catalog                optional:OAuth2PasswordBearer  -                                 -              200
```

A trailing `*` marks a required parameter or request body. `AUTH` lists the security schemes that the operation accepts; `optional:` means that anonymous requests are also allowed. `spec` does not check `base_url` and uses the same exit codes as `check`.

The table comes from `apiguard.operations.extract_operations(document)`, which returns one `Operation` for each path and method. Each operation contains its parameters, request body, response status codes with their schemas, and security requirements. Local `$ref` references are resolved, so the generator, validator and metrics do not follow references themselves. A recursive schema keeps its inner `$ref` object instead of expanding forever. Operation parameters replace path-level parameters with the same name and location, and operation-level `security` replaces the global list.

The OpenAPI document only states which operations need a token. It does not state which roles may call them, such as NexStock's Admin-only operations, so authorization tests need that information from another source.

## Generate Tests

`apiguard generate` sends the extracted operations and `apps/nexstock/context.md` to Claude and asks for structured test definitions (happy path, schema validation, authentication and boundary value). APIGuard validates every definition against the specification before it saves it, and records why it excluded the others. Set `ANTHROPIC_API_KEY` in the git-ignored `.env` file. The `generation.limits` section in the configuration caps calls, output tokens and estimated cost.

```bash
apiguard generate nexstock --tag Authentication --tag Categories --tag Products --tag Inventory
```

A suite is saved in `suites/nexstock/<suite-id>/` with a snapshot of the specification it was generated from. Login credentials appear in tests only as placeholders such as `{{admin.email}}`, never as values.

## Development Checks

Run these commands before opening a pull request:

```powershell
.\.venv\Scripts\python.exe -m ruff format .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -q
```

To check formatting without changing files:

```powershell
.\.venv\Scripts\python.exe -m ruff format --check .
```

Configuration and CLI tests use temporary files and simulated HTTP responses. They do not require Docker, a running NexStock instance, or AI credentials.
