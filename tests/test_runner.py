import base64
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest
from shop_spec import SHOP

from apiguard.operations import extract_operations
from apiguard.reporting import format_run
from apiguard.runner import RunError, get_token, load_suite, run_suite

TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
PASSWORD = "Sup3r-Secret!"
OPERATIONS = extract_operations(SHOP)
REAL_CLIENT = httpx.Client


def config():
    return {
        "name": "shop",
        "base_url": "http://shop.test",
        "timeouts": {"request_seconds": 5, "run_seconds": 60},
        "auth": {
            "login_path": "/api/auth/login",
            "token_path": "data.access_token",
            "roles": {
                "admin": {"email_env": "SHOP_ADMIN_EMAIL", "password_env": "SHOP_ADMIN_PASSWORD"},
                "manager": {
                    "email_env": "SHOP_MANAGER_EMAIL",
                    "password_env": "SHOP_MANAGER_PASSWORD",
                },
            },
        },
        "reset": {"command": ["reset-shop"]},
    }


def make_test(test_id, method, path, role="admin", expected=200, body=None, path_params=None):
    return {
        "id": test_id,
        "type": "happy_path",
        "description": test_id,
        "method": method,
        "path": path,
        "role": role,
        "path_params": path_params or {},
        "query_params": {},
        "body": body,
        "expected_status": expected,
    }


def shop(request):
    """A fake API: login, a protected list, a create and a delete that crashes."""
    authorized = request.headers.get("Authorization") == f"Bearer {TOKEN}"
    if request.url.path == "/api/auth/login":
        body = json.loads(request.content)
        if body == {"email": "admin@shop.test", "password": PASSWORD}:
            return httpx.Response(200, json={"data": {"access_token": TOKEN}})
        return httpx.Response(401, json={"detail": "bad credentials"})
    if not authorized:
        return httpx.Response(401, json={"detail": "Not authenticated"})
    if request.method == "GET":
        return httpx.Response(200, json={"data": []})
    if request.method == "POST":
        return httpx.Response(201, json={"id": 7})
    return httpx.Response(500, text="Internal Server Error")


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("SHOP_ADMIN_EMAIL", "admin@shop.test")
    monkeypatch.setenv("SHOP_ADMIN_PASSWORD", PASSWORD)
    monkeypatch.delenv("SHOP_MANAGER_EMAIL", raising=False)
    resets = []

    def fake_reset(command, **kwargs):
        resets.append(command)
        return subprocess.CompletedProcess(command, 0)

    handler = {"value": shop}
    monkeypatch.setattr("apiguard.runner.subprocess.run", fake_reset)
    monkeypatch.setattr(
        "apiguard.runner.httpx.Client",
        lambda **kwargs: REAL_CLIENT(
            transport=httpx.MockTransport(lambda r: handler["value"](r)), **kwargs
        ),
    )
    monkeypatch.chdir(tmp_path)
    return {"resets": resets, "handler": handler}


def run(tests, settings=None):
    return run_suite(settings or config(), {"suite_id": "s1"}, tests, OPERATIONS, "runs")


def test_run_records_results_and_categories(server):
    tests = [
        make_test(
            "create", "POST", "/api/products", expected=201, body={"name": "Lamp", "price": 1}
        ),
        make_test(
            "delete",
            "DELETE",
            "/api/products/{product_id}",
            path_params={"product_id": "3"},
        ),
        make_test("list", "GET", "/api/products"),
        make_test("anonymous", "GET", "/api/products", role="anonymous", expected=401),
        make_test("manager", "GET", "/api/products", role="manager"),
    ]
    directory, summary, results = run(tests)

    by_id = {r["id"]: r for r in results}
    # Reads run before changes; the second change starts from a fresh reset.
    assert [r["id"] for r in results] == ["list", "anonymous", "manager", "create", "delete"]
    assert len(server["resets"]) == 2
    assert by_id["list"]["outcome"] == "passed"
    assert by_id["anonymous"]["outcome"] == "passed"
    assert by_id["create"]["actual"]["status"] == 201
    assert by_id["delete"]["category"] == "unexpected_status"
    assert by_id["delete"]["detail"] == "server error 500 (expected 200)"
    assert by_id["delete"]["request"]["path_params"] == {"product_id": "3"}
    assert by_id["manager"]["category"] == "configuration_error"
    assert by_id["manager"]["detail"] == "environment variable SHOP_MANAGER_EMAIL is not set"
    assert by_id["list"]["type"] == "happy_path"
    assert by_id["list"]["operation"] == "GET /api/products"
    assert by_id["list"]["expected"] == {"status": 200}
    assert by_id["list"]["actual"] == {"status": 200, "body_excerpt": '{"data":[]}'}
    assert all(isinstance(result["duration_ms"], int) for result in results)

    assert summary["outcomes"] == {"passed": 3, "failed": 1, "error": 1}
    assert summary["categories"] == {"unexpected_status": 1, "configuration_error": 1}
    assert summary["ai_model_used"] is False
    saved = json.loads((directory / "results.json").read_text())
    assert saved == results
    assert json.loads((directory / "run.json").read_text()) == summary
    assert (directory.parent / "LATEST").read_text().strip() == summary["run_id"]


def test_run_saves_app_commit_spec_hash_and_suite_id(server):
    settings = config()
    settings["app_commit"] = "616e053ebda66294f5d3532dae4b3d752acc6cb0"
    metadata = {
        "suite_id": "saved-suite-14",
        "spec_sha256": "a" * 64,
        # The tested app's current pin comes from configuration, not generation metadata.
        "app_commit": "b" * 40,
    }
    directory, summary, _ = run_suite(
        settings, metadata, [make_test("list", "GET", "/api/products")], OPERATIONS, "runs"
    )

    saved = json.loads((directory / "run.json").read_text())
    assert saved == summary
    assert saved["app_commit"] == settings["app_commit"]
    assert saved["spec_sha256"] == metadata["spec_sha256"]
    assert saved["suite_id"] == metadata["suite_id"]
    assert server["resets"] == [["reset-shop"]]


@pytest.mark.parametrize("explicit_null", [False, True])
def test_run_saves_null_when_app_commit_is_unavailable(server, explicit_null):
    settings = config()
    if explicit_null:
        settings["app_commit"] = None
    directory, _, _ = run([make_test("list", "GET", "/api/products")], settings)

    saved = json.loads((directory / "run.json").read_text())
    assert "app_commit" in saved
    assert saved["app_commit"] is None
    assert saved["suite_id"] == "s1"
    assert saved["spec_sha256"] is None  # Older suite metadata may lack a hash.
    assert server["resets"] == [["reset-shop"]]  # No Git lookup or fallback.


def test_credentials_use_placeholders_and_are_redacted(server):
    login = make_test(
        "login",
        "POST",
        "/api/auth/login",
        role="anonymous",
        body={"email": "{{admin.email}}", "password": "{{admin.password}}"},
    )
    directory, _, results = run([login])
    assert results[0]["outcome"] == "passed"
    # The saved request keeps the placeholders; the token in the response is removed.
    assert results[0]["request"]["body"]["password"] == "{{admin.password}}"
    text = (directory / "results.json").read_text() + (directory / "run.json").read_text()
    assert PASSWORD not in text
    assert TOKEN not in text
    assert "[REDACTED" in results[0]["actual"]["body_excerpt"]


def test_response_schema_mismatch(server):
    server["handler"]["value"] = lambda r: (
        httpx.Response(200, json={"items": []}) if r.url.path != "/api/auth/login" else shop(r)
    )
    _, _, results = run([make_test("list", "GET", "/api/products")])
    assert results[0]["outcome"] == "failed"
    assert results[0]["detail"].startswith("response does not match its schema at (root)")


def test_unreachable_application_does_not_stop_other_tests(server):
    def flaky(request):
        if request.url.path == "/api/auth/login":
            return shop(request)
        if request.headers.get("X-Never") is None and request.method == "GET":
            raise httpx.ConnectError("refused", request=request)
        return shop(request)

    server["handler"]["value"] = flaky
    tests = [
        make_test("list", "GET", "/api/products"),
        make_test("create", "POST", "/api/products", expected=201, body={"name": "A", "price": 1}),
    ]
    _, _, results = run(tests)
    assert results[0]["category"] == "infrastructure_error"
    assert results[1]["outcome"] == "passed"


def test_run_time_limit_marks_remaining_tests(server, monkeypatch):
    from types import SimpleNamespace

    now = 100.0
    clock = SimpleNamespace(monotonic=lambda: now)
    monkeypatch.setattr("apiguard.runner.time", clock)

    def slow_shop(request):
        nonlocal now
        if request.url.path == "/api/products":
            now += 2
        return shop(request)

    server["handler"]["value"] = slow_shop
    settings = config()
    settings["timeouts"]["run_seconds"] = 1
    tests = [
        make_test("first", "GET", "/api/products"),
        make_test("second", "GET", "/api/products"),
    ]
    _, summary, results = run(tests, settings)

    assert [(r["id"], r["outcome"]) for r in results] == [
        ("first", "passed"),
        ("second", "not_run"),
    ]
    assert summary["outcomes"] == {"passed": 1, "not_run": 1}


def test_failed_reset_stops_the_run(server, monkeypatch):
    def failing(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("apiguard.runner.subprocess.run", failing)
    with pytest.raises(RunError, match="resetting the application data failed"):
        run([make_test("list", "GET", "/api/products")])


def test_get_token(server):
    assert get_token(config(), "admin") == TOKEN
    with pytest.raises(RunError, match="SHOP_MANAGER_EMAIL is not set"):
        get_token(config(), "manager")


def test_load_suite(tmp_path):
    with pytest.raises(RunError, match="no saved suite for shop"):
        load_suite(tmp_path, "shop")
    suite = tmp_path / "shop" / "s1"
    suite.mkdir(parents=True)
    (suite / "suite.json").write_text('{"suite_id": "s1"}')
    (suite / "tests.json").write_text("[]")
    (tmp_path / "shop" / "LATEST").write_text("s1\n")
    directory, metadata, tests = load_suite(tmp_path, "shop")
    assert (directory, metadata, tests) == (suite, {"suite_id": "s1"}, [])


def test_each_request_uses_a_fresh_connection(server, monkeypatch):
    # FastAPI closes the connection after a server error; reusing it fails the next test.
    created = []

    def client(**kwargs):
        created.append(kwargs)
        return REAL_CLIENT(transport=httpx.MockTransport(shop), **kwargs)

    monkeypatch.setattr("apiguard.runner.httpx.Client", client)
    run([make_test("list", "GET", "/api/products")])
    assert created[0]["limits"].max_keepalive_connections == 0


def test_failures_are_redacted_before_the_ai_model_sees_them(server, monkeypatch):
    from test_generation import FakeAnthropic

    from apiguard.ai import AIClient
    from apiguard.classifier import UNCLASSIFIED

    monkeypatch.setattr("apiguard.classifier.classify", lambda result: (UNCLASSIFIED, None))
    server["handler"]["value"] = lambda r: (
        shop(r) if r.url.path == "/api/auth/login" else httpx.Response(500, text=PASSWORD + TOKEN)
    )
    answer = json.dumps({"classifications": [{"id": "list", "category": "unexpected_status"}]})
    fake = FakeAnthropic([(answer, "end_turn")])
    ai = AIClient("claude-opus-5-5", {}, client=fake)
    _, summary, results = run_suite(
        config(),
        {"suite_id": "s1"},
        [make_test("list", "GET", "/api/products")],
        OPERATIONS,
        "runs",
        ai=ai,
    )
    prompt = fake.requests[0]["messages"][0]["content"]
    assert PASSWORD not in prompt
    assert TOKEN not in prompt
    assert results[0]["classified_by"] == "ai"
    assert summary["ai_model_used"] is True
    assert summary["ai_usage"]["calls"] == 1
    assert summary["categories"] == {"unexpected_status": 1}


def test_run_without_ai_records_no_ai_use(server):
    _, summary, _ = run([make_test("list", "GET", "/api/products")])
    assert summary["ai_model_used"] is False
    assert summary["ai_usage"] is None


def jwt(claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{payload}.c2lnbmF0dXJl"


def test_expired_token_is_refreshed(server, monkeypatch):
    issued = []

    def expiring(request):
        if request.url.path == "/api/auth/login":
            # Each token expires 10 seconds after it is issued: inside the refresh margin.
            issued.append(jwt({"sub": "1", "exp": int(time.time()) + 10, "n": len(issued)}))
            return httpx.Response(200, json={"data": {"access_token": issued[-1]}})
        if request.headers.get("Authorization") != f"Bearer {issued[-1]}":
            return httpx.Response(401, json={"detail": "Token expired"})
        return httpx.Response(200, json={"data": []})

    server["handler"]["value"] = expiring
    tests = [make_test("one", "GET", "/api/products"), make_test("two", "GET", "/api/products")]
    _, _, results = run(tests)
    assert [r["outcome"] for r in results] == ["passed", "passed"]
    assert len(issued) == 2


def test_token_without_expiry_is_reused(server):
    tests = [make_test("one", "GET", "/api/products"), make_test("two", "GET", "/api/products")]
    _, summary, _ = run(tests)
    assert summary["requests"] == 3  # One login and two tests.


def test_no_credential_in_any_saved_or_shown_output(server, monkeypatch, capsys):
    """NFR-04: search every report and log for the test credentials."""
    api_key = "sk-ant-test-key-0001"
    monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)

    def leaky(request):
        if request.url.path == "/api/auth/login":
            return shop(request)
        # A faulty API that echoes the credentials and the token back.
        text = f"{PASSWORD} {api_key} {request.headers.get('Authorization')}"
        return httpx.Response(500, text=text)

    server["handler"]["value"] = leaky
    _, summary, results = run([make_test("list", "GET", "/api/products")])
    print(format_run(summary, results))

    saved = "".join(path.read_text() for path in Path("runs").rglob("*") if path.is_file())
    assert "[REDACTED" in saved
    for text in (saved, capsys.readouterr().out):
        for secret in (PASSWORD, api_key, TOKEN):
            assert secret not in text
