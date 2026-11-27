# NexStock Schemathesis baseline (Issue #15)

Use the existing `apiguard baseline` command. It resets NexStock, logs in as the
configured admin, and runs Schemathesis in Docker. It needs no Claude key, saved
AI-generated suite, or AI calls. Fault-detection comparisons are Issue #27.

The first attempt is recorded in [nexstock-first-results.json](nexstock-first-results.json).
It is **blocked**, not a completed baseline: Docker Desktop's Linux engine was
unreachable on 2026-11-27. The configured reset failed before authentication or
Schemathesis started. No findings or baseline execution time are available.

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

No `--tag` is passed for the first baseline. The checked-in v1 snapshot lists 28
operations, 26 requiring authentication; the planned list is in the first-results
JSON. This historical snapshot is a scope reference, not proof of the running
server's scope. The standalone baseline uses the **served** specification, unlike
the saved snapshot used by `scripts/evaluate_faults.py`. Confirm the live scope
with `spec nexstock`, then record the operations actually listed in the report.

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

After a completed run, update `nexstock-first-results.json` with observed runtime
versions, actual report paths, tested operations, elapsed time, and findings from
`summary.json`. Record the build/recreation evidence that establishes no seeded
fault was active. Keep intended settings distinct from observed results. Inspect
any shared excerpts for passwords, bearer tokens and reproduction headers;
publish only the sanitized summary under `eval/`, not raw request bodies or
container environments. A baseline finding on the original app is not evidence
of seeded-fault detection.
