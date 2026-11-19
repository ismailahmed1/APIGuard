"""Run APIGuard and Schemathesis on original NexStock and on each seeded fault.

A fault counts as detected when a tool reports a new failure, compared with the original
application, on the operation that the fault changes. New failures on other operations are
reported as possible false positives. Run from the repository root:

    python scripts/evaluate_faults.py [--suite SUITE_ID]
    python scripts/evaluate_faults.py --show   # print the latest saved evaluation
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

from apiguard.baseline import compare_baselines, run_baseline
from apiguard.config import load_config
from apiguard.openapi import load_spec
from apiguard.operations import extract_operations
from apiguard.reporting import table
from apiguard.runner import get_token, load_suite, reset_app, run_suite

COMPOSE = ["docker", "compose", "-f", "apps/nexstock/compose.yaml"]
FAULTS = Path("apps/nexstock/faults/faults.yaml")


def start(fault):
    env = {**os.environ, "NEXSTOCK_FAULT": fault or ""}
    subprocess.run([*COMPOSE, "up", "--detach", "--wait", "api"], env=env, check=True,
                   capture_output=True)  # fmt: skip


def failing_operations(results):
    return {r["operation"] for r in results if r["outcome"] != "passed"}


def report(evaluation):
    faults = evaluation["faults"]
    rows = [("FAULT", "CATEGORY", "APIGUARD", "SCHEMATHESIS")]
    rows += [
        (f["id"][:3], f["category"], f["apiguard"]["text"], f["schemathesis"]["text"])
        for f in faults
    ]
    print("\n".join(table(rows)))
    found = {
        tool: sum(f[tool]["detected"] for f in faults) for tool in ("apiguard", "schemathesis")
    }
    print(
        f"\nFault-detection rate: APIGuard {found['apiguard']}/{len(faults)}, "
        f"Schemathesis {found['schemathesis']}/{len(faults)}"
    )
    original = evaluation["original_failing_operations"]
    print(
        f"Operations failing on the original app: APIGuard {original['apiguard']}, "
        f"Schemathesis {original['schemathesis']}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", help="Suite ID (default: the latest suite).")
    parser.add_argument("--show", action="store_true", help="Print the latest saved evaluation.")
    args = parser.parse_args()
    if args.show:
        saved = sorted(Path("runs/nexstock").glob("evaluation-*.json"))
        if not saved:
            print("No saved evaluation; run without --show first.")
            return 2
        print(f"Evaluation {saved[-1].name}")
        report(json.loads(saved[-1].read_text(encoding="utf-8")))
        return 0
    load_dotenv(".env")

    config = load_config("configs/nexstock.yaml")
    suite_dir, metadata, tests = load_suite("suites", "nexstock", args.suite)
    snapshot = load_spec(str(suite_dir / "openapi.yaml"), 10)
    operations = extract_operations(snapshot.document)
    tags = metadata["tags"]
    faults = yaml.safe_load(FAULTS.read_text(encoding="utf-8"))

    runs = {}
    for fault in [None, *(f["id"] for f in faults)]:
        label = fault or "original"
        print(f"{label}: starting NexStock ...", flush=True)
        start(fault)
        _, _, results = run_suite(config, metadata, tests, operations, "runs", label)
        reset_app(config)
        # Both tools check the application against the same saved specification.
        _, baseline = run_baseline(
            config, tags, get_token(config, "admin"), "runs", label, suite_dir / "openapi.yaml"
        )
        runs[label] = {"apiguard": results, "schemathesis": baseline}
    start(None)

    base = runs["original"]
    record = []
    for fault in faults:
        run = runs[fault["id"]]
        before = {r["id"]: r["outcome"] for r in base["apiguard"]}
        new_apiguard = {
            r["operation"]
            for r in run["apiguard"]
            if r["outcome"] != "passed" and before.get(r["id"]) == "passed"
        }
        new_schemathesis = {
            op for op, _ in compare_baselines(base["schemathesis"], run["schemathesis"])
        }
        verdicts = {}
        for tool, new in (("apiguard", new_apiguard), ("schemathesis", new_schemathesis)):
            detected = fault["operation"] in new
            others = sorted(new - {fault["operation"]})
            text = "DETECTED" if detected else "missed"
            if others:
                text += f" (+{len(others)} other)"
            verdicts[tool] = {"detected": detected, "other_new_failures": others, "text": text}
        record.append({**fault, **{tool: v for tool, v in verdicts.items()}})

    evaluation = {
        "suite_id": metadata["suite_id"],
        "tests": len(tests),
        "original_failing_operations": {
            "apiguard": len(failing_operations(base["apiguard"])),
            "schemathesis": sum(bool(c) for c in base["schemathesis"]["failures"].values()),
        },
        "faults": record,
    }
    print()
    report(evaluation)
    out = Path("runs/nexstock") / f"evaluation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(evaluation, indent=2) + "\n")
    print(f"Saved to {out}")


if __name__ == "__main__":
    sys.exit(main())
