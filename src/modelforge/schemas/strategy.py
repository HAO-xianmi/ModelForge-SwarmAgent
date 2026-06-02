"""Strategy generation, critique, pilots, and selection.

Spec references: 8.4 (StrategyProposerAgent), 8.5 (SkepticAgent),
8.6 (StrategyJudgeAgent), 17 (generation/debate/selection), 18 (pilots).
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import (
    ExperimentStatus,
    IssueSeverity,
    JudgeDecision,
    ProblemFamily,
    StrategyGoal,
)


class MethodStackEntry(MFBaseModel):
    method_id: str
    role: str = ""  # e.g. preprocessing | core_model | evaluation
    rationale: str = ""


class StrategyCandidate(MFBaseModel):
    """A complete modeling strategy (spec 8.4 / Appendix A.2).

    Invariant: the candidate MUST define a runnable pilot experiment
    (``pilot_template`` + ``problem_family`` route to a real code template).
    """

    strategy_id: str
    strategy_name: str
    design_goal: StrategyGoal
    problem_family: ProblemFamily = ProblemFamily.UNKNOWN
    subproblem_mapping: list[str] = Field(default_factory=list)
    method_stack: list[MethodStackEntry] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    variable_definitions: list[str] = Field(default_factory=list)
    mathematical_formulation: str = ""
    data_requirements: list[str] = Field(default_factory=list)
    preprocessing_plan: list[str] = Field(default_factory=list)
    experiment_plan: list[str] = Field(default_factory=list)
    baseline_plan: list[str] = Field(default_factory=list)
    robustness_plan: list[str] = Field(default_factory=list)
    visualization_plan: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    estimated_runtime_seconds: float = 0.0
    implementation_risk: str = "medium"  # low | medium | high
    known_limitations: list[str] = Field(default_factory=list)
    fallback_plan: list[str] = Field(default_factory=list)
    # The code template this strategy's pilot/formal code is generated from.
    pilot_template: str = ""

    @property
    def is_pilotable(self) -> bool:
        return bool(self.pilot_template) and self.problem_family is not ProblemFamily.UNKNOWN


class SkepticIssue(MFBaseModel):
    severity: IssueSeverity
    category: str  # assumption | data_leakage | overfitting | runtime | compliance ...
    description: str
    required_fix: str = ""


class SkepticCandidateReview(MFBaseModel):
    strategy_id: str
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    issues: list[SkepticIssue] = Field(default_factory=list)
    required_pilot_experiments: list[str] = Field(default_factory=list)
    recommendation: str = "revise"  # pass | revise

    @property
    def has_blocker(self) -> bool:
        return any(i.severity is IssueSeverity.BLOCKER for i in self.issues)


class SkepticReport(MFBaseModel):
    """Structured critique of all candidates (spec 8.5 / 17.3).

    Invariant: the skeptic MUST NOT silently approve every strategy.
    """

    reviews: list[SkepticCandidateReview] = Field(default_factory=list)
    summary: str = ""

    def for_strategy(self, strategy_id: str) -> SkepticCandidateReview | None:
        return next((r for r in self.reviews if r.strategy_id == strategy_id), None)


class PilotExperiment(MFBaseModel):
    """Result of a low-cost pilot run (spec 18.3).

    Metrics are populated ONLY from real sandbox execution — never typed by an
    agent (working rule 5).
    """

    pilot_id: str
    strategy_id: str
    status: ExperimentStatus = ExperimentStatus.PENDING
    runtime_seconds: float = 0.0
    sample_size: int = 0
    metrics: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
    failure_reason: str | None = None
    recommendation: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status is ExperimentStatus.SUCCEEDED


class StrategyScore(MFBaseModel):
    """Per-candidate weighted score (spec 17.4 dimensions)."""

    strategy_id: str
    problem_fit: float = 0.0
    data_fit: float = 0.0
    feasibility: float = 0.0
    interpretability: float = 0.0
    experimental_evidence: float = 0.0
    robustness_potential: float = 0.0
    novelty: float = 0.0
    runtime_cost: float = 0.0
    total: float = 0.0


class JudgeReport(MFBaseModel):
    """Strategy selection decision record (spec 8.6).

    Invariant: the decision MUST reference pilot evidence when available.
    """

    decision: JudgeDecision
    selected_strategy_id: str | None = None
    merged_from: list[str] = Field(default_factory=list)
    rationale: str = ""
    rejected_alternatives: list[str] = Field(default_factory=list)
    scores: list[StrategyScore] = Field(default_factory=list)
    referenced_pilot_ids: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
