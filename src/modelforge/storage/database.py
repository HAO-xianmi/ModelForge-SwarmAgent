"""Engine and session management for SQLite (default) and PostgreSQL.

``create_all`` is used for the local/zero-config path; Alembic migrations exist
for production (see ``alembic/``). SQLite gets ``check_same_thread=False`` plus a
foreign-keys pragma so it behaves like the Postgres path under tests and the API.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from modelforge.common.config import get_settings
from modelforge.storage.models import Base


def make_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_settings().database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    engine = create_engine(url, future=True, connect_args=connect_args)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_pragma(dbapi_conn, _record):  # type: ignore[no-untyped-def]
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


class Database:
    """Owns an engine + session factory. One per process (or per test)."""

    def __init__(self, database_url: str | None = None) -> None:
        self.engine = make_engine(database_url)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=Session, future=True
        )

    def create_all(self) -> None:
        """Create tables if absent (local/dev path; prod uses Alembic)."""
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Transactional scope: commit on success, rollback on error."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def new_session(self) -> Session:
        """A raw session the caller manages (used by long-lived API deps)."""
        return self._session_factory()
