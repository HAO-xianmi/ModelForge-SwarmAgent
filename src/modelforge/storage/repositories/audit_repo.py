"""Audit event persistence (spec 27.4 / 31)."""

from __future__ import annotations

from sqlalchemy import select

from modelforge.common.ids import new_event_id
from modelforge.common.timeutil import utcnow
from modelforge.schemas.artifacts import AuditEvent
from modelforge.schemas.enums import ActorType, EventType
from modelforge.storage.database import Database
from modelforge.storage.models import AuditEventModel


class AuditRepository:
    """Append-only audit event log backed by the database."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def record(
        self,
        run_id: str,
        event_type: EventType,
        *,
        actor_type: ActorType = ActorType.SYSTEM,
        actor_id: str = "system",
        payload: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            event_id=new_event_id(),
            run_id=run_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_id=actor_id,
            timestamp=utcnow(),
            payload=payload or {},
        )
        with self.db.session() as session:
            session.add(
                AuditEventModel(
                    id=event.event_id,
                    run_id=event.run_id,
                    event_type=event.event_type.value,
                    actor_type=event.actor_type.value,
                    actor_id=event.actor_id,
                    timestamp=event.timestamp,
                    payload_json=event.payload,
                )
            )
        return event

    def list_for_run(self, run_id: str) -> list[AuditEvent]:
        with self.db.session() as session:
            rows = (
                session.execute(
                    select(AuditEventModel)
                    .where(AuditEventModel.run_id == run_id)
                    .order_by(AuditEventModel.timestamp.asc(), AuditEventModel.id.asc())
                )
                .scalars()
                .all()
            )
            return [
                AuditEvent(
                    event_id=r.id,
                    run_id=r.run_id,
                    event_type=EventType(r.event_type),
                    actor_type=ActorType(r.actor_type),
                    actor_id=r.actor_id,
                    timestamp=r.timestamp,
                    payload=r.payload_json or {},
                )
                for r in rows
            ]
