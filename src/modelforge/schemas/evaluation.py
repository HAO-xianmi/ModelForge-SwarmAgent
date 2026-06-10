"""Schemas for the CompetitionJudge evaluation framework.

These extend the existing ``JudgeReport``/``StrategyScore`` pattern in
``schemas/strategy.py`` to *paper-level* judging (the "full multi-judge panel"
the ``run_judge_panel`` node promises). All models inherit ``MFBaseModel`` so the
same ``extra='forbid'`` validation applies (spec 37.2).

Nothing here forks run state: a ``PaperDocument`` is constructed offline by the
benchmark harness, or in-workflow from the rendered report; scores are written
into the existing ``state.judge_reports`` lineage when run in-workflow.
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel

# Calibration tiers. Kept as plain strings (not an enum) so datasets are
# pluggable by dropping files + label entries without touching code.
TIER_AWARD = "award"
TIER_AVERAGE = "average"
TIER_WEAK = "weak"
KNOWN_TIERS = (TIER_AWARD, TIER_AVERAGE, TIER_WEAK)


class PaperDocument(MFBaseModel):
    """A normalized, language-agnostic view of a modeling paper to be judged."""

    paper_id: str
    title: str
    raw_text: str
    source_format: str = "txt"  # txt | md | tex
    language: str = "mixed"  # zh | en | mixed
    word_count: int = 0
    problem_slug: str | None = None
    tier: str | None = None  # award | average | weak | None when unknown
    source: str | None = None  # provenance (competition id, run id, ...)


class StructuralMetrics(MFBaseModel):
    """Deterministic, reproducible structural signals extracted from the text."""

    n_subproblems: int = 0
    n_equations: int = 0
    n_tables: int = 0
    n_figures: int = 0
    n_assumptions: int = 0
    n_references: int = 0
    n_sections: int = 0
    has_baseline: bool = False
    has_sensitivity: bool = False
    has_symbol_table: bool = False
    has_cross_validation: bool = False
    has_validation_metrics: bool = False  # RMSE / R2 / accuracy etc.
    section_completeness: float = 0.0  # fraction of canonical sections present
    word_count: int = 0
    # Transparency: a few example spans per signal (not exhaustive).
    evidence: dict[str, list[str]] = Field(default_factory=dict)


class DimensionScore(MFBaseModel):
    """A single rubric dimension's score, with both layers exposed."""

    dimension_id: str
    name: str
    structural_score: float | None = None  # 0-10, None if no structural signal
    llm_score: float | None = None  # 0-10, None if not LLM-judged
    final_score: float = 0.0  # 0-10, blend of present layers (global weights)
    weight: float = 0.0  # cross-dimension weight (rubric)
    evidence: list[str] = Field(default_factory=list)  # validated quotes / notes
    justification: str = ""
    evidence_unverified: bool = False  # an LLM evidence span failed verbatim check


class JudgeVote(MFBaseModel):
    """One LLM judge's raw per-dimension vote (before median aggregation)."""

    judge_id: str
    scores: dict[str, float] = Field(default_factory=dict)
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    justifications: dict[str, str] = Field(default_factory=dict)


class CompetitionJudgeReport(MFBaseModel):
    """Paper-level judging record. Mirrors the strategy ``JudgeReport`` style."""

    paper_id: str
    title: str
    final_score: float = 0.0  # 0-10
    structural_subtotal: float = 0.0  # 0-10
    llm_subtotal: float = 0.0  # 0-10
    w_struct: float = 0.40
    w_llm: float = 0.60
    n_judges: int = 0
    provider: str = "none"
    dimension_scores: list[DimensionScore] = Field(default_factory=list)
    structural_metrics: StructuralMetrics = Field(default_factory=StructuralMetrics)
    rubric_version: str = ""
    notes: list[str] = Field(default_factory=list)
    # Optional context when scored as part of a benchmark run.
    problem_slug: str | None = None
    tier: str | None = None


class MethodFitReport(MFBaseModel):
    """Pre-codegen gate result for one subproblem/candidate pairing."""

    subproblem_id: str | None = None
    candidate_id: str = ""
    passed: bool
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    issues: list[str] = Field(default_factory=list)
    required_revisions: list[str] = Field(default_factory=list)
    routing_hint: str = "proceed"


class JudgeIssue(MFBaseModel):
    """One deterministic final-panel issue with routing information."""

    judge: str
    severity: str = "major"  # info | minor | major | critical
    message: str
    routing_hint: str = "request_human_review"
    subproblem_id: str | None = None
    critical: bool = False


class JudgePanelReport(MFBaseModel):
    """Hard final-quality gate report used before checkpoint 3/export."""

    final_score: float = Field(default=0.0, ge=0.0, le=10.0)
    passed: bool = False
    per_judge_scores: dict[str, float] = Field(default_factory=dict)
    issues: list[JudgeIssue] = Field(default_factory=list)
    revision_plan: list[str] = Field(default_factory=list)
    routing_hints: list[str] = Field(default_factory=list)
    threshold: float = 7.0
