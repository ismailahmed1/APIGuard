import contextlib
import json
from types import SimpleNamespace

import pytest
from shop_spec import SHOP, raw_test

from apiguard.ai import AIClient, AIError, Usage
from apiguard.generator import TEST_SCHEMA, generate_suite, select_operations
from apiguard.openapi import LoadedSpec
from apiguard.operations import extract_operations

OPERATIONS = extract_operations(SHOP)


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


def test_generate_suite_validates_and_saves(tmp_path):
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
    assert (directory / "openapi.yaml").read_bytes() == json.dumps(SHOP).encode()
    assert (tmp_path / "shop" / "LATEST").read_text().strip() == metadata["suite_id"]


def test_limit_stops_generation_but_keeps_tests(tmp_path):
    fake = FakeAnthropic([reply(raw_test())])
    ai = AIClient("claude-opus-5-5", {"max_calls": 1}, client=fake)
    _, metadata = generate(tmp_path, ai)
    assert metadata["counts"]["valid"] == 1
    assert metadata["stopped_reason"] == "the limit of 1 model calls was reached"


@pytest.mark.parametrize(
    ("limits", "message"),
    [
        ({"max_output_tokens": 500}, "500 output tokens"),
        ({"max_cost_usd": 0.01}, r"cost limit of \$0\.01"),
    ],
)
def test_token_and_cost_limits(limits, message):
    ai = AIClient("claude-opus-5-5", limits, client=FakeAnthropic([reply(), reply()]))
    ai.generate_json("s", "p", TEST_SCHEMA)
    with pytest.raises(AIError, match=message):
        ai.generate_json("s", "p", TEST_SCHEMA)
