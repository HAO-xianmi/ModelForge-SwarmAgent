"""Sandbox runner Protocol and request model.

A sandbox runs a Python entrypoint against a workspace with the canonical mount
layout (spec 20.3):
    input/   read-only data
    src/     read-write source
    output/  read-write generated files (figures, tables, metrics.json)
    logs/    read-write logs

Every runner returns a :class:`~modelforge.schemas.experiment.SandboxResult`
with captured stdout/stderr/exit code, collected output files, and any metrics
parsed from ``output/metrics.json``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import Field

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.experiment import SandboxResult

# Dependency allowlist (spec 20.1 MVP + science extras). Code that imports
# outside this set is flagged by static inspection before execution.
DEFAULT_ALLOWED_IMPORTS: frozenset[str] = frozenset(
    {
        "numpy",
        "pandas",
        "scipy",
        "sklearn",
        "statsmodels",
        "networkx",
        "matplotlib",
        "pulp",
        "openpyxl",
        "json",
        "csv",
        "math",
        "random",
        "statistics",
        "itertools",
        "functools",
        "collections",
        "dataclasses",
        "datetime",
        "pathlib",
        "os",
        "sys",
        "typing",
        "warnings",
        "re",
        "io",
        "time",
    }
)


class SandboxRequest(MFBaseModel):
    """A single sandboxed execution request."""

    run_id: str
    workspace: Path  # absolute path to the experiment workspace
    entrypoint: str = "main.py"
    timeout_seconds: int = 120
    memory_mb: int = 1024
    cpu: float = 1.0
    seed: int = 42
    allowed_imports: frozenset[str] = DEFAULT_ALLOWED_IMPORTS
    env: dict[str, str] = Field(default_factory=dict)

    model_config = MFBaseModel.model_config | {"arbitrary_types_allowed": True}


@runtime_checkable
class SandboxRunner(Protocol):
    """Contract implemented by every sandbox backend."""

    backend_name: str

    def run(self, request: SandboxRequest) -> SandboxResult:
        """Execute the entrypoint and return a structured result.

        Implementations MUST NOT raise on ordinary code failure (non-zero exit,
        timeout); those are encoded in the returned ``SandboxResult.status``.
        They MAY raise ``SandboxError`` only for infrastructure problems.
        """
        ...


def collect_output_files(output_dir: Path) -> list[str]:
    """Return output files as paths relative to the output directory."""
    if not output_dir.exists():
        return []
    return sorted(
        str(p.relative_to(output_dir)).replace("\\", "/")
        for p in output_dir.rglob("*")
        if p.is_file()
    )
