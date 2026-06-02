"""Typed domain schemas (Pydantic v2) — the contracts for the whole system.

These are the authoritative data shapes for the Shared Blackboard
(:class:`~modelforge.schemas.state.ModelingState`) and every artifact, agent
input/output, and registry record. Everything else builds on these.

Submodules:
    enums       — all status / category enumerations (spec status values)
    base        — shared base model + mixins
    artifacts   — ArtifactRecord, AuditEvent, manifests
    problem     — InputManifest, ProblemCard, DomainAnalysis, RetrievedMethod
    strategy    — StrategyCandidate, SkepticReport, JudgeReport, PilotExperiment
    data        — DataProfile and column stats
    experiment  — CodeArtifact, ExperimentRecord, Baseline/Robustness results
    evidence    — EvidenceClaim, CitationRecord
    report      — ReportOutline, ReportSection, report artifacts
    control     — Checkpoint, HumanFeedback, BudgetState, FailureState, ExportState
    state       — ModelingState (the blackboard) + Run
"""

from modelforge.schemas import (
    artifacts,
    base,
    control,
    data,
    enums,
    evidence,
    experiment,
    problem,
    report,
    state,
    strategy,
)

__all__ = [
    "artifacts",
    "base",
    "control",
    "data",
    "enums",
    "evidence",
    "experiment",
    "problem",
    "report",
    "state",
    "strategy",
]
