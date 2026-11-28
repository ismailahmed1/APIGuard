# NexStock Schemathesis baseline (Issue #15)

Use the existing `apiguard baseline` command. It resets NexStock, logs in as the
configured admin, and runs Schemathesis in Docker. It needs no Claude key, saved
AI-generated suite, or AI calls. Fault-detection comparisons are Issue #27.

The first run is recorded in [nexstock-first-results.json](nexstock-first-results.json).
Run `baseline-20261127-234654` started at 2026-11-27 23:46:54 UTC and produced reports
after the configured database reset and admin login. It supersedes the earlier
Docker-blocked attempt. No application or runner changes were needed to record it.

## First results

Schemathesis selected and tested **28 API method/path operations**, with no tag
filter. Of these, 21 had findings and seven had none. JUnit contains **29 groups**:
the 28 API operations plus `Stateful tests`. The raw summary's `operations_tested:
29` counts these groups, not 29 distinct API endpoints.

The Docker subprocess took **31.5 seconds**, including the first tool-image pull;
Schemathesis itself reported **14.99 seconds** and exit code **1**. Reset and initial
login occurred before that timed subprocess. The tool generated 696 cases; 34
cases exposed 45 unique check failures, with one execution error and one warning.

| Reported check | Failures across phases |
|---|---:|
| ST101 Server error | 11 |
| ST103 Undocumented status code | 21 |
| ST105 Undocumented Content-Type | 3 |
| ST201 Schema-violating request accepted | 1 |
| ST202 Schema-valid request rejected | 3 |
| ST205 Allow header mismatch | 6 |

These are the console's totals, including stateful scenarios; they are not counts
of affected endpoints. The JSON separately lists findings per API operation.
Findings include 500 responses, undocumented 400/401/404 responses, CSV exports
with undocumented content types, request-validation mismatches, and `Allow` header
mismatches. They describe behavior of the original app and its specification;
they do not establish seeded-fault detection.

The authentication warning concerns generated `POST /api/auth/login` cases that
returned 401. The CLI's initial configured admin login succeeded before the tool
started; random login cases do not reuse that credential exchange.

### Stateful execution error

`Stateful tests` recorded 105 scenarios: 86 passed, 18 failed and one errored.
The error is a **Network Error** on
`GET /api/reports/export/stock-movements`: the chunked response ended prematurely.
It is recorded as a JUnit `<error>`, separately from the group's `<failure>`
elements for ordinary status/schema check findings.

The matching API traceback at `2026-11-27T23:47:25.133Z` shows an invalid movement
`type` causing `ValueError` in `MovementType(movement_type)` at
`app/services/report_service.py:60`, called from `export_movements_csv` at line 140.
The export handler wraps that generator in `StreamingResponse`; the exception
occurs while the response stream is being consumed. This explains the interrupted
body observed by Schemathesis. It is an application streaming exception surfaced
as a transport error, rather than a completed HTTP response failing an assertion
or evidence of a Docker outage. No raw query values or reproduction headers are
needed in the shared summary.

The stateful phase reported **0 of 79 inferred links covered** and includes an
errored scenario. These results do not establish complete workflow coverage.
Fixing the upstream app or changing the baseline runner is outside this recording
update.

### Application and environment evidence

The run used `schemathesis/schemathesis:4.33.4`; the console records version 4.33.4
and the pulled image digest. Read-only inspection after the run found the API
container started at `23:46:15 UTC`, before the run, with zero restarts. Its image
history records the pinned NexStock SHA
`616e053ebda66294f5d3532dae4b3d752acc6cb0` and an empty `NEXSTOCK_FAULT` on the patch
layer. This verifies the original image independently of its `original` tag.
The image was created on November 24; no fresh no-cache rebuild is claimed.

Runtime inspection found NexStock version 1.0.0 (OpenAPI 3.1.0), Python 3.11.18,
FastAPI 0.163.1 and PostgreSQL 16.4. Docker Engine/CLI were 29.9.3, Compose 5.7.0,
and host Python 3.14.4 with APIGuard 0.1.0. The JSON records the image identity,
timestamps and which versions came from post-run inspection.

## Prerequisites and credentials

- Run from the APIGuard repository root on Linux/WSL with Python 3.11 or newer.
- Install the development environment using the root README's setup instructions.
- Start Docker Desktop with the Linux engine and enable integration for this WSL
  distribution, or use a local Linux Docker Engine. Docker Compose v2 or newer
  must be available. `docker version` must show a reachable server.
- Allow Docker to fetch the pinned NexStock source, Python dependencies, PostgreSQL
  image, and `schemathesis/schemathesis:4.33.4` image. Port 8000 must be available.
- Set `NEXSTOCK_ADMIN_EMAIL` and `NEXSTOCK_ADMIN_PASSWORD` to the admin credentials
  matching the checked-in seed data. Use environment variables or the git-ignored
  root `.env` file; `.env.example` lists the names. Existing environment variables
  take precedence over `.env`. Do not publish credential values.

`NEXSTOCK_MANAGER_EMAIL` and `NEXSTOCK_MANAGER_PASSWORD` are not required for this
admin baseline. `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` are not required.
The CLI obtains the bearer token internally; do not copy tokens into commands.

## Prepare an original, fault-free application

These commands rebuild the original image explicitly and recreate the API
container. A label or an image tag alone does not prove that the app has no fault.
The empty shell variable overrides a fault set in the shell or Compose `.env`;
the empty build argument prevents a patch from being applied during this build.
The no-cache build avoids reusing an earlier faulty image layer. This uses the
Dockerfile's upstream pin `616e053ebda66294f5d3532dae4b3d752acc6cb0`.

```bash
source .venv/bin/activate
docker version
docker compose version
NEXSTOCK_FAULT= docker compose -f apps/nexstock/compose.yaml build --no-cache --build-arg NEXSTOCK_FAULT= api
NEXSTOCK_FAULT= docker compose -f apps/nexstock/compose.yaml up --detach --force-recreate --wait api
NEXSTOCK_FAULT= docker compose -f apps/nexstock/compose.yaml ps
python -m apiguard.cli check nexstock
python -m apiguard.cli spec nexstock
```

The API is served at `http://127.0.0.1:8000`; PostgreSQL and Schemathesis use the
isolated Compose network `apiguard-nexstock_default`. The baseline mutates local
test data. Its reset service restores `apps/nexstock/seed.sql` before login.

Record runtime versions without printing the container environment or credentials:

```bash
python --version
python -m apiguard.cli --version
NEXSTOCK_FAULT= docker compose -f apps/nexstock/compose.yaml exec -T api python -c 'import platform; from importlib.metadata import version; print("Python", platform.python_version()); print("FastAPI", version("fastapi"))'
NEXSTOCK_FAULT= docker compose -f apps/nexstock/compose.yaml exec -T db postgres --version
docker run --rm schemathesis/schemathesis:4.33.4 --version
```

## Run the baseline

```bash
python -m apiguard.cli baseline nexstock --label original
```

This is the one-command baseline after prerequisites and app preparation. It calls
the existing reset command from `configs/nexstock.yaml`:

```bash
docker compose -f apps/nexstock/compose.yaml run --rm reset
```

The CLI then logs in through `POST /api/auth/login`, extracts `data.access_token`,
and supplies the bearer token to Schemathesis. The configured settings are:

| Setting | Value |
|---|---|
| Tool image | `schemathesis/schemathesis:4.33.4` |
| Specification inside Docker | `http://api:8000/openapi.json` |
| Role | `admin` |
| Checks | `all` |
| Random seed | `4907` |
| Maximum examples (`--max-examples`) | `25` |
| Schemathesis subprocess timeout | `900` seconds |
| Login request timeout | `10` seconds |
| Reset subprocess timeout | `120` seconds |
| Endpoint filter | None; all operations in the served specification |

No `--tag` was passed for the first baseline. The console confirms 28 selected and
28 tested API operations; their method/path names are in the first-results JSON.
The standalone baseline uses the **served** specification, unlike the saved
snapshot used by `scripts/evaluate_faults.py`. Confirm the live scope with
`spec nexstock` when repeating the run.

The database resets once before the baseline, not between Schemathesis cases.
The fixed seed and limits do not guarantee identical timings or generated cases
across different tool versions or changed server state.

## Reports and sharing results

Successful report creation writes these files to the git-ignored directory
`runs/nexstock/baseline-<UTC YYYYMMDD-HHMMSS>/`:

- `summary.json`: image/version setting, scope filters, operation names and
  findings, start time, elapsed Schemathesis subprocess time, and tool exit code.
- `output.txt`: Schemathesis stdout/stderr with the supplied token and JWT-shaped
  values redacted.
- `junit.xml`: operation-level results with the same token redaction.

The CLI prints the report directory. Findings may produce a nonzero Schemathesis
exit code in `summary.json` even when the APIGuard command exits successfully;
read the summary and JUnit report. An error before report creation produces no
baseline report. On timeout or tool/report failure, do not treat partial files as
a completed run or publish them without checking for secrets.

This run's retained reports are `summary.json`, `output.txt` and `junit.xml` under
`runs/nexstock/baseline-20261127-234654/`. The console also mentions
`schema-coverage.html`, but that path was inside the removed tool container and is
not a retained host report. Raw reports and credentials remain outside Git;
`eval/nexstock-first-results.json` contains only sanitized results and evidence.
Inspect future shared excerpts for passwords, bearer tokens and reproduction
headers, and separate execution errors from API findings. Fault-detection
comparisons remain Issue #27.
