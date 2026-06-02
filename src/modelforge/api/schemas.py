"""API request/response schemas (spec 26 / Appendix E)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    mode: str = "practice"
    competition_profile_id: str = "practice"
    budget_profile: str = "standard"


class CreateRunResponse(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    mode: str
    status: str
    competition_profile_id: str | None = None
    current_state_version: int
    total_cost_estimate: float = 0.0
    total_runtime_seconds: float = 0.0


class ResolveCheckpointRequest(BaseModel):
    action: str = Field(description="APPROVE | APPROVE_WITH_EDITS | REJECT_AND_RETRY | "
                        "RETURN_TO_STAGE | CANCEL_RUN")
    comments: str = ""
    edits: dict = Field(default_factory=dict)
    user_id: str = "user"


class ExportRequest(BaseModel):
    kind: str = "bundle"


class StructuredError(BaseModel):
    error: str
    detail: str
    failure_type: str | None = None
    context: dict = Field(default_factory=dict)
