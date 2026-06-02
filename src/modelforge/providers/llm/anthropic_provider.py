"""Anthropic provider (spec milestone 5).

Uses the Messages API via httpx. System messages are hoisted into the top-level
``system`` field per the Anthropic API. Network/credential-dependent; the mock
provider is the default for offline CI.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

from modelforge.common.config import get_settings
from modelforge.common.errors import ModelProviderError
from modelforge.providers.llm.base import LLMResponse, Message, TokenUsage

_DEFAULT_PRICE_PER_1K = {"input": 0.003, "output": 0.015}
_API_URL = "https://api.anthropic.com/v1/messages"
_API_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        s = get_settings()
        self.model = model or s.llm_model or "claude-sonnet-4-6"
        key = api_key or s.anthropic_api_key
        if not key:
            raise ModelProviderError("ANTHROPIC_API_KEY is not set")
        self.api_key: str = key

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        system = "\n".join(m.content for m in messages if m.role == "system")
        chat = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]
        payload: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": chat,
        }
        if system:
            payload["system"] = system
        start = time.monotonic()
        try:
            resp = httpx.post(
                _API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": _API_VERSION,
                    "content-type": "application/json",
                },
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelProviderError(
                "Anthropic request failed", context={"error": str(exc)}
            ) from exc
        latency = int((time.monotonic() - start) * 1000)
        data = resp.json()
        text = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        in_tok = int(usage.get("input_tokens", 0))
        out_tok = int(usage.get("output_tokens", 0))
        cost = (
            in_tok / 1000 * _DEFAULT_PRICE_PER_1K["input"]
            + out_tok / 1000 * _DEFAULT_PRICE_PER_1K["output"]
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
            latency_ms=latency,
            estimated_cost=cost,
        )
