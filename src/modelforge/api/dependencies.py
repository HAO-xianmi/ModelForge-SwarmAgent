"""Shared API dependencies: a process-wide database + coordinator.

The database is created once and reused across requests. Run state is loaded
from / persisted to the DB per request, so the API is stateless beyond the DB.
"""

from __future__ import annotations

from functools import lru_cache

from modelforge.graph.coordinator import RunCoordinator, default_database
from modelforge.storage.database import Database


@lru_cache(maxsize=1)
def get_database() -> Database:
    return default_database()


def get_coordinator() -> RunCoordinator:
    return RunCoordinator(get_database())
