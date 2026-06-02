"""Artifact Registry (spec 11) — a core foundation component.

Responsibilities:
  * Persist bytes/text to the object store under the run directory.
  * Record an immutable :class:`ArtifactRecord` with a content hash.
  * Enforce immutability: registered artifacts are never modified in place; a
    revision creates a NEW artifact_id linked to the prior one (spec 11.4).
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from sqlalchemy import select

from modelforge.common.errors import InputError
from modelforge.common.hashing import hash_bytes
from modelforge.common.ids import new_artifact_id
from modelforge.schemas.artifacts import ArtifactRecord
from modelforge.schemas.enums import ArtifactType
from modelforge.storage.database import Database
from modelforge.storage.models import ArtifactModel
from modelforge.storage.object_store import LocalObjectStore

# Default run-subdirectory for each artifact type (spec 28.1 layout).
_TYPE_DIR: dict[ArtifactType, str] = {
    ArtifactType.INPUT_FILE: "input",
    ArtifactType.PARSED_TEXT: "ingestion",
    ArtifactType.EXTRACTED_TABLE: "ingestion",
    ArtifactType.PROBLEM_CARD: "problem",
    ArtifactType.DOMAIN_ANALYSIS: "problem",
    ArtifactType.METHOD_RETRIEVAL: "methods",
    ArtifactType.STRATEGY_CANDIDATE: "strategies",
    ArtifactType.SKEPTIC_REPORT: "strategies",
    ArtifactType.PILOT_SCRIPT: "pilots",
    ArtifactType.PILOT_RESULT: "pilots",
    ArtifactType.DATA_PROFILE: "data",
    ArtifactType.NOTEBOOK: "notebooks",
    ArtifactType.SCRIPT: "code",
    ArtifactType.DEPENDENCY_LOCK: "code",
    ArtifactType.EXECUTION_LOG: "logs",
    ArtifactType.METRICS_FILE: "metrics",
    ArtifactType.FIGURE: "figures",
    ArtifactType.TABLE: "tables",
    ArtifactType.BASELINE_RESULT: "metrics",
    ArtifactType.ROBUSTNESS_RESULT: "metrics",
    ArtifactType.EVIDENCE_RECORD: "evidence",
    ArtifactType.CITATION_RECORD: "citations",
    ArtifactType.REPORT_OUTLINE: "reports",
    ArtifactType.REPORT_MARKDOWN: "reports",
    ArtifactType.REPORT_LATEX: "reports",
    ArtifactType.REPORT_PDF: "reports",
    ArtifactType.DISCLOSURE_RECORD: "disclosures",
    ArtifactType.REPRODUCIBILITY_BUNDLE: "exports",
}


class ArtifactRegistry:
    """Content-addressed, immutable artifact store + index."""

    def __init__(self, db: Database, object_store: LocalObjectStore | None = None) -> None:
        self.db = db
        self.store = object_store or LocalObjectStore()

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    def register_bytes(
        self,
        run_id: str,
        artifact_type: ArtifactType,
        filename: str,
        data: bytes,
        *,
        created_by: str = "system",
        source_artifact_ids: list[str] | None = None,
        experiment_id: str | None = None,
        metadata: dict | None = None,
        subdir: str | None = None,
    ) -> ArtifactRecord:
        """Store bytes and create an immutable artifact record."""
        safe_name = _safe_filename(filename)
        directory = subdir or _TYPE_DIR.get(artifact_type, "ingestion")
        artifact_id = new_artifact_id(artifact_type.value)
        # Storage path is artifact-id-scoped so revisions never overwrite a
        # prior artifact's bytes (immutability, spec 11.4). The human-readable
        # name is preserved in the record's `filename` field.
        stored_name = f"{_short_suffix(artifact_id)}__{safe_name}"
        relative = f"{directory}/{stored_name}"
        uri = self.store.put_bytes(run_id, relative, data)
        record = ArtifactRecord(
            artifact_id=artifact_id,
            run_id=run_id,
            artifact_type=artifact_type,
            filename=safe_name,
            storage_uri=uri,
            content_hash=hash_bytes(data),
            mime_type=_guess_mime(safe_name),
            size_bytes=len(data),
            created_by=created_by,
            source_artifact_ids=source_artifact_ids or [],
            experiment_id=experiment_id,
            metadata=metadata or {},
        )
        self._persist(record)
        return record

    def register_text(
        self,
        run_id: str,
        artifact_type: ArtifactType,
        filename: str,
        text: str,
        **kwargs: object,
    ) -> ArtifactRecord:
        return self.register_bytes(
            run_id, artifact_type, filename, text.encode("utf-8"), **kwargs  # type: ignore[arg-type]
        )

    def register_existing_file(
        self,
        run_id: str,
        artifact_type: ArtifactType,
        path: str | Path,
        *,
        created_by: str = "system",
        experiment_id: str | None = None,
        metadata: dict | None = None,
    ) -> ArtifactRecord:
        """Register a file already present inside the run directory."""
        p = Path(path)
        data = p.read_bytes()
        return self.register_bytes(
            run_id,
            artifact_type,
            p.name,
            data,
            created_by=created_by,
            experiment_id=experiment_id,
            metadata=metadata,
        )

    def revise(
        self,
        prior: ArtifactRecord,
        data: bytes,
        *,
        created_by: str = "system",
        metadata: dict | None = None,
    ) -> ArtifactRecord:
        """Create a NEW artifact linked to ``prior`` (spec 11.4 immutability)."""
        return self.register_bytes(
            prior.run_id,
            prior.artifact_type,
            prior.filename,
            data,
            created_by=created_by,
            source_artifact_ids=[prior.artifact_id],
            metadata={**(metadata or {}), "revises": prior.artifact_id},
        )

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #
    def get(self, artifact_id: str) -> ArtifactRecord | None:
        with self.db.session() as session:
            row = session.get(ArtifactModel, artifact_id)
            return _row_to_record(row) if row else None

    def list_for_run(
        self, run_id: str, artifact_type: ArtifactType | None = None
    ) -> list[ArtifactRecord]:
        with self.db.session() as session:
            stmt = select(ArtifactModel).where(ArtifactModel.run_id == run_id)
            if artifact_type is not None:
                stmt = stmt.where(ArtifactModel.artifact_type == artifact_type.value)
            stmt = stmt.order_by(ArtifactModel.created_at.asc())
            rows = session.execute(stmt).scalars().all()
            return [_row_to_record(r) for r in rows]

    def read_bytes(self, artifact_id: str) -> bytes:
        record = self.get(artifact_id)
        if record is None:
            raise InputError("artifact not found", context={"artifact_id": artifact_id})
        return self.store.get_bytes(record.storage_uri)

    # ------------------------------------------------------------------ #
    def _persist(self, record: ArtifactRecord) -> None:
        with self.db.session() as session:
            existing = session.get(ArtifactModel, record.artifact_id)
            if existing is not None:
                # Immutability: never overwrite an existing artifact row.
                raise InputError(
                    "artifact already registered (immutable)",
                    context={"artifact_id": record.artifact_id},
                )
            session.add(
                ArtifactModel(
                    id=record.artifact_id,
                    run_id=record.run_id,
                    artifact_type=record.artifact_type.value,
                    filename=record.filename,
                    storage_uri=record.storage_uri,
                    content_hash=record.content_hash,
                    mime_type=record.mime_type,
                    size_bytes=record.size_bytes,
                    created_at=record.created_at,
                    created_by=record.created_by,
                    experiment_id=record.experiment_id,
                    metadata_json={
                        **record.metadata,
                        "source_artifact_ids": record.source_artifact_ids,
                    },
                )
            )


def _row_to_record(row: ArtifactModel) -> ArtifactRecord:
    meta = dict(row.metadata_json or {})
    source_ids = meta.pop("source_artifact_ids", [])
    return ArtifactRecord(
        artifact_id=row.id,
        run_id=row.run_id,
        artifact_type=ArtifactType(row.artifact_type),
        filename=row.filename,
        storage_uri=row.storage_uri,
        content_hash=row.content_hash,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        created_at=row.created_at,
        created_by=row.created_by,
        source_artifact_ids=source_ids,
        experiment_id=row.experiment_id,
        metadata=meta,
    )


def _short_suffix(artifact_id: str) -> str:
    """Last id segment, used to scope on-disk storage paths per artifact."""
    return artifact_id.rsplit("_", 1)[-1]


def _safe_filename(name: str) -> str:
    """Strip directory components and dangerous characters (security §30.2)."""
    base = Path(name).name  # drop any path components
    cleaned = "".join(c for c in base if c.isalnum() or c in "._-") or "artifact"
    return cleaned[:200]


def _guess_mime(name: str) -> str:
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"
