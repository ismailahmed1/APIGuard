"""Run Schemathesis, the evaluation baseline, on the same operations as APIGuard."""

import json
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

SCHEMATHESIS_IMAGE = "schemathesis/schemathesis:4.33.4"
JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")


class BaselineError(Exception):
    """Schemathesis could not be run or its report could not be read."""


def run_baseline(config, tags, token, runs_dir, label=None, spec_file=None):
    """Run Schemathesis and save a summary. Returns (directory, summary).

    With `spec_file`, Schemathesis checks the application against that saved specification
    instead of the one the application serves. Evaluation passes the snapshot that the APIGuard
    suite was generated from: a seeded fault can change the served specification too, and
    checking a fault against its own changed documentation would hide it.
    """
    settings = config.get("baseline")
    if not isinstance(settings, dict):
        raise BaselineError("the configuration has no 'baseline' section")
    started = datetime.now(UTC)
    run_id = "baseline-" + started.strftime("%Y%m%d-%H%M%S")
    directory = (Path(runs_dir) / config["name"] / run_id).resolve()
    directory.mkdir(parents=True, exist_ok=True)

    command = [
        "docker", "run", "--rm",
        "--network", settings["docker_network"],
        "--volume", f"{directory}:/out",
        "--user", f"{os.getuid()}:{os.getgid()}",
    ]  # fmt: skip
    if spec_file:
        command += ["--volume", f"{Path(spec_file).resolve()}:/spec/openapi.yaml:ro"]
        target = ["/spec/openapi.yaml", "--url", settings["base_url"]]
    else:
        target = [settings["spec_url"]]
    command += [
        SCHEMATHESIS_IMAGE, "run", *target,
        "--checks", "all",
        "--max-examples", str(settings.get("max_examples", 25)),
        "--seed", str(settings.get("seed", 4907)),
        "--report", "junit",
        "--report-junit-path", "/out/junit.xml",
        "--header", f"Authorization: Bearer {token}",
    ]  # fmt: skip
    for tag in tags:
        command += ["--include-tag", tag]

    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,  # Schemathesis exits nonzero when it finds failures.
            timeout=settings.get("timeout_seconds", 900),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaselineError(f"could not run Schemathesis: {exc}") from exc
    seconds = round(time.monotonic() - start, 1)

    # Schemathesis prints reproduction commands that include the token (NFR-04).
    output = _redact(completed.stdout + completed.stderr, token)
    (directory / "output.txt").write_text(output, encoding="utf-8")
    junit = directory / "junit.xml"
    if not junit.exists():
        raise BaselineError("Schemathesis did not write a report; see " + str(directory))
    junit.write_text(_redact(junit.read_text(encoding="utf-8"), token), encoding="utf-8")

    failures = parse_junit(junit)
    summary = {
        "run_id": run_id,
        "app": config["name"],
        "label": label,
        "tool": SCHEMATHESIS_IMAGE,
        "tags": list(tags),
        "spec": str(spec_file) if spec_file else settings["spec_url"],
        "started_at": started.isoformat(timespec="seconds"),
        "seconds": seconds,
        "exit_code": completed.returncode,
        "operations_tested": len(failures),
        "failures": failures,
    }
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", "utf-8")
    return directory, summary


def parse_junit(path):
    """Map each tested operation to its sorted findings, such as 'ST103 ... (received 200)'."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise BaselineError(f"cannot read the Schemathesis report {path}") from exc
    failures = {}
    for case in root.iter("testcase"):
        findings = set()
        for problem in [*case.iter("failure"), *case.iter("error")]:
            text = (problem.get("message") or "") + "\n" + (problem.text or "")
            findings.update(_findings(text) or {problem.get("type") or "failure"})
        failures[case.get("name", "?")] = sorted(findings)
    return failures


def _findings(text):
    """Read '- <check name>' lines; a following 'Received: <status>' line refines the finding.

    The status matters: an operation that already returns an undocumented 400 on the original
    application must still show a new finding when a fault makes it return an undocumented 200.
    """
    findings, current, refined = set(), None, False
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- "):
            if current and not refined:
                findings.add(current)
            current, refined = line[2:].strip(), False
        elif current and line.startswith("Received: "):
            findings.add(f"{current} (received {line.split()[1]})")
            refined = True
    if current and not refined:
        findings.add(current)
    return findings


def compare_baselines(base, run):
    """(operation, check) pairs that fail in the run but not in the base run."""
    new = []
    for operation, checks in run["failures"].items():
        old = set(base["failures"].get(operation, []))
        new += [(operation, check) for check in checks if check not in old]
    return new


def _redact(text, token):
    return JWT.sub("[REDACTED-TOKEN]", text.replace(token, "[REDACTED]"))
