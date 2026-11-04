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

The `generate`, `run`, and `report` commands are placeholders and are not implemented yet. OpenAPI document validation and parsing are planned separately.

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

Keep actual credentials out of tracked configuration files. `.env.example` documents the intended environment-variable names; the current CLI does not automatically load a `.env` file.

## Check NexStock Connectivity

Start the NexStock environment separately, then run from the APIGuard repository root:

```powershell
.\.venv\Scripts\apiguard.exe check nexstock
$LASTEXITCODE
```

The default configuration requests:

```text
http://127.0.0.1:8000/openapi.json
```

With a successful HTTP 200 response, the command prints:

```text
OK: nexstock is reachable (HTTP 200).
```

If `spec_location` points to a local file, the command checks `base_url` instead. It does not load or validate the local specification.

| Exit code | Meaning |
|---|---|
| `0` | Connectivity check succeeded |
| `1` | Network failure, timeout, or HTTP error |
| `2` | Configuration or command-input error, or an unimplemented command |

A connection error is expected when NexStock is not running. A successful connectivity check does not prove that the response is a valid OpenAPI document.

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