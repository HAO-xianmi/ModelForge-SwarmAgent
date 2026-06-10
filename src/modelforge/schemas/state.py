"""The Shared Blackboard (``ModelingState``) and ``Run`` — the authoritative
state of a run (spec 10.2 / Appendix A.1).

All agents read from and write to this through typed update operations
(applied by the storage layer's state versioning). No agent relies on hidden
persistent state (spec 4.1).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from modelforge.common.timeutil import utcnow
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.control import (
    BudgetState,
    Checkpoint,
    CompetitionProfile,
    ExportState,
    FailureState,
    HumanFeedback,
)
from modelforge.schemas.data import DataProfile
from modelforge.schemas.enums import RunStatus
from modelforge.schemas.evaluation import JudgePanelReport, MethodFitReport
from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.experiment import (
    AuditSummary,
    BaselineResult,
    BlockingIssue,
    CodeArtifact,
    ExperimentRecord,
    RobustnessResult,
)
from modelforge.schemas.problem import (
    DomainAnalysis,
    InputManifest,
    ProblemCard,
    RetrievedMethod,
)
from modelforge.schemas.report import ReportArtifacts, ReportOutline
from modelforge.schemas.route import ModelingRoute, RouteSet
from modelforge.schemas.strategy import (
    JudgeReport,
    PilotExperiment,
    SkepticReport,
    StrategyCandidate,
)


class Run(MFBaseModel):
    """Run-level metadata (spec 27.2)."""

    run_id: str
    mode: str = "practice"  # OperatingMode value
    status: RunStatus = RunStatus.CREATED
    competition_profile_id: str | None = None
    budget_profile: str = "standard"
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_reason: str | None = None
    current_state_version: int = 0


class ModelingState(MFBaseModel):
    """The blackboard — the single authoritative run state (spec 10.2).

    This is the LangGraph state object. Nodes return partial updates that the
    control plane validates, versions, and audits.
    """

    run_id: str
    mode: str = "practice"
    status: RunStatus = RunStatus.CREATED
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    competition_profile: CompetitionProfile | None = None
    input_manifest: InputManifest | None = None

    problem_card: ProblemCard | None = None
    domain_analysis: DomainAnalysis | None = None
    retrieved_methods: list[RetrievedMethod] = Field(default_factory=list)

    strategy_candidates: list[StrategyCandidate] = Field(default_factory=list)
    skeptic_report: SkepticReport | None = None
    pilot_experiments: list[PilotExperiment] = Field(default_factory=list)
    selected_strategy: StrategyCandidate | None = None
    judge_reports: list[JudgeReport] = Field(default_factory=list)
    subproblem_routes: dict[str, RouteSet] = Field(default_factory=dict)
    subproblem_selected_routes: dict[str, ModelingRoute] = Field(default_factory=dict)
    subproblem_experiments: dict[str, list[ExperimentRecord]] = Field(default_factory=dict)
    subproblem_evidence: dict[str, list[EvidenceClaim]] = Field(default_factory=dict)
    subproblem_sections: dict[str, str] = Field(default_factory=dict)
    method_fit_reports: list[MethodFitReport] = Field(default_factory=list)

    data_profile: DataProfile | None = None
    code_artifacts: list[CodeArtifact] = Field(default_factory=list)
    experiment_records: list[ExperimentRecord] = Field(default_factory=list)
    baseline_results: list[BaselineResult] = Field(default_factory=list)
    robustness_results: list[RobustnessResult] = Field(default_factory=list)
    audit_summary: AuditSummary | None = None

    evidence_claims: list[EvidenceClaim] = Field(default_factory=list)
    citations: list[CitationRecord] = Field(default_factory=list)

    report_outline: ReportOutline | None = None
    report_artifacts: ReportArtifacts | None = None
    # Drafted section bodies keyed by section_id, between writer and assembly.
    section_texts: dict[str, str] = Field(default_factory=dict)
    judge_panel_reports: list[JudgePanelReport] = Field(default_factory=list)

    blocking_issues: list[BlockingIssue] = Field(default_factory=list)
    pending_checkpoint: Checkpoint | None = None
    human_feedback: list[HumanFeedback] = Field(default_factory=list)

    budget_state: BudgetState = Field(default_factory=BudgetState)
    export_state: ExportState = Field(default_factory=ExportState)
    failure_state: FailureState | None = None

    # --- convenience accessors -------------------------------------------- #
    def strategy_by_id(self, strategy_id: str) -> StrategyCandidate | None:
        return next(
            (s for s in self.strategy_candidates if s.strategy_id == strategy_id), None
        )

    def pilot_for(self, strategy_id: str) -> PilotExperiment | None:
        return next(
            (p for p in self.pilot_experiments if p.strategy_id == strategy_id), None
        )

    def verified_claims(self, subproblem_id: str | None = None) -> list[EvidenceClaim]:
        claims = [c for c in self.evidence_claims if c.usable_by_writer]
        if subproblem_id is not None:
            return [c for c in claims if c.subproblem_id == subproblem_id]
        return claims
