"""DeepSeek provider — OpenAI-compatible endpoint with DeepSeek-specific defaults.

Uses the chat-completions HTTP API via httpx (no SDK dependency).
Set DEEPSEEK_API_KEY and optionally MODELFORGE_LLM_MODEL (default: deepseek-chat).
Network- and credential-dependent; mock is the default for offline CI.
"""

from __future__ import annotations

import time

import httpx
from pydantic import BaseModel

from modelforge.common.config import get_settings
from modelforge.common.errors import ModelProviderError
from modelforge.providers.llm.base import LLMResponse, Message, TokenUsage

# DeepSeek pricing per 1K tokens (USD) as of 2025; check platform.deepseek.com for updates.
_PRICE_PER_1K = {"input": 0.00014, "output": 0.00028}


class DeepSeekProvider:
    name = "deepseek"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        s = get_settings()
        self.model = model or s.llm_model or "deepseek-chat"
        key = api_key or s.deepseek_api_key
        self.base_url = s.deepseek_base_url.rstrip("/")
        if not key:
            raise ModelProviderError("DEEPSEEK_API_KEY is not set")
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
                "DeepSeek request failed", context={"error": str(exc)}
            ) from exc
        latency = int((time.monotonic() - start) * 1000)
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        in_tok = int(usage.get("prompt_tokens", 0))
        out_tok = int(usage.get("completion_tokens", 0))
        cost = (
            in_tok / 1000 * _PRICE_PER_1K["input"]
            + out_tok / 1000 * _PRICE_PER_1K["output"]
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
            latency_ms=latency,
            estimated_cost=cost,
        )
