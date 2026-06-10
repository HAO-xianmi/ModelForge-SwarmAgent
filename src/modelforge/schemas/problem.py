"""Problem ingestion, problem card, domain analysis, and method records.

Spec references: 8.1 (ProblemParserAgent), 8.2 (DomainAnalystAgent),
8.3 (MethodRetrieverAgent), 15 (ingestion/parsing), 16 (domain/method).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import MethodCategory, ProblemFamily


# --------------------------------------------------------------------------- #
# Ingestion
# --------------------------------------------------------------------------- #
class FileManifest(MFBaseModel):
    """One ingested file (spec 15.2)."""

    file_id: str
    original_name: str
    normalized_name: str
    content_hash: str
    mime_type: str
    size_bytes: int
    extracted_text_available: bool = False
    extracted_tables_available: bool = False
    ingestion_status: str = "INGESTED"
    source_reference: str = ""
    artifact_id: str | None = None
    role: str = "data"  # problem | rules | data | notes | constraints | image


class InputManifest(MFBaseModel):
    """The full set of ingested inputs for a run."""

    run_id: str
    files: list[FileManifest] = Field(default_factory=list)
    total_size_bytes: int = 0
    problem_text: str = ""  # consolidated, untrusted problem statement text

    def by_role(self, role: str) -> list[FileManifest]:
        return [f for f in self.files if f.role == role]


# --------------------------------------------------------------------------- #
# Problem card
# --------------------------------------------------------------------------- #
class SourceReference(MFBaseModel):
    """Provenance for an extracted requirement (spec 15.4)."""

    source_file: str = ""
    page: int | None = None
    table_name: str | None = None
    line_reference: str | None = None
    quote: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_llm_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalized = dict(data)
            if "source" in normalized and "source_file" not in normalized:
                normalized["source_file"] = normalized.pop("source")
            if "sub_id" in normalized and "line_reference" not in normalized:
                normalized["line_reference"] = normalized.pop("sub_id")
            return normalized
        return data


class SubProblem(MFBaseModel):
    sub_id: str
    statement: str
    objective: str = ""
    required_outputs: list[str] = Field(default_factory=list)
    input_data_refs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)
    expected_figures: list[str] = Field(default_factory=list)
    expected_tables: list[str] = Field(default_factory=list)
    expected_equations: list[str] = Field(default_factory=list)
    risk_of_misread: str = ""
    inferred: bool = False
    source: SourceReference | None = None


class DatasetRef(MFBaseModel):
    name: str
    description: str = ""
    file_id: str | None = None


class ProblemCard(MFBaseModel):
    """Structured problem decomposition (spec 8.1 / 15.3).

    Invariant: each extracted requirement SHOULD carry a source reference.
    """

    title: str
    background: str = ""
    problem_summary: str = ""
    objective_summary: str = ""
    subproblems: list[SubProblem] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    decision_variables: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    global_constraints: list[str] = Field(default_factory=list)
    datasets: list[DatasetRef] = Field(default_factory=list)
    required_outputs: list[str] = Field(default_factory=list)
    formatting_requirements: list[str] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    assumptions_to_confirm: list[str] = Field(default_factory=list)
    forbidden_misreadings: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_map: list[SourceReference] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Domain analysis
# --------------------------------------------------------------------------- #
class DomainAnalysis(MFBaseModel):
    """Domain classification (spec 8.2 / 16.1).

    Invariant: facts MUST be distinguished from assumptions.
    """

    domain_tags: list[str] = Field(default_factory=list)
    likely_problem_families: list[ProblemFamily] = Field(default_factory=list)
    domain_assumptions: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)
    data_requirements: list[str] = Field(default_factory=list)
    potential_external_facts: list[str] = Field(default_factory=list)
    research_questions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_specialists: list[str] = Field(default_factory=list)
    # spec 16.1 classification axes
    data_modality: str = ""
    time_dependence: bool = False
    spatial_dependence: bool = False
    optimization_required: bool = False
    uncertainty_required: bool = False
    interpretability_required: bool = False

    @property
    def primary_family(self) -> ProblemFamily:
        if self.likely_problem_families:
            return self.likely_problem_families[0]
        return ProblemFamily.UNKNOWN


# --------------------------------------------------------------------------- #
# Method library record
# --------------------------------------------------------------------------- #
class RetrievedMethod(MFBaseModel):
    """A method record from the library (spec 8.3 / 16.3).

    Invariant: retrieved methods MUST come from registered library entries.
    """

    method_id: str
    name: str
    category: MethodCategory
    summary: str = ""
    suitability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    use_cases: list[str] = Field(default_factory=list)
    applicability_conditions: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    advantages: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)
    computational_cost: str = "low"  # low | medium | high
    pilot_template: str = ""  # method key into the code template library
    implementation_template: str = ""
    visualization_templates: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
