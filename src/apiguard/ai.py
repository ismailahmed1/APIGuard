"""Call the AI model with configurable call, token and cost limits, and record its usage."""

import json
import time
from dataclasses import asdict, dataclass

import anthropic

# USD per million tokens: input, output, cache write (5 minutes), cache read.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
}
# Models that accept the server-side fallback, which reruns a declined request on another model.
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AIError(Exception):
    """A model call failed in a way that we can explain to the user."""


class LimitReached(AIError):
    """A configured call, token or cost limit stops further model calls."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    seconds: float = 0.0

    def cost(self, model):
        """Estimated cost in USD, or None for a model without a known price."""
        if model not in PRICES:
            return None
        price_in, price_out, price_write, price_read = PRICES[model]
        total = (
            self.input_tokens * price_in
            + self.output_tokens * price_out
            + self.cache_write_tokens * price_write
            + self.cache_read_tokens * price_read
        )
        return round(total / 1_000_000, 4)

    def as_dict(self, model):
        return {**asdict(self), "seconds": round(self.seconds, 1), "cost_usd": self.cost(model)}


class AIClient:
    def __init__(self, model, limits, effort="medium", client=None):
        self.model = model
        self.effort = effort
        self.max_calls = limits.get("max_calls")
        self.max_output_tokens = limits.get("max_output_tokens")
        self.max_cost_usd = limits.get("max_cost_usd")
        self.usage = Usage()
        self._client = client

    @property
    def client(self):
        # Created on first use, so commands that never call the model need no API key.
        if self._client is None:
            self._client = anthropic.Anthropic()
        return self._client

    def check_limits(self):
        if self.max_calls is not None and self.usage.calls >= self.max_calls:
            raise LimitReached(f"the limit of {self.max_calls} model calls was reached")
        if (
            self.max_output_tokens is not None
            and self.usage.output_tokens >= self.max_output_tokens
        ):
            raise LimitReached(f"the limit of {self.max_output_tokens} output tokens was reached")
        cost = self.usage.cost(self.model)
        if self.max_cost_usd is not None and cost is not None and cost >= self.max_cost_usd:
            raise LimitReached(f"the estimated cost limit of ${self.max_cost_usd} was reached")

    def generate_json(self, system, prompt, schema, max_tokens=32000):
        """Return the model's answer as an object that matches the JSON schema."""
        self.check_limits()
        request = {
            "model": self.model,
            "max_tokens": max_tokens,
            # The system prompt is identical for every call in a run, so it is cached.
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
        }
        if self.model in FALLBACK_MODELS:
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = "default"

        start = time.monotonic()
        try:
            with self.client.beta.messages.stream(**request) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise AIError("the AI model rejected the API key; check ANTHROPIC_API_KEY") from exc
        except anthropic.RateLimitError as exc:
            raise AIError("the AI model is rate limiting requests; try again later") from exc
        except anthropic.APIStatusError as exc:
            raise AIError(f"the AI model returned HTTP {exc.status_code}") from exc
        except anthropic.APIConnectionError as exc:
            raise AIError("could not reach the AI model") from exc
        finally:
            self.usage.seconds += time.monotonic() - start

        self._record(message.usage)
        if message.stop_reason == "refusal":
            raise AIError("the AI model declined the request")
        if message.stop_reason == "max_tokens":
            raise AIError("the AI model's answer was cut off by the output token limit")
        text = next((block.text for block in message.content if block.type == "text"), None)
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise AIError("the AI model did not return valid JSON") from exc

    def _record(self, usage):
        self.usage.calls += 1
        self.usage.input_tokens += usage.input_tokens or 0
        self.usage.output_tokens += usage.output_tokens or 0
        self.usage.cache_write_tokens += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.usage.cache_read_tokens += getattr(usage, "cache_read_input_tokens", 0) or 0
