"""Base agent: typed structured LLM calls with bounded retry + repair-once.

The base handles the cross-cutting concerns every agent shares (spec quality
requirements): a versioned prompt, a typed output schema, one repair attempt on
invalid output, a safe failure after retry exhaustion, and model-call accounting
(tokens/cost/latency) appended to a list the workflow persists.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

from pydantic import BaseModel

from modelforge.common.errors import SchemaValidationError
from modelforge.common.logging import get_logger
from modelforge.prompts.registry import get_prompt
from modelforge.providers.llm.base import LLMProvider, Message, parse_structured

_log = get_logger("modelforge.agents")

# Classic TypeVar/Generic form: mypy 1.11 does not fully support PEP 695
# generic classes yet. Ruff's UP046/UP047 are suppressed in pyproject for this.
TOut = TypeVar("TOut", bound=BaseModel)


@dataclass
class ModelCall:
    """A record of one LLM call for observability (spec 27.8 model_calls)."""

    agent_name: str
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    estimated_cost: float
    status: str


@dataclass
class AgentContext:
    """Shared services + accounting passed to every agent invocation."""

    run_id: str
    provider: LLMProvider
    model_calls: list[ModelCall] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.model_calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.model_calls)

    @property
    def total_cost(self) -> float:
        return sum(c.estimated_cost for c in self.model_calls)


@dataclass
class AgentResult(Generic[TOut]):
    """Outcome of an agent run: either ``output`` or a ``failure`` reason."""

    output: TOut | None
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.output is not None and self.failure is None


class BaseAgent(Generic[TOut]):
    """Common machinery for structured LLM agents.

    Subclasses set ``agent_key`` (matching the prompt registry + mock dispatch)
    and ``output_schema``, then call :meth:`run_structured` with a context dict.
    """

    agent_key: str = ""
    output_schema: type[TOut]

    def __init__(self, ctx: AgentContext) -> None:
        self.ctx = ctx
        self.prompt = get_prompt(self.agent_key)

    @property
    def name(self) -> str:
        return self.prompt.agent_name

    def run_structured(
        self,
        context: dict,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> AgentResult[TOut]:
        """Call the provider once, with a single repair retry on bad output."""
        system, user = self.prompt.render(self.agent_key, context)
        messages = [Message(role="system", content=system), Message(role="user", content=user)]

        last_error: str | None = None
        for attempt in range(2):  # bounded: 1 initial + 1 repair (spec 37.2)
            response = self.ctx.provider.complete(
                messages, temperature=temperature, max_tokens=max_tokens,
                response_schema=self.output_schema,
            )
            self.ctx.model_calls.append(
                ModelCall(
                    agent_name=self.name,
                    provider=response.provider,
                    model=response.model,
                    prompt_version=self.prompt.version,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    latency_ms=response.latency_ms,
                    estimated_cost=response.estimated_cost,
                    status="ok",
                )
            )
            try:
                output = parse_structured(response.text, self.output_schema)
                return AgentResult(output=output)
            except SchemaValidationError as exc:
                last_error = exc.detail
                _log.warning(
                    "%s output invalid (attempt %d): %s", self.name, attempt + 1, exc.detail
                )
                # On the repair attempt, append a corrective user message.
                if attempt == 0:
                    messages.append(
                        Message(
                            role="user",
                            content=(
                                "Your previous response was not valid for the required "
                                f"schema ({exc.detail}). Respond again with ONLY a valid "
                                "JSON object matching the schema."
                            ),
                        )
                    )

        return AgentResult(output=None, failure=f"schema validation failed: {last_error}")
