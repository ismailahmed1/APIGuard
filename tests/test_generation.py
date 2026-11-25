import contextlib
import hashlib
import json
from types import SimpleNamespace

import pytest
from shop_spec import SHOP, raw_test

from apiguard.ai import AIClient, AIError, LimitReached, Usage
from apiguard.generator import TEST_SCHEMA, generate_suite, select_operations
from apiguard.openapi import LoadedSpec
from apiguard.operations import extract_operations

OPERATIONS = extract_operations(SHOP)


@pytest.fixture(autouse=True)
def no_real_ai_client(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    def unexpected_client(*args, **kwargs):
        pytest.fail("Generation tests must inject a fake AI client.")

    monkeypatch.setattr("apiguard.ai.anthropic.Anthropic", unexpected_client)


class FakeAnthropic:
    """Records requests and answers each one with the next prepared reply."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self.stream))

    @contextlib.contextmanager
    def stream(self, **request):
        self.requests.append(request)
        text, stop_reason = self.replies.pop(0)
        usage = SimpleNamespace(
            input_tokens=1000,
            output_tokens=500,
            cache_creation_input_tokens=2000,
            cache_read_input_tokens=0,
        )
        message = SimpleNamespace(
            stop_reason=stop_reason,
            usage=usage,
            content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        )
        yield SimpleNamespace(get_final_message=lambda: message)


def reply(*tests, stop_reason="end_turn"):
    return json.dumps({"tests": list(tests)}), stop_reason


def test_generate_json_sends_structured_output_request():
    fake = FakeAnthropic([reply(raw_test())])
    ai = AIClient("claude-opus-5-5", {}, client=fake)
    assert ai.generate_json("system text", "prompt", TEST_SCHEMA) == {"tests": [raw_test()]}

    request = fake.requests[0]
    assert request["model"] == "claude-opus-5-5"
    assert request["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert request["output_config"]["format"] == {"type": "json_schema", "schema": TEST_SCHEMA}
    assert request["output_config"]["effort"] == "medium"
    assert request["fallbacks"] == "default"
    assert ai.usage.calls == 1
    # 1000 x $4 + 500 x $20 + 2000 x $5 per million tokens.
    assert ai.usage.cost("claude-opus-5-5") == 0.024


def test_models_without_fallback_support_send_no_fallback():
    fake = FakeAnthropic([reply()])
    AIClient("claude-haiku-5-5", {}, client=fake).generate_json("s", "p", TEST_SCHEMA)
    assert "fallbacks" not in fake.requests[0]
    assert Usage(input_tokens=10).cost("claude-haiku-5-5") is None


@pytest.mark.parametrize(
    ("answer", "message"),
    [
        (("{}", "refusal"), "declined"),
        (('{"tests": [', "max_tokens"), "cut off"),
        (("not json", "end_turn"), "did not return valid JSON"),
    ],
)
def test_unusable_answers(answer, message):
    ai = AIClient("claude-opus-5-5", {}, client=FakeAnthropic([answer]))
    with pytest.raises(AIError, match=message):
        ai.generate_json("s", "p", TEST_SCHEMA)
    assert ai.usage.calls == 1  # A failed answer still counts towards the limits.


def test_select_operations_by_tag():
    assert [op.path for op in select_operations(OPERATIONS, ["auth"])] == ["/api/auth/login"]
    assert len(select_operations(OPERATIONS, [])) == len(OPERATIONS)


def generate(tmp_path, ai, tags=("Products", "Auth")):
    spec = LoadedSpec(document=SHOP, raw=json.dumps(SHOP).encode())
    return generate_suite(
        "shop", spec, OPERATIONS, list(tags), ai, "Seed data.", ["admin"], tmp_path
    )


def test_generate_suite_validates_and_saves(tmp_path, monkeypatch):
    login = raw_test(
        id="auth-001",
        path="/api/auth/login",
        role="anonymous",
        body_json='{"email": "{{admin.email}}", "password": "{{admin.password}}"}',
        expected_status=200,
    )
    # Tags are generated in specification order: Auth, then Products.
    fake = FakeAnthropic(
        [reply(login), reply(raw_test(), raw_test(id="products-002", path="/api/nowhere"))]
    )
    # Shared monotonic clock: loop start, each request's start/end, loop end.
    ticks = iter([0, 1, 2.5, 3, 5, 6])
    monkeypatch.setattr("apiguard.ai.time.monotonic", lambda: next(ticks))
    directory, metadata = generate(tmp_path, AIClient("claude-opus-5-5", {}, client=fake))

    # One call per tag; the cached system prompt includes the application context.
    assert len(fake.requests) == 2
    assert "Seed data." in fake.requests[0]["system"][0]["text"]
    assert "'auth-'" in fake.requests[0]["messages"][0]["content"]
    assert "'products-'" in fake.requests[1]["messages"][0]["content"]
    assert metadata["counts"] == {"generated": 3, "valid": 2, "excluded": 1}
    assert metadata["ai_usage"]["calls"] == 2
    assert metadata["operations"] == ["POST /api/auth/login", "GET /api/products"] + [
        "POST /api/products",
        "DELETE /api/products/{product_id}",
    ]
    tests = json.loads((directory / "tests.json").read_text())
    assert [t["id"] for t in tests] == ["auth-001", "products-001"]
    excluded = json.loads((directory / "excluded.json").read_text())
    assert excluded[0]["reason"] == "no operation POST /api/nowhere in the specification"
    snapshot = (directory / "openapi.yaml").read_bytes()
    assert snapshot == json.dumps(SHOP).encode()

    expected_hash = hashlib.sha256(snapshot).hexdigest()
    saved_hash = (directory / "openapi.sha256").read_text(encoding="ascii").strip()
    saved_suite = json.loads((directory / "suite.json").read_text(encoding="utf-8"))
    assert saved_hash == expected_hash
    assert saved_suite["spec_sha256"] == expected_hash
    assert saved_suite == metadata
    assert saved_suite["generation_seconds"] == 6.0
    assert saved_suite["ai_usage"] == {
        "calls": 2,
        "input_tokens": 2000,
        "output_tokens": 1000,
        "cache_write_tokens": 4000,
        "cache_read_tokens": 0,
        "seconds": 3.5,
        "cost_usd": 0.048,
    }
    assert (tmp_path / "shop" / "LATEST").read_text().strip() == metadata["suite_id"]


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"max_calls": 1}, "the limit of 1 model calls was reached"),
        ({"max_output_tokens": 500}, "the limit of 500 output tokens was reached"),
        ({"max_output_tokens": 499}, "the limit of 499 output tokens was reached"),
        ({"max_cost_usd": 0.024}, "the estimated cost limit of $0.024 was reached"),
        ({"max_cost_usd": 0.01}, "the estimated cost limit of $0.01 was reached"),
    ],
)
def test_limit_stops_generation_but_keeps_tests(tmp_path, limits, reason):
    fake = FakeAnthropic([reply(raw_test()), reply(raw_test(id="products-002"))])
    ai = AIClient("claude-opus-5-5", limits, client=fake)
    directory, metadata = generate(tmp_path, ai)
    assert len(fake.requests) == 1
    assert metadata["counts"] == {"generated": 1, "valid": 1, "excluded": 0}
    assert metadata["stopped_reason"] == reason
    saved_tests = json.loads((directory / "tests.json").read_text())
    assert [test["id"] for test in saved_tests] == ["products-001"]
    saved_suite = json.loads((directory / "suite.json").read_text())
    assert saved_suite == metadata
    assert saved_suite["ai_usage"]["calls"] == 1
    assert saved_suite["ai_usage"]["output_tokens"] == 500
    assert saved_suite["ai_usage"]["cost_usd"] == 0.024


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        ({"max_output_tokens": 500}, "500 output tokens"),
        ({"max_cost_usd": 0.01}, r"cost limit of \$0\.01"),
    ],
)
def test_token_and_cost_limits(limits, message):
    fake = FakeAnthropic([reply(), reply()])
    ai = AIClient("claude-opus-5-5", limits, client=fake)
    ai.generate_json("s", "p", TEST_SCHEMA)
    with pytest.raises(LimitReached, match=message):
        ai.generate_json("s", "p", TEST_SCHEMA)
    assert len(fake.requests) == 1
