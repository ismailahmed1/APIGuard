import json

import pytest
from shop_spec import SHOP
from test_generation import FakeAnthropic

from apiguard.ai import AIClient
from apiguard.generator_pytest import check_file, generate_pytest_suite
from apiguard.openapi import LoadedSpec
from apiguard.operations import extract_operations

OPERATIONS = extract_operations(SHOP)
GOOD = """
def test_products_list(api):
    api.check("GET", "/api/products", "admin", 200)


def test_products_without_token(api):
    api.check("GET", "/api/products", "anonymous", 401)
"""


def answer(code):
    return json.dumps({"code": code}), "end_turn"


def generate(tmp_path, replies, limits=None):
    fake = FakeAnthropic(replies)
    ai = AIClient("claude-opus-5-5", limits or {}, client=fake)
    spec = LoadedSpec(document=SHOP, raw=json.dumps(SHOP).encode())
    directory, metadata = generate_pytest_suite(
        "shop", spec, OPERATIONS, ["Products", "Auth"], ai, "Seed data.", ["admin"], tmp_path
    )
    return directory, metadata, fake


def test_saves_files_that_pytest_can_collect_and_records_metrics(tmp_path):
    directory, metadata, fake = generate(tmp_path, [answer(GOOD), answer("def broken(:\n")])
    pytest_dir = directory / "pytest"
    assert sorted(p.name for p in pytest_dir.iterdir() if p.suffix == ".py") == [
        "conftest.py",
        "test_auth.py",  # The first group in the specification.
    ]
    assert metadata["generation_method"] == "pytest-direct"
    assert metadata["counts"] == {
        "files_generated": 2,
        "files_saved": 1,
        "files_rejected": 1,
        "files_that_run": 1,
        "tests_collected": 2,
    }
    assert metadata["ai_usage"]["calls"] == 2
    assert metadata["generation_seconds"] >= 0
    rejected = json.loads((directory / "rejected.json").read_text())
    assert rejected[0]["file"] == "test_products.py"
    assert rejected[0]["reason"].startswith("syntax error on line 1")
    assert (directory / "openapi.yaml").exists()
    # The prompt names the shared fixture and the function prefix.
    request = fake.requests[0]
    assert "api.check(" in request["system"][0]["text"]
    assert "'test_auth_'" in request["messages"][0]["content"]
    # Method A suites do not replace the latest structured suite.
    assert not (tmp_path / "shop" / "LATEST").exists()


def test_limit_keeps_the_files_already_generated(tmp_path):
    _, metadata, _ = generate(tmp_path, [answer(GOOD)], limits={"max_calls": 1})
    assert metadata["counts"]["files_saved"] == 1
    assert "1 model calls" in metadata["stopped_reason"]


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("x = 1\n", "no test functions"),
        ("import httpx\n\ndef test_a(api):\n    pass\n", "imports 'httpx'"),
        ("from os import path\n\ndef test_a(api):\n    pass\n", "imports 'os'"),
    ],
)
def test_check_file_rejects_unusable_files(code, reason):
    assert reason in check_file(code)


def test_check_file_accepts_allowed_imports():
    assert check_file("import json\nimport pytest\n\ndef test_a(api):\n    pass\n") is None
