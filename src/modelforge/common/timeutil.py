"""Time utilities.

All timestamps in ModelForge-Swarm are timezone-aware UTC and serialized in
ISO-8601 with a trailing ``Z`` so audit records are unambiguous across hosts.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def isoformat(dt: datetime | None = None) -> str:
    """Serialize a datetime (default now) to ISO-8601 UTC with ``Z`` suffix."""
    dt = dt or utcnow()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string (accepting trailing ``Z``) into UTC datetime."""
    normalized = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)
