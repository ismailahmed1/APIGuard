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
- Running saved suites without the AI model with `apiguard run`, and reading results with `apiguard report`.
- Running a saved suite more than one time with `apiguard validate <app> --runs N`. It flags tests with different results and saves the saved, rejected and flaky tests in `validation.json` in the suite directory.
- Comparing two runs with `apiguard compare`, and running a Schemathesis baseline with `apiguard baseline`.
- Evaluating fault detection against seeded NexStock faults with `scripts/evaluate_faults.py`.

The `check` command loads and validates self-contained OpenAPI 3.0, 3.1 and 3.2 documents from JSON/YAML files or HTTP/HTTPS URLs.

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

## Local Setup — WSL/Linux

Run the following commands from the repository root, which contains `pyproject.toml`:

```bash
# Requires Python 3.11 or newer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"

apiguard --version

# Development checks
python -m ruff check .
python -m ruff format --check .
python -m pytest -q
```

On Ubuntu, if environment creation reports missing `ensurepip`, install `python3-venv` with `sudo apt install python3-venv`, then retry creating the environment.

## Application Configuration

The NexStock configuration is stored in `configs/nexstock.yaml`.

It defines:

- `name`: application identifier.
- `app_commit`: optional full upstream commit SHA for the tested application; keep it in sync with the Dockerfile or submodule pin. Omit it or set it to `null` when unavailable.
- `base_url`: application address.
- `spec_location`: OpenAPI specification URL or local file location.
- `timeouts`: positive request and run time limits.
- `auth`: authentication settings and environment-variable names.
- `reset`: the proposed command for restoring test data.

The current `check` command uses the request timeout. Authentication, database resets, and total-run timeout enforcement are not implemented by this command.

Keep actual credentials out of tracked configuration files. `.env.example` lists the environment variables. The CLI reads a git-ignored `.env` file in the current directory; variables that are already set take priority.

Each saved `run.json` records `app_commit` from the application configuration, plus
`spec_sha256` and `suite_id` from the saved suite metadata. An unavailable commit is
recorded as JSON `null`; APIGuard does not infer it from its own Git checkout. The
spec hash identifies the suite's specification snapshot used during the run.

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

Use a separate directory for each suite version. The snapshot helper replaces the two snapshot files when called again for the same directory. It does not make the two writes atomic. When `apiguard generate` saves a suite, it writes the original specification to `openapi.yaml`, saves its SHA-256 fingerprint in `openapi.sha256`, and records the same fingerprint in `suite.json`. The `check` command only validates connectivity and the specification.

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

## Generate and Run Tests

`apiguard generate` sends the extracted operations and `apps/nexstock/context.md` to Claude and asks for structured test definitions (happy path, schema validation, authentication and boundary value). APIGuard validates every definition against the specification before it saves it, and records why it excluded the others. Set `ANTHROPIC_API_KEY` in the git-ignored `.env` file.

The `generation.limits` settings stop further requests once recorded calls, output tokens or estimated cost reach a threshold. Checks happen between requests: an in-flight request can exceed the output-token or estimated-cost threshold, so the spending threshold is not a guaranteed hard cap. Valid tests already returned are saved with the stop reason. `suite.json` records calls, token usage, generation time and estimated cost. See [AI usage limits and records](docs/PROJECT_CONTEXT.md#ai-usage-limits-and-records-issue-10) for accounting limitations.

```bash
apiguard generate nexstock --tag Authentication --tag Categories --tag Products --tag Inventory
apiguard run nexstock --label original      # no AI model; resets seed data
apiguard report nexstock                    # latest run
```

A suite is saved in `suites/nexstock/<suite-id>/` with a snapshot of the specification it was generated from. Runs are saved in `runs/nexstock/<run-id>/` (git-ignored). Login credentials appear in tests only as placeholders such as `{{admin.email}}`; the runner fills them from `.env`, and passwords and tokens are removed from saved results. Each failure has a category: API failure, generated-test error, configuration error or infrastructure error.

### Seeded faults and the Schemathesis baseline

For the standalone NexStock baseline, follow [the setup and exact commands in eval/](eval/README.md).
The [first-results summary](eval/nexstock-first-results.json) records the authenticated
original-app run: 28 API operations tested, 45 reported check failures and one
stateful streaming error. The 29 JUnit groups include `Stateful tests`; they do
not represent 29 distinct API endpoints.

`apps/nexstock/faults/` contains three patches, each with one fault. Start NexStock with one of them, run the same suite, and compare the run with the run on the original app. `compare` accepts run IDs or labels:

```bash
NEXSTOCK_FAULT=F01-products-list-without-auth docker compose -f apps/nexstock/compose.yaml up --detach --wait api
apiguard run nexstock --label F01-products-list-without-auth
apiguard compare nexstock original F01-products-list-without-auth
```

`apiguard baseline nexstock --tag ... --label original` runs Schemathesis in Docker on the same operations, and `apiguard compare nexstock A B --schemathesis` compares two baseline runs. `python scripts/evaluate_faults.py` does all of this for the original app and every fault, and prints the fault-detection rate of each tool (`--show` prints the latest saved result). A fault counts as detected only when a tool reports a new failure on the operation that the fault changes. Both tools check the application against the specification snapshot of the suite.

## Web UI

`apiguard ui nexstock` opens a local page at http://127.0.0.1:8765/ with the same workflow: choose operation tags and generate a suite with Claude, switch NexStock between the original code and each seeded fault, run a saved suite without the AI model, compare two runs, and see the latest evaluation against Schemathesis. Task output appears live at the bottom of the page.

The page runs the same CLI commands and scripts and reads the same saved files. It listens on 127.0.0.1 only, refuses requests from other sites, and accepts only those fixed actions. Stop it with Ctrl+C.

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

The automated tests use temporary files and simulated HTTP responses. They do not require Docker, a running application, or an AI API key.

## Run the Full Stack FastAPI Template

Start Docker Desktop, then run these commands from the APIGuard repository root:

```powershell
git submodule update --init apps/template/upstream
.\.venv\Scripts\python.exe apps/template/manage.py start
.\.venv\Scripts\apiguard.exe check template
.\.venv\Scripts\apiguard.exe run template --suite smoke
```

The template uses port 8011. The first start saves a copy of its initial database.
APIGuard restores that copy before running the saved health test. Run
`python apps/template/manage.py logs` to check recent health-request logs.

## Run the Task Management API

From the repository root in PowerShell with the APIGuard virtual environment active:

```powershell
git -c core.autocrlf=false submodule update --init apps/tasks/upstream
$env:TASKS_MEMBER_EMAIL = 'member@example.com'
$env:TASKS_MEMBER_PASSWORD = [guid]::NewGuid().ToString('N')
python apps/tasks/manage.py start
apiguard check tasks
python apps/tasks/manage.py snapshot
apiguard run tasks --suite smoke
python apps/tasks/manage.py logs
```

The API listens on loopback port 8012. The snapshot command saves the live
OpenAPI document and its hash for the smoke suite. Commit the three generated
snapshot files with the integration. Once committed, later runs can skip this step.
Each smoke run replaces the disposable database and Redis volumes belonging to
the `apiguard-tasks` Compose project, migrates the database, and registers one
test member using the two session variables above. Set them again in a new shell.
The same profile read should return 200 with the member's token and 401 without it.
The logs command parses those two request events from the current API container.
Use `python apps/tasks/manage.py stop` to stop this app.
