"""Run directory layout builder (spec 28.1 / Appendix F).

Creates ``runs/{run_id}/`` with the canonical subdirectories. Path access is
mediated so callers cannot escape the run root (defense in depth alongside the
sandbox path guard).
"""

from __future__ import annotations

from pathlib import Path

from modelforge.common.config import get_settings
from modelforge.common.errors import InputError

# Canonical subdirectories from spec 28.1.
RUN_SUBDIRS: tuple[str, ...] = (
    "input",
    "ingestion",
    "problem",
    "methods",
    "strategies",
    "pilots",
    "data",
    "code",
    "notebooks",
    "experiments",
    "figures",
    "tables",
    "metrics",
    "evidence",
    "citations",
    "reports",
    "disclosures",
    "logs",
    "manifests",
    "exports",
)


class RunDirectory:
    """Filesystem layout for a single run."""

    def __init__(self, run_id: str, root: Path | None = None) -> None:
        self.run_id = run_id
        base = (root or get_settings().runs_path).resolve()
        self.path = (base / run_id).resolve()
        # Guard: the run path must stay inside the runs root.
        if base not in self.path.parents and self.path != base:
            raise InputError("run path escapes runs root", context={"run_id": run_id})

    def create(self) -> RunDirectory:
        self.path.mkdir(parents=True, exist_ok=True)
        for sub in RUN_SUBDIRS:
            (self.path / sub).mkdir(parents=True, exist_ok=True)
        return self

    def subdir(self, name: str) -> Path:
        if name not in RUN_SUBDIRS:
            raise InputError(f"unknown run subdir: {name}", context={"name": name})
        return self.path / name

    def resolve_within(self, *parts: str) -> Path:
        """Resolve a path under the run root, rejecting traversal escapes."""
        target = self.path.joinpath(*parts).resolve()
        if self.path != target and self.path not in target.parents:
            raise InputError(
                "path escapes run directory", context={"parts": list(parts)}
            )
        return target

    def exists(self) -> bool:
        return self.path.exists()
