import ast

import httpx
import pytest
from shop_spec import SHOP

from apiguard.builder import build_pytest, collect
from apiguard.operations import extract_operations
from apiguard.pytest_support import Api

REAL_CLIENT = httpx.Client


def definition(test_id, method="GET", body=None, expected=200):
    return {
        "id": test_id,
        "type": "happy_path",
        "description": f"Check {test_id}\nwith 'quotes'",
        "method": method,
        "path": "/api/products",
        "role": "anonymous",
        "path_params": {},
        "query_params": {"limit": "5"},
        "body": body,
        "expected_status": expected,
    }


def test_build_writes_one_file_per_group_and_pytest_collects_them(tmp_path):
    tests = [
        definition("products-create", "POST", {"name": "Lamp", "ok": True, "x": None}, 201),
        definition("products-list"),
        definition("products_list"),  # Same function name as products-list.
        definition("auth-login"),
    ]
    paths = build_pytest(tmp_path, tests)
    assert sorted(p.name for p in paths) == ["test_auth.py", "test_products.py"]
    source = (tmp_path / "pytest" / "test_products.py").read_text()
    ast.parse(source)
    names = [n.name for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)]
    # Reads come before changes.
    assert names == ["test_products_list", "test_products_list_2", "test_products_create"]
    assert "'ok': True" in source
    assert collect(tmp_path / "pytest") == {
        "files_collected": 2,
        "tests_collected": 4,
        "collect_exit_code": 0,
    }


def test_build_removes_old_test_files(tmp_path):
    build_pytest(tmp_path, [definition("old-test")])
    build_pytest(tmp_path, [definition("new-test")])
    assert [p.name for p in (tmp_path / "pytest").glob("test_*.py")] == ["test_new.py"]


@pytest.fixture
def api(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"data": []}) if request.url.params else httpx.Response(500)

    monkeypatch.setattr(
        "apiguard.pytest_support.httpx.Client",
        lambda **kwargs: REAL_CLIENT(transport=httpx.MockTransport(handler), **kwargs),
    )
    config = {
        "name": "shop",
        "base_url": "http://shop.test",
        "timeouts": {"request_seconds": 5, "run_seconds": 60},
        "auth": {},
        "reset": {},
    }
    return Api(config, extract_operations(SHOP), reset=False)


def test_check_passes_on_the_expected_status(api):
    result = api.check("GET", "/api/products", "anonymous", 200, query_params={"limit": "5"})
    assert result["outcome"] == "passed"


def test_check_fails_with_the_category_and_detail(api):
    with pytest.raises(pytest.fail.Exception, match="server error 500"):
        api.check("GET", "/api/products", "anonymous", 200)
