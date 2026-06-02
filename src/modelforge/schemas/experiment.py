"""Code artifacts, experiment records, sandbox results, baselines, robustness.

Spec references: 8.7 (CodeAuthorAgent), 8.8 (DebuggerAgent), 9.3/9.4 (sandbox /
experiment tracker), 20 (code/sandbox/debug), 21 (baselines/robustness/audit).
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import (
    ExperimentStatus,
    ExperimentType,
    IssueSeverity,
    SandboxStatus,
)


class CodeFile(MFBaseModel):
    """One generated source file (spec 20.2 structure)."""

    filename: str  # load_data.py | preprocess.py | model.py | ...
    content: str
    role: str = ""


class CodeArtifact(MFBaseModel):
    """A generated code project for an experiment (spec 8.7)."""

    code_artifact_id: str
    strategy_id: str
    files: list[CodeFile] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    entrypoint: str = "main.py"
    seed: int = 42
    content_hash: str = ""
    artifact_ids: list[str] = Field(default_factory=list)
    notes: str = ""

    def file(self, name: str) -> CodeFile | None:
        return next((f for f in self.files if f.filename == name), None)


class SandboxResult(MFBaseModel):
    """Structured result of one sandbox execution (spec 9.3).

    All fields come from real execution: captured stdout/stderr/exit code and
    files collected from the output directory.
    """

    status: SandboxStatus
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    runtime_seconds: float = 0.0
    timed_out: bool = False
    output_files: list[str] = Field(default_factory=list)  # relative paths in output/
    metrics: dict[str, float] = Field(default_factory=dict)  # parsed from metrics.json
    backend: str = "subprocess"  # subprocess | docker
    policy_block_reason: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status is SandboxStatus.SUCCEEDED


class DebugPatch(MFBaseModel):
    """A single bounded debug attempt (spec 8.8)."""

    attempt: int
    reason: str
    changed_files: list[str] = Field(default_factory=list)
    explanation: str = ""


class ExperimentRecord(MFBaseModel):
    """Tracked experiment with full reproducibility metadata (spec 9.4)."""

    experiment_id: str
    run_id: str
    strategy_id: str
    experiment_type: ExperimentType
    status: ExperimentStatus = ExperimentStatus.PENDING
    seed: int = 42
    code_artifact_id: str | None = None
    input_manifest_hash: str = ""
    dependencies: list[str] = Field(default_factory=list)
    runtime_seconds: float = 0.0
    metrics: dict[str, float] = Field(default_factory=dict)
    output_artifact_ids: list[str] = Field(default_factory=list)
    log_artifact_ids: list[str] = Field(default_factory=list)
    figure_artifact_ids: list[str] = Field(default_factory=list)
    table_artifact_ids: list[str] = Field(default_factory=list)
    sandbox_backend: str = "subprocess"
    debug_patches: list[DebugPatch] = Field(default_factory=list)
    failure_reason: str | None = None
    train_test_split: bool = False
    leakage_checked: bool = False


class BaselineResult(MFBaseModel):
    """A baseline comparison (spec 21.1)."""

    baseline_name: str
    strategy_id: str
    experiment_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.PENDING
    is_waiver: bool = False
    waiver_reason: str | None = None
    waiver_approved_by: str | None = None


class RobustnessResult(MFBaseModel):
    """A robustness / sensitivity test result (spec 21.2)."""

    test_name: str  # parameter_perturbation | repeated_seeds | subsampling | noise | ...
    strategy_id: str
    experiment_id: str | None = None
    variants: list[dict] = Field(default_factory=list)  # [{param, value, metrics}]
    summary: dict[str, float] = Field(default_factory=dict)  # e.g. {"metric_std": ...}
    status: ExperimentStatus = ExperimentStatus.PENDING
    is_waiver: bool = False
    waiver_reason: str | None = None
    waiver_approved_by: str | None = None


class BlockingIssue(MFBaseModel):
    """An audit blocking issue that prevents report export (spec 21.4)."""

    issue_id: str
    severity: IssueSeverity = IssueSeverity.BLOCKER
    category: str  # implementation_defect | model_design_defect | evidence | reproducibility
    description: str
    routing_hint: str = ""  # revise_code | revise_strategy | escalate


class AuditSummary(MFBaseModel):
    """Experiment auditor output (spec 21.3)."""

    checks: dict[str, bool] = Field(default_factory=dict)
    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    passed: bool = False

    @property
    def has_blocking(self) -> bool:
        return len(self.blocking_issues) > 0
