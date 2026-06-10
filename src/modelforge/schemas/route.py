"""Modeling routes + route-tournament schemas (Phase H, Slice 2).

A *route* is a substantially-distinct way to model a (sub-)problem — grounded in a
domain model (KB) and/or generic methods — carrying its own assumptions,
advantages, limitations, risks, and expected metrics. The tournament compares
routes pairwise on explicit criteria and records an audit trail for the choice.
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import ProblemFamily


class ModelingRoute(MFBaseModel):
    route_id: str
    name: str
    approach: str  # mechanistic | data_driven | optimization | simulation | hybrid | network
    family: ProblemFamily
    model_family: str = ""
    methods: list[str] = Field(default_factory=list)
    data_needed: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    why_fit: str = ""
    summary: str
    domain_model_ids: list[str] = Field(default_factory=list)
    method_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    # Expected per-criterion merit in [0,1] (problem_fit, modeling_depth, ...).
    expected_metrics: dict[str, float] = Field(default_factory=dict)
    subproblem_id: str | None = None


class RouteSet(MFBaseModel):
    routes: list[ModelingRoute] = Field(default_factory=list)
    subproblem_id: str | None = None


class RouteScore(MFBaseModel):
    route_id: str
    problem_fit: float = 0.0
    modeling_depth: float = 0.0
    innovation: float = 0.0
    feasibility: float = 0.0
    robustness: float = 0.0
    interpretability: float = 0.0
    expected_total: float = 0.0


class PairwiseComparison(MFBaseModel):
    route_a: str
    route_b: str
    winner: str
    criterion: str = "expected_total"
    rationale: str = ""


class RouteTournamentResult(MFBaseModel):
    subproblem_id: str | None = None
    routes_considered: list[str] = Field(default_factory=list)
    scores: list[RouteScore] = Field(default_factory=list)
    comparisons: list[PairwiseComparison] = Field(default_factory=list)
    selected_route_id: str = ""
    runner_up_id: str = ""
    rationale: str = ""
    audit_trail: list[str] = Field(default_factory=list)
