"""Run repository with audited, versioned blackboard state (spec 10.4, 27.2/27.3).

The blackboard (``ModelingState``) is persisted as immutable, numbered
``run_state_versions`` rows. Each ``save_state`` computes the changed fields,
writes a new version, updates the run pointer, and emits a ``STATE_UPDATED``
audit event recording actor, prev/new version, changed fields, and reason
(spec 10.4 rule 3).
"""

from __future__ import annotations

from sqlalchemy import select

from modelforge.common.timeutil import utcnow
from modelforge.schemas.artifacts import StateChange
from modelforge.schemas.enums import ActorType, EventType, RunStatus
from modelforge.schemas.state import ModelingState, Run
from modelforge.storage.database import Database
from modelforge.storage.models import RunModel, RunStateVersionModel
from modelforge.storage.repositories.audit_repo import AuditRepository


class RunRepository:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.audit = AuditRepository(db)

    # ------------------------------------------------------------------ #
    # Run lifecycle
    # ------------------------------------------------------------------ #
    def create_run(self, run: Run, initial_state: ModelingState) -> Run:
        with self.db.session() as session:
            session.add(
                RunModel(
                    id=run.run_id,
                    user_id=None,
                    mode=run.mode,
                    status=run.status.value,
                    competition_profile_id=run.competition_profile_id,
                    budget_profile=run.budget_profile,
                    created_at=run.created_at,
                    updated_at=run.updated_at,
                    current_state_version=0,
                )
            )
            session.add(
                RunStateVersionModel(
                    run_id=run.run_id,
                    version_number=0,
                    state_json=initial_state.model_dump(mode="json"),
                    created_by="system",
                    change_reason="run created",
                )
            )
        self.audit.record(run.run_id, EventType.RUN_CREATED, payload={"mode": run.mode})
        return run

    def get_run(self, run_id: str) -> Run | None:
        with self.db.session() as session:
            row = session.get(RunModel, run_id)
            if row is None:
                return None
            return _row_to_run(row)

    def list_runs(self, limit: int = 100) -> list[Run]:
        with self.db.session() as session:
            rows = (
                session.execute(
                    select(RunModel).order_by(RunModel.created_at.desc()).limit(limit)
                )
                .scalars()
                .all()
            )
            return [_row_to_run(r) for r in rows]

    # ------------------------------------------------------------------ #
    # State versioning
    # ------------------------------------------------------------------ #
    def load_state(self, run_id: str, version: int | None = None) -> ModelingState | None:
        with self.db.session() as session:
            stmt = select(RunStateVersionModel).where(
                RunStateVersionModel.run_id == run_id
            )
            if version is None:
                stmt = stmt.order_by(RunStateVersionModel.version_number.desc()).limit(1)
            else:
                stmt = stmt.where(RunStateVersionModel.version_number == version)
            row = session.execute(stmt).scalars().first()
            if row is None:
                return None
            return ModelingState.model_validate(row.state_json)

    def current_version(self, run_id: str) -> int:
        with self.db.session() as session:
            row = session.get(RunModel, run_id)
            return row.current_state_version if row else -1

    def save_state(
        self,
        state: ModelingState,
        *,
        actor: str,
        actor_type: ActorType,
        reason: str,
    ) -> StateChange:
        """Persist a new immutable state version + audit event."""
        run_id = state.run_id
        prev_version = self.current_version(run_id)
        prev_state = self.load_state(run_id) if prev_version >= 0 else None
        new_version = prev_version + 1
        state.updated_at = utcnow()

        changed = _changed_fields(prev_state, state)

        with self.db.session() as session:
            run_row = session.get(RunModel, run_id)
            session.add(
                RunStateVersionModel(
                    run_id=run_id,
                    version_number=new_version,
                    state_json=state.model_dump(mode="json"),
                    created_by=actor,
                    change_reason=reason,
                )
            )
            if run_row is not None:
                run_row.current_state_version = new_version
                run_row.status = state.status.value
                run_row.updated_at = state.updated_at
                run_row.total_cost_estimate = state.budget_state.estimated_cost_usd
                run_row.total_runtime_seconds = state.budget_state.sandbox_runtime_seconds
                if state.status is RunStatus.COMPLETED:
                    run_row.completed_at = utcnow()
                if state.failure_state is not None:
                    run_row.failure_reason = state.failure_state.detail

        change = StateChange(
            actor=actor,
            actor_type=actor_type,
            previous_version=prev_version,
            new_version=new_version,
            changed_fields=changed,
            reason=reason,
        )
        self.audit.record(
            run_id,
            EventType.STATE_UPDATED,
            actor_type=actor_type,
            actor_id=actor,
            payload=change.model_dump(mode="json"),
        )
        return change

    def list_versions(self, run_id: str) -> list[int]:
        with self.db.session() as session:
            rows = (
                session.execute(
                    select(RunStateVersionModel.version_number)
                    .where(RunStateVersionModel.run_id == run_id)
                    .order_by(RunStateVersionModel.version_number.asc())
                )
                .scalars()
                .all()
            )
            return list(rows)


def _row_to_run(row: RunModel) -> Run:
    return Run(
        run_id=row.id,
        mode=row.mode,
        status=RunStatus(row.status),
        competition_profile_id=row.competition_profile_id,
        budget_profile=row.budget_profile,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        failure_reason=row.failure_reason,
        current_state_version=row.current_state_version,
    )


def _changed_fields(prev: ModelingState | None, new: ModelingState) -> list[str]:
    if prev is None:
        return ["*"]
    prev_d = prev.model_dump(mode="json")
    new_d = new.model_dump(mode="json")
    return sorted(k for k in new_d if prev_d.get(k) != new_d.get(k))
