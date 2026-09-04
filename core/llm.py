"""Thin wrapper around the Anthropic Messages API.

The API is asked for a JSON object that conforms to a schema (structured
outputs), so the model cannot return markdown fences, prose, or a shape
that does not match. What the API cannot guarantee is that the values are
true or that the output was not cut off, so the wrapper returns the raw
text together with stop_reason and token usage and leaves validation to
the caller.

Retries for 429, 5xx and connection errors are handled by the SDK client
(max_retries). There is deliberately no second retry layer here.
"""

import logging
import os
import time
from dataclasses import dataclass

import anthropic
from anthropic import transform_schema
from pydantic import BaseModel

from core.cassettes import CassetteStore
from core.config import CLAUDE_MODEL, CLAUDE_MAX_TOKENS, CLAUDE_MAX_RETRIES

logger = logging.getLogger(__name__)

_client = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ValueError("ANTHROPIC_API_KEY is not set (environment or .env)")
        _client = anthropic.Anthropic(max_retries=CLAUDE_MAX_RETRIES)
    return _client


@dataclass
class LLMResult:
    text: str
    stop_reason: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int = 0

    @property
    def truncated(self) -> bool:
        return self.stop_reason == "max_tokens"

    @property
    def refused(self) -> bool:
        return self.stop_reason == "refusal"

    def usage(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "stop_reason": self.stop_reason,
            "latency_ms": self.latency_ms,
        }

    def to_cassette(self) -> dict:
        return {"text": self.text, "stop_reason": self.stop_reason, "model": self.model,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "latency_ms": self.latency_ms}

    @classmethod
    def from_cassette(cls, entry: dict) -> "LLMResult":
        return cls(**{k: entry[k] for k in ("text", "stop_reason", "model", "input_tokens", "output_tokens")},
                   latency_ms=entry.get("latency_ms", 0))


def extract_structured(
    system_prompt: str,
    user_message: str,
    output_model: type[BaseModel],
    model: str = CLAUDE_MODEL,
    max_tokens: int = CLAUDE_MAX_TOKENS,
) -> LLMResult:
    """Ask the model for JSON matching output_model's schema.

    Raises anthropic.APIError subclasses on transport or API failure after
    the SDK's own retries are exhausted. Never raises on truncation or
    refusal; the caller decides what those mean.
    """
    schema = transform_schema(output_model)
    store = CassetteStore.from_env()
    if store and store.mode == "replay":
        return LLMResult.from_cassette(store.load(model, system_prompt, user_message, schema))

    client = get_client()
    logger.info("Calling %s (%d chars in)", model, len(user_message))

    started = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    latency_ms = int((time.perf_counter() - started) * 1000)

    text = "".join(block.text for block in response.content if block.type == "text")
    result = LLMResult(
        text=text,
        stop_reason=response.stop_reason or "unknown",
        model=response.model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
    )
    if store and store.mode == "record":
        store.save(model, system_prompt, user_message, schema, result.to_cassette())
    return result
