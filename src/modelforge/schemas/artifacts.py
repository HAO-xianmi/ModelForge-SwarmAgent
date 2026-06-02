"""Artifact registry records, audit events, and manifests (spec 11, 10.4, 28.2)."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from modelforge.common.timeutil import utcnow
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import ActorType, ArtifactType, EventType


class ArtifactRecord(MFBaseModel):
    """Immutable reference to a generated or uploaded file (spec 11.3).

    Registered artifacts MUST NOT be modified in place; a revision creates a new
    ``artifact_id`` linked via ``source_artifact_ids`` (spec 11.4). The
    ``immutable`` flag documents this contract.
    """

    artifact_id: str
    run_id: str
    artifact_type: ArtifactType
    filename: str
    storage_uri: str
    content_hash: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str = "system"
    source_artifact_ids: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    immutable: bool = True


class AuditEvent(MFBaseModel):
    """A single audit event (spec 31.1 / 10.4).

    Every state update emits one. ``payload`` carries the structured detail; for
    STATE_UPDATED events it records prev/new version, changed fields, and reason.
    """

    event_id: str
    run_id: str
    event_type: EventType
    actor_type: ActorType = ActorType.SYSTEM
    actor_id: str = "system"
    timestamp: datetime = Field(default_factory=utcnow)
    payload: dict = Field(default_factory=dict)


class StateChange(MFBaseModel):
    """The required fields recorded on every state update (spec 10.4 rule 3)."""

    actor: str
    actor_type: ActorType
    timestamp: datetime = Field(default_factory=utcnow)
    previous_version: int
    new_version: int
    changed_fields: list[str] = Field(default_factory=list)
    reason: str


class ReproducibilityManifest(MFBaseModel):
    """Reproducibility bundle manifest (spec 18 / 28.2 / Appendix F)."""

    run_id: str
    mode: str
    competition_profile_id: str | None = None
    input_file_hashes: dict[str, str] = Field(default_factory=dict)
    code_artifact_hashes: dict[str, str] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list)
    seeds: dict[str, int] = Field(default_factory=dict)
    experiments: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    evidence_claim_ids: list[str] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    human_approvals: list[dict] = Field(default_factory=list)
    exported_at: datetime = Field(default_factory=utcnow)
