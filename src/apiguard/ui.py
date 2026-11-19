"""Local web UI for the prototype loop: generate, choose the app version, run, compare, evaluate.

The UI runs the same CLI commands and scripts as a terminal user, and reads the same saved suites
and runs. It accepts only a fixed set of actions and listens on 127.0.0.1 only.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import yaml

from apiguard.openapi import load_spec
from apiguard.operations import extract_operations

PAGE = Path(__file__).with_name("ui.html")
ID = re.compile(r"[0-9]{8}-[0-9]{6}")
ORIGINAL = "original"
CLI = "import sys; from apiguard.cli import main; sys.exit(main(sys.argv[1:]))"
DOCKER_BIN = Path.home() / ".docker" / "bin"


class UIError(Exception):
    """A request that the UI does not accept; the message is shown to the user."""


class Job:
    def __init__(self, action, title, command, env):
        self.id = f"{time.time():.3f}"
        self.action = action
        self.title = title
        self.command = command
        self.env = env
        self.status = "running"
        self.exit_code = None
        self.log = []
        self.started = time.time()
        self.finished = None

    def summary(self, log=True):
        data = {
            "id": self.id,
            "action": self.action,
            "title": self.title,
            "status": self.status,
            "exit_code": self.exit_code,
            "seconds": round((self.finished or time.time()) - self.started, 1),
        }
        if log:
            data["log"] = self.log[-400:]
        return data


class Workspace:
    """Reads saved results and starts actions for one configured application."""

    def __init__(self, config, root="."):
        self.config = config
        self.app = config["name"]
        self.root = Path(root)
        self.suites = self.root / "suites" / self.app
        self.runs = self.root / "runs" / self.app
        self.compose = self.root / "apps" / self.app / "compose.yaml"
        self.faults_file = self.root / "apps" / self.app / "faults" / "faults.yaml"
        self.lock = threading.Lock()
        self.job = None

    # Reading state.

    def faults(self):
        if not self.faults_file.exists():
            return []
        return yaml.safe_load(self.faults_file.read_text(encoding="utf-8")) or []

    def variants(self):
        return [{"id": ORIGINAL, "category": "No fault", "operation": ""}, *self.faults()]

    def running_variant(self):
        if not self.compose.exists():
            return None
        try:
            result = subprocess.run(
                ["docker", "compose", "-f", str(self.compose), "ps", "api", "--format",
                 "{{.Image}}"],
                capture_output=True, text=True, timeout=10, env=self._env(), check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            return None
        image = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
        return image.rsplit(":", 1)[-1] if ":" in image else None

    def reachable(self):
        try:
            response = httpx.get(self.config["spec_location"], timeout=2)
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    def tags(self):
        """Operation tags with operation counts, from the live spec or the latest snapshot."""
        sources = [self.config["spec_location"]]
        latest = self._latest(self.suites)
        if latest:
            sources.append(str(self.suites / latest / "openapi.yaml"))
        for source in sources:
            try:
                operations = extract_operations(load_spec(source, 5).document)
            except Exception:  # noqa: BLE001, S112 - any failure falls through to the next source
                continue
            counts = Counter(tag for operation in operations for tag in operation.tags)
            return [{"name": name, "operations": n} for name, n in counts.items()]
        return []

    def suite_list(self):
        suites = []
        for directory in sorted(self.suites.glob("*/"), reverse=True):
            metadata = self._json(directory / "suite.json")
            tests = self._json(directory / "tests.json")
            if metadata is None or tests is None:
                continue
            usage = metadata.get("ai_usage", {})
            suites.append({
                "id": metadata["suite_id"],
                "tags": metadata.get("tags", []),
                "operations": len(metadata.get("operations", [])),
                "counts": metadata.get("counts", {}),
                "types": dict(Counter(test["type"] for test in tests)),
                "cost_usd": usage.get("cost_usd"),
                "model": metadata.get("model"),
                "seconds": metadata.get("generation_seconds"),
            })  # fmt: skip
        return suites

    def run_list(self):
        runs = []
        for directory in sorted(self.runs.glob("[0-9]*/"), reverse=True):
            run = self._json(directory / "run.json")
            if run is None:
                continue
            keys = ("run_id", "label", "suite_id", "total", "outcomes", "seconds", "started_at")
            runs.append({key: run.get(key) for key in keys})
        return runs

    def evaluation(self):
        saved = sorted(self.runs.glob("evaluation-*.json"))
        if not saved:
            return None
        data = self._json(saved[-1]) or {}
        return {**data, "file": saved[-1].name}

    def state(self):
        with self.lock:
            job = self.job.summary(log=False) if self.job else None
        return {
            "app": self.app,
            "base_url": self.config["base_url"],
            "reachable": self.reachable(),
            "variant": self.running_variant(),
            "variants": self.variants(),
            "has_ai_key": bool(
                os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            ),
            "tags": self.tags(),
            "suites": self.suite_list(),
            "latest_suite": self._latest(self.suites),
            "runs": self.run_list(),
            "evaluation": self.evaluation(),
            "job": job,
        }

    def suite(self, suite_id):
        directory = self.suites / self._checked(suite_id)
        tests = self._json(directory / "tests.json")
        if tests is None:
            raise UIError(f"no suite {suite_id}")
        return {
            "metadata": self._json(directory / "suite.json"),
            "tests": tests,
            "excluded": self._json(directory / "excluded.json") or [],
        }

    def run(self, run_id):
        directory = self.runs / self._checked(run_id)
        run, results = self._json(directory / "run.json"), self._json(directory / "results.json")
        if run is None or results is None:
            raise UIError(f"no run {run_id}")
        return {"run": run, "results": results}

    def compare(self, base_id, other_id):
        base, other = self.run(base_id), self.run(other_id)
        before = {r["id"]: r["outcome"] for r in base["results"]}
        failing = [r for r in other["results"] if r["outcome"] != "passed"]
        detected = [r for r in failing if before.get(r["id"]) == "passed"]
        return {
            "base": base["run"],
            "other": other["run"],
            "detected": detected,
            "existing": len(failing) - len(detected),
            "same_suite": base["run"]["suite_id"] == other["run"]["suite_id"],
        }

    def job_status(self):
        with self.lock:
            return self.job.summary() if self.job else None

    # Starting actions.

    def start(self, action, params):
        env = self._env()
        python = [sys.executable, "-c", CLI]
        if action == "generate":
            known = {tag["name"] for tag in self.tags()}
            tags = params.get("tags") or []
            if not tags or not all(isinstance(t, str) and t in known for t in tags):
                raise UIError("choose one or more operation tags")
            command = [*python, "generate", self.app, *[f"--tag={tag}" for tag in tags]]
            title = f"Generate tests with Claude: {', '.join(tags)}"
        elif action == "variant":
            variant = params.get("variant")
            if variant not in {v["id"] for v in self.variants()}:
                raise UIError("unknown application version")
            env[f"{self.app.upper()}_FAULT"] = "" if variant == ORIGINAL else variant
            command = ["docker", "compose", "-f", str(self.compose.resolve()), "up", "--detach", "--wait",
                       "api"]  # fmt: skip
            title = f"Start {self.app} ({variant})"
        elif action == "run":
            suite_id = self._checked(params.get("suite"))
            label = self.running_variant() or "unknown"
            env["ANTHROPIC_API_KEY"] = ""  # A run must not use the AI model.
            env["ANTHROPIC_AUTH_TOKEN"] = ""
            command = [*python, "run", self.app, "--suite", suite_id, "--label", label]
            title = f"Run suite {suite_id} on {label} (no AI model)"
        elif action == "evaluate":
            suite_id = self._checked(params.get("suite"))
            env["ANTHROPIC_API_KEY"] = ""
            env["ANTHROPIC_AUTH_TOKEN"] = ""
            script = self.root / "scripts" / "evaluate_faults.py"
            command = [sys.executable, str(script.resolve()), "--suite", suite_id]
            title = f"Evaluate suite {suite_id} against every seeded fault and Schemathesis"
        else:
            raise UIError(f"unknown action {action!r}")

        with self.lock:
            if self.job and self.job.status == "running":
                raise UIError(f"wait for the current task to finish: {self.job.title}")
            self.job = Job(action, title, command, env)
            job = self.job
        threading.Thread(target=self._execute, args=(job,), daemon=True).start()
        return job.summary()

    def _execute(self, job):
        job.log.append("$ " + _display(job.command, self.root))
        try:
            process = subprocess.Popen(  # fixed commands built by start()
                job.command, cwd=self.root, env=job.env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )  # fmt: skip
            for line in process.stdout:
                job.log.append(line.rstrip("\n"))
            job.exit_code = process.wait()
        except OSError as exc:
            job.log.append(f"Error: {exc}")
            job.exit_code = 2
        # `apiguard run` exits 1 when tests fail; that is a completed run, not a failed task.
        ok = job.exit_code == 0 or (job.action == "run" and job.exit_code == 1)
        job.status = "done" if ok else "failed"
        job.finished = time.time()

    # Helpers.

    def _env(self):
        env = {**os.environ, "PYTHONUNBUFFERED": "1", "DOCKER_CLI_HINTS": "false"}
        if DOCKER_BIN.is_dir() and str(DOCKER_BIN) not in env.get("PATH", ""):
            env["PATH"] = f"{DOCKER_BIN}{os.pathsep}{env.get('PATH', '')}"
        return env

    @staticmethod
    def _checked(identifier):
        if not isinstance(identifier, str) or not ID.fullmatch(identifier):
            raise UIError("invalid ID")
        return identifier

    @staticmethod
    def _latest(directory):
        try:
            return (directory / "LATEST").read_text(encoding="utf-8").strip()
        except OSError:
            return None

    @staticmethod
    def _json(path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def _display(command, root):
    """Show a command as a user would type it: `apiguard ...`, relative paths."""
    if command[1:3] == ["-c", CLI]:
        command = ["apiguard", *command[3:]]
    elif command[0] == sys.executable:
        command = ["python", *command[1:]]
    prefix = f"{Path(root).resolve()}{os.sep}"
    return " ".join(str(part).replace(prefix, "") for part in command)


def make_handler(workspace, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # Keep the terminal quiet.
            pass

        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _guarded(self, handler):
            # Refuse requests from other sites (DNS rebinding, cross-site posts).
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(403, {"error": "forbidden host"})
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc not in allowed_hosts:
                return self._send(403, {"error": "forbidden origin"})
            try:
                return self._send(200, handler())
            except UIError as exc:
                return self._send(400, {"error": str(exc)})

        def do_GET(self):  # http.server API
            url = urlparse(self.path)
            query = {key: values[0] for key, values in parse_qs(url.query).items()}
            if url.path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            routes = {
                "/api/state": workspace.state,
                "/api/job": workspace.job_status,
                "/api/suite": lambda: workspace.suite(query.get("id")),
                "/api/run": lambda: workspace.run(query.get("id")),
                "/api/compare": lambda: workspace.compare(query.get("base"), query.get("other")),
            }
            if url.path not in routes:
                return self._send(404, {"error": "not found"})
            return self._guarded(routes[url.path])

        def do_POST(self):  # http.server API
            if self.path != "/api/start":
                return self._send(404, {"error": "not found"})
            length = min(int(self.headers.get("Content-Length") or 0), 10_000)
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "invalid JSON"})
            return self._guarded(lambda: workspace.start(body.get("action"), body))

    return Handler


def serve(config, port=8765, open_browser=True):
    workspace = Workspace(config)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(workspace, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"APIGuard UI for {config['name']}: {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0
