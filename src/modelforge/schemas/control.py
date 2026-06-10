"""Control-plane schemas: competition profiles, checkpoints, budgets, failures.

Spec references: 7 (control plane), 24 (compliance/profiles), 25 (checkpoints),
32 (failure/recovery), 5 (operating modes).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from modelforge.common.errors import FailureType
from modelforge.common.timeutil import utcnow
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import (
    CheckpointAction,
    CheckpointId,
    CheckpointStatus,
)


# --------------------------------------------------------------------------- #
# Competition profile (spec 24.2 / Appendix C)
# --------------------------------------------------------------------------- #
class CompetitionProfile(MFBaseModel):
    profile_id: str
    competition_name: str
    rule_version: str = "1.0"
    operating_mode: str = "practice"  # practice | contest_compliant | research
    allowed_capabilities: dict[str, bool] = Field(default_factory=dict)
    prohibited_tools: list[str] = Field(default_factory=list)
    required_checkpoints: list[str] = Field(default_factory=list)
    required_disclosure_fields: list[str] = Field(default_factory=list)
    restricted_actions: list[str] = Field(default_factory=list)
    notes: str = ""
    source_reference: str = ""

    def capability_enabled(self, name: str) -> bool:
        # Default-allow in practice mode; default-deny otherwise unless listed.
        if name in self.allowed_capabilities:
            return self.allowed_capabilities[name]
        return self.operating_mode == "practice"

    def action_restricted(self, action: str) -> bool:
        return action in self.restricted_actions


# --------------------------------------------------------------------------- #
# Checkpoints (spec 25)
# --------------------------------------------------------------------------- #
class Checkpoint(MFBaseModel):
    checkpoint_id: str  # CheckpointId value, possibly suffixed for retries
    kind: CheckpointId
    run_id: str
    status: CheckpointStatus = CheckpointStatus.PENDING
    context: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow)
    resolved_at: datetime | None = None
    action: CheckpointAction | None = None
    actor_id: str | None = None
    comments: str = ""
    edited_fields: dict = Field(default_factory=dict)
    previous_state_version: int | None = None
    new_state_version: int | None = None


class HumanFeedback(MFBaseModel):
    checkpoint_id: str
    user_id: str
    action: CheckpointAction
    comments: str = ""
    edits: dict = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Budgets & loop protection (spec 7.3 / 14.4)
# --------------------------------------------------------------------------- #
class BudgetState(MFBaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    sandbox_runtime_seconds: float = 0.0
    model_revision_count: int = 0
    code_debug_count: int = 0
    report_revision_count: int = 0
    paper_revision_count: int = 0
    method_reroute_count: int = 0
    judge_retry_count: int = 0
    max_quality_revisions: int = 2
    citation_retry_count: int = 0
    total_loop_count: int = 0
    warnings: list[str] = Field(default_factory=list)

    def add_tokens(self, in_tokens: int, out_tokens: int, cost: float) -> None:
        self.input_tokens += in_tokens
        self.output_tokens += out_tokens
        self.estimated_cost_usd += cost


# --------------------------------------------------------------------------- #
# Disclosure (spec 24.4)
# --------------------------------------------------------------------------- #
class DisclosureInteraction(MFBaseModel):
    provider: str
    model_identifier: str
    purpose: str
    stage: str
    summary: str = ""
    human_edits: bool = False
    human_confirmation: bool = False


class DisclosureRecord(MFBaseModel):
    run_id: str
    interactions: list[DisclosureInteraction] = Field(default_factory=list)
    exported_at: datetime = Field(default_factory=utcnow)


# --------------------------------------------------------------------------- #
# Failure & export state (spec 32)
# --------------------------------------------------------------------------- #
class FailureState(MFBaseModel):
    failure_type: FailureType
    stage: str
    detail: str
    logs: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    escalated: bool = False
    timestamp: datetime = Field(default_factory=utcnow)


class ExportState(MFBaseModel):
    bundle_artifact_id: str | None = None
    bundle_path: str | None = None
    disclosure_required: bool = False
    disclosure_artifact_id: str | None = None
    exported_at: datetime | None = None
    exports: list[dict] = Field(default_factory=list)
