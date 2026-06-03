"""Domain / mechanistic model knowledge base schema (Phase H, Slice 2).

This is the structured modeling knowledge the agents retrieve from instead of
free-recalling. It is RICHER than the generic ``RetrievedMethod`` (textbook
methods) — each entry carries governing equations, competition usage, failure
modes, validation/sensitivity methods, and implementation hints, so a route can
be grounded in a real domain model (e.g. FAO Penman-Monteith) rather than a
generic template.

Kept deliberately additive: it does NOT replace the existing MethodLibrary; the
RouteGenerator queries both. Extensible — add an entry to ``DOMAIN_MODELS`` and a
``families``/``keywords`` mapping; no code change elsewhere.
"""

from __future__ import annotations

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import ProblemFamily


class DomainModel(MFBaseModel):
    model_id: str
    name: str
    category: str  # mechanistic | hybrid | stochastic | optimization | data_driven | network
    families: list[ProblemFamily]
    summary: str
    governing_equations: list[str] = []  # LaTeX (no surrounding $); rendered by the writer
    assumptions: list[str] = []
    applicability: list[str] = []
    advantages: list[str] = []
    failure_modes: list[str] = []
    validation_methods: list[str] = []
    sensitivity_methods: list[str] = []
    implementation_hints: list[str] = []
    typical_competition_usage: str = ""
    references: list[str] = []
    keywords: list[str] = []
    suitability_score: float = 0.0  # populated by retrieval, not stored
