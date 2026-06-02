"""Report outline, sections, and report artifacts (spec 8.9, 8.10, 22)."""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel


class ReportSection(MFBaseModel):
    """One outline section (spec 8.9).

    Invariant: no section may request unsupported claims — the architect only
    references claim/figure/table IDs that exist in the evidence registry.
    """

    section_id: str
    title: str
    purpose: str = ""
    required_claim_ids: list[str] = Field(default_factory=list)
    required_figure_ids: list[str] = Field(default_factory=list)
    required_table_ids: list[str] = Field(default_factory=list)
    required_citation_ids: list[str] = Field(default_factory=list)
    word_budget: int = 200
    human_review_required: bool = False


class ReportOutline(MFBaseModel):
    sections: list[ReportSection] = Field(default_factory=list)
    title: str = ""
    template: str = "generic"


class ClaimMapEntry(MFBaseModel):
    section_id: str
    paragraph_id: str = ""
    sentence_id: str = ""
    claim_id: str
    evidence_artifact_ids: list[str] = Field(default_factory=list)


class ReportArtifacts(MFBaseModel):
    """References to generated report files (spec 22.2)."""

    markdown_artifact_id: str | None = None
    latex_artifact_id: str | None = None
    pdf_artifact_id: str | None = None
    bib_artifact_id: str | None = None
    claim_map: list[ClaimMapEntry] = Field(default_factory=list)
    markdown_path: str | None = None
    latex_path: str | None = None
    pdf_path: str | None = None
    compiled_pdf: bool = False
    compilation_log: str = ""
