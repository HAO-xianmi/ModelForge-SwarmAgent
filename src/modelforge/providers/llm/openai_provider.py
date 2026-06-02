"""OpenAI-compatible provider (spec milestone 5).

Uses the chat-completions HTTP API via httpx (no SDK dependency), so any
OpenAI-compatible endpoint works by setting ``OPENAI_BASE_URL``. Network- and
credential-dependent; not exercised in offline CI. The mock provider is the
default.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

from modelforge.common.config import get_settings
from modelforge.common.errors import ModelProviderError
from modelforge.providers.llm.base import LLMResponse, Message, TokenUsage

# Rough public price per 1K tokens (USD); override per deployment as needed.
_DEFAULT_PRICE_PER_1K = {"input": 0.0005, "output": 0.0015}


class OpenAICompatibleProvider:
    name = "openai"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        s = get_settings()
        self.model = model or s.llm_model or "gpt-4o-mini"
        key = api_key or s.openai_api_key
        self.base_url = s.openai_base_url.rstrip("/")
        if not key:
            raise ModelProviderError("OPENAI_API_KEY is not set")
        self.api_key: str = key

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        payload: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_schema is not None:
            payload["response_format"] = {"type": "json_object"}
        start = time.monotonic()
        try:
            resp = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=60.0,
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ModelProviderError(
                "OpenAI request failed", context={"error": str(exc)}
            ) from exc
        latency = int((time.monotonic() - start) * 1000)
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
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
