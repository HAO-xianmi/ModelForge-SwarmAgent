"""LLM provider selection from configuration (spec 33.2 routing)."""

from __future__ import annotations

from modelforge.common.config import LLMBackend, get_settings
from modelforge.providers.llm.base import LLMProvider
from modelforge.providers.llm.mock import MockProvider


def get_llm_provider(backend: LLMBackend | None = None) -> LLMProvider:
    chosen = backend or get_settings().llm
    if chosen is LLMBackend.OPENAI:
        from modelforge.providers.llm.openai_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider()
    if chosen is LLMBackend.ANTHROPIC:
        from modelforge.providers.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    return MockProvider()
