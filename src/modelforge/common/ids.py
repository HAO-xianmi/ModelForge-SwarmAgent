"""Identifier generation following spec Appendix G.1 conventions.

ID formats:
    run_id        -> run_{YYYYMMDDHHMMSS}_{short_uuid}
    artifact_id   -> artifact_{type}_{uuid}
    experiment_id -> experiment_{uuid}
    claim_id      -> claim_{uuid}
    citation_id   -> citation_{uuid}
    checkpoint_id -> checkpoint_{name}
    generic       -> {prefix}_{uuid}
"""

from __future__ import annotations

import re
import uuid

from .timeutil import utcnow

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _short_uuid(length: int = 8) -> str:
    return uuid.uuid4().hex[:length]


def _full_uuid() -> str:
    return uuid.uuid4().hex


def slugify(value: str) -> str:
    """Lowercase, replace non-alphanumeric runs with underscores, trim."""
    return _SLUG_RE.sub("_", value.strip().lower()).strip("_") or "x"


def new_run_id() -> str:
    return f"run_{utcnow().strftime('%Y%m%d%H%M%S')}_{_short_uuid()}"


def new_artifact_id(artifact_type: str) -> str:
    return f"artifact_{slugify(artifact_type)}_{_short_uuid(12)}"


def new_experiment_id() -> str:
    return f"experiment_{_short_uuid(12)}"


def new_claim_id() -> str:
    return f"claim_{_short_uuid(12)}"


def new_citation_id() -> str:
    return f"citation_{_short_uuid(12)}"


def new_pilot_id(strategy_id: str) -> str:
    return f"pilot_{slugify(strategy_id)}_{_short_uuid(6)}"


def new_event_id() -> str:
    return f"event_{_full_uuid()}"


def new_id(prefix: str) -> str:
    return f"{slugify(prefix)}_{_short_uuid(12)}"
