"""SQLAlchemy 2.x ORM models (spec section 27).

Tables map directly to the spec's core tables. JSON columns hold the typed
Pydantic payloads (validated on the way in/out by the repositories) so the
schema stays stable while the domain models evolve. Works identically on SQLite
and PostgreSQL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from modelforge.common.timeutil import utcnow


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class RunModel(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), default="practice")
    status: Mapped[str] = mapped_column(String(48), default="CREATED")
    competition_profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_profile: Mapped[str] = mapped_column(String(32), default="standard")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_state_version: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    total_runtime_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    state_versions: Mapped[list[RunStateVersionModel]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class RunStateVersionModel(Base):
    __tablename__ = "run_state_versions"
    __table_args__ = (UniqueConstraint("run_id", "version_number", name="uq_run_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    state_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    change_reason: Mapped[str] = mapped_column(Text, default="")

    run: Mapped[RunModel] = relationship(back_populates="state_versions")


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    actor_type: Mapped[str] = mapped_column(String(16), default="system")
    actor_id: Mapped[str] = mapped_column(String(64), default="system")
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(48), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    storage_uri: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(96), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    experiment_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ExperimentModel(Base):
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    strategy_id: Mapped[str] = mapped_column(String(96))
    experiment_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    seed: Mapped[int] = mapped_column(Integer, default=42)
    code_artifact_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    input_manifest_hash: Mapped[str] = mapped_column(String(64), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    runtime_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    sandbox_backend: Mapped[str] = mapped_column(String(24), default="subprocess")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class EvidenceClaimModel(Base):
    __tablename__ = "evidence_claims"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    claim_type: Mapped[str] = mapped_column(String(40))
    statement: Mapped[str] = mapped_column(Text)
    verification_status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="system")
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CitationModel(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(Text)
    doi: Mapped[str] = mapped_column(String(255), default="")
    verification_status: Mapped[str] = mapped_column(String(24), default="UNRESOLVED")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class CheckpointModel(Base):
    __tablename__ = "checkpoints"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    status: Mapped[str] = mapped_column(String(24), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelCallModel(Base):
    __tablename__ = "model_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    agent_name: Mapped[str] = mapped_column(String(64))
    model_provider: Mapped[str] = mapped_column(String(48))
    model_identifier: Mapped[str] = mapped_column(String(96), default="")
    prompt_version: Mapped[str] = mapped_column(String(48), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExportModel(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    artifact_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


ALL_MODELS = [
    RunModel,
    RunStateVersionModel,
    AuditEventModel,
    ArtifactModel,
    ExperimentModel,
    EvidenceClaimModel,
    CitationModel,
    CheckpointModel,
    ModelCallModel,
    ExportModel,
]
