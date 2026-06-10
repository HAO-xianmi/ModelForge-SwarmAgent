"""LLM provider Protocol, message/response models, and the structured-output
helper with one repair attempt (spec 37.2).
"""

from __future__ import annotations

import json
import re
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from modelforge.common.errors import SchemaValidationError
from modelforge.schemas.base import MFBaseModel

T = TypeVar("T", bound=BaseModel)


class Message(MFBaseModel):
    role: str  # system | user | assistant
    content: str


class TokenUsage(MFBaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class LLMResponse(MFBaseModel):
    text: str
    model: str
    provider: str
    usage: TokenUsage = TokenUsage()
    latency_ms: int = 0
    estimated_cost: float = 0.0


@runtime_checkable
class LLMProvider(Protocol):
    """Vendor-neutral chat completion interface."""

    name: str
    model: str

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Return a completion. ``response_schema`` hints JSON output shape."""
        ...


# --------------------------------------------------------------------------- #
# Structured output helper
# --------------------------------------------------------------------------- #
_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON object/array from a model response (fenced or bare)."""
    m = _JSON_BLOCK.search(text)
    if m:
        return m.group(1)
    # All current agent schemas are JSON objects. Prefer object starts so a
    # stray explanatory "[...]" does not get selected before the real payload.
    decoder = json.JSONDecoder()
    for opening in ("{", "["):
        start = text.find(opening)
        while start != -1:
            try:
                _, end = decoder.raw_decode(text[start:])
                return text[start : start + end]
            except json.JSONDecodeError:
                start = text.find(opening, start + 1)
    return text


def parse_structured(text: str, schema: type[T]) -> T:
    """Parse model text into ``schema`` or raise SchemaValidationError."""
    raw = extract_json(text)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SchemaValidationError(
            "model output is not valid JSON", context={"error": str(exc), "raw": raw[:500]}
        ) from exc
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(
            "model output does not match schema",
            context={"errors": exc.errors(include_url=False)[:5], "schema": schema.__name__},
        ) from exc
