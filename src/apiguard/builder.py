"""Convert saved test definitions to Pytest files (Method B builder)."""

import pprint
import re
import subprocess
import sys
from pathlib import Path

from apiguard.validator import MUTATING_METHODS

CONFTEST = '''"""Shared fixture for the generated tests. Made by APIGuard; do not edit."""

from pathlib import Path

import pytest

from apiguard.pytest_support import open_api


@pytest.fixture(scope="session")
def api():
    client = open_api(Path(__file__).resolve().parents[1])
    yield client
    client.close()
'''


def build_pytest(suite_dir, tests):
    """Write conftest.py and one test file for each operation group. Returns the file paths."""
    directory = Path(suite_dir) / "pytest"
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob("test_*.py"):
        old.unlink()
    (directory / "conftest.py").write_text(CONFTEST, encoding="utf-8")

    # Reads first, as in `apiguard run`; each file keeps the order of its tests.
    ordered = sorted(tests, key=lambda test: test["method"] in MUTATING_METHODS)
    groups = {}
    for test in ordered:
        groups.setdefault(_group(test["id"]), []).append(test)
    paths, names = [], set()
    for group, group_tests in groups.items():
        path = directory / f"test_{group}.py"
        header = f'"""Tests for {group}. Made by APIGuard from tests.json; do not edit."""\n'
        path.write_text(header + "".join(_function(t, names) for t in group_tests), "utf-8")
        paths.append(path)
    return paths


def collect(directory):
    """Return the number of test files and tests that Pytest can collect, without running them."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "."],
        cwd=directory,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    ids = [line for line in completed.stdout.splitlines() if "::" in line]
    return {
        "files_collected": len({line.split("::")[0] for line in ids}),
        "tests_collected": len(ids),
        "collect_exit_code": completed.returncode,
    }


def _group(test_id):
    return _name(re.split(r"[-_.]", test_id)[0]) or "other"


def _name(text):
    return re.sub(r"\W+", "_", text).strip("_").lower()


def _function(test, names):
    arguments = {
        "method": test["method"],
        "path": test["path"],
        "role": test["role"],
        "expected_status": test["expected_status"],
        "path_params": test["path_params"],
        "query_params": test["query_params"],
        "body": test["body"],
        "test_id": test["id"],
        "test_type": test["type"],
    }
    name = base = _name(test["id"])
    number = 2
    while name in names:  # IDs such as "a-b" and "a_b" give the same function name.
        name, number = f"{base}_{number}", number + 1
    names.add(name)
    lines = [f"\n\ndef test_{name}(api):", f"    {_docstring(test['description'])}"]
    lines.append("    api.check(")
    for key, value in arguments.items():
        text = pprint.pformat(value, width=88, sort_dicts=False).replace("\n", "\n        ")
        lines.append(f"        {key}={text},")
    lines.append("    )")
    return "\n".join(lines) + "\n"


def _docstring(text):
    return repr(" ".join(str(text).split()))
