"""Custom exception hierarchy for ModelForge-Swarm.

All recoverable failures should raise a subclass of :class:`ModelForgeError` so
that the control plane can classify them (see the failure types in spec 32.1)
and never silently swallow errors (working rule 5).
"""

from __future__ import annotations

from enum import StrEnum


class FailureType(StrEnum):
    """Failure categories from architecture spec section 32.1."""

    INPUT_FAILURE = "INPUT_FAILURE"
    PARSING_FAILURE = "PARSING_FAILURE"
    MODEL_PROVIDER_FAILURE = "MODEL_PROVIDER_FAILURE"
    SANDBOX_FAILURE = "SANDBOX_FAILURE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    CODE_FAILURE = "CODE_FAILURE"
    QUALITY_GATE_FAILURE = "QUALITY_GATE_FAILURE"
    CITATION_FAILURE = "CITATION_FAILURE"
    EXPORT_FAILURE = "EXPORT_FAILURE"
    BUDGET_FAILURE = "BUDGET_FAILURE"
    POLICY_FAILURE = "POLICY_FAILURE"
    USER_CANCELLED = "USER_CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ModelForgeError(Exception):
    """Base class for all ModelForge-Swarm errors.

    Attributes:
        failure_type: structured classification used by the control plane.
        detail: human-readable explanation, safe to surface to a reviewer.
        context: optional structured context for debugging/audit.
    """

    failure_type: FailureType = FailureType.INTERNAL_ERROR

    def __init__(self, detail: str, *, context: dict | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.context = context or {}

    def to_dict(self) -> dict:
        return {
            "error": type(self).__name__,
            "failure_type": self.failure_type.value,
            "detail": self.detail,
            "context": self.context,
        }


class ConfigurationError(ModelForgeError):
    failure_type = FailureType.INTERNAL_ERROR


class InputError(ModelForgeError):
    failure_type = FailureType.INPUT_FAILURE


class ParsingError(ModelForgeError):
    failure_type = FailureType.PARSING_FAILURE


class ModelProviderError(ModelForgeError):
    failure_type = FailureType.MODEL_PROVIDER_FAILURE


class SchemaValidationError(ModelForgeError):
    """Raised when an LLM output cannot be parsed into its typed schema."""

    failure_type = FailureType.MODEL_PROVIDER_FAILURE


class SandboxError(ModelForgeError):
    failure_type = FailureType.SANDBOX_FAILURE


class SandboxPolicyError(SandboxError):
    """Raised when sandbox code attempts a prohibited action (e.g., path escape)."""

    failure_type = FailureType.POLICY_FAILURE


class DependencyError(ModelForgeError):
    failure_type = FailureType.DEPENDENCY_FAILURE


class CodeExecutionError(ModelForgeError):
    failure_type = FailureType.CODE_FAILURE


class QualityGateError(ModelForgeError):
    failure_type = FailureType.QUALITY_GATE_FAILURE


class CitationError(ModelForgeError):
    failure_type = FailureType.CITATION_FAILURE


class ExportError(ModelForgeError):
    failure_type = FailureType.EXPORT_FAILURE


class BudgetExceededError(ModelForgeError):
    failure_type = FailureType.BUDGET_FAILURE


class PolicyViolationError(ModelForgeError):
    failure_type = FailureType.POLICY_FAILURE


class RunCancelledError(ModelForgeError):
    failure_type = FailureType.USER_CANCELLED


class RetryExhaustedError(ModelForgeError):
    """Raised when a bounded retry loop exhausts its budget (spec 4.6)."""

    failure_type = FailureType.INTERNAL_ERROR
