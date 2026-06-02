"""Structured logging.

Two sinks:
  * A standard Python logger for console/dev output.
  * A :class:`JsonlEventLogger` that appends one JSON object per line to a run's
    ``logs/workflow.jsonl`` (spec 31.1 events / Appendix F). This is the durable,
    machine-readable audit trail; it never raises on a single bad record.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from .timeutil import isoformat

_CONFIGURED = False


def get_logger(name: str = "modelforge") -> logging.Logger:
    """Return a process logger, configuring a single stderr handler once."""
    global _CONFIGURED
    logger = logging.getLogger(name)
    if not _CONFIGURED:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s")
        )
        root = logging.getLogger("modelforge")
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        root.propagate = False
        _CONFIGURED = True
    return logger


class JsonlEventLogger:
    """Append-only JSONL event sink for a single run.

    Each ``emit`` writes one line: ``{"ts": ..., "event_type": ..., ...payload}``.
    Failures to write are logged but never propagate, so observability problems
    cannot crash a workflow.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._log = get_logger("modelforge.events")

    def emit(self, event_type: str, **payload: Any) -> None:
        record = {"ts": isoformat(), "event_type": event_type, **payload}
        try:
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
        except OSError as exc:  # pragma: no cover - defensive
            self._log.warning("failed to write event %s: %s", event_type, exc)

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
