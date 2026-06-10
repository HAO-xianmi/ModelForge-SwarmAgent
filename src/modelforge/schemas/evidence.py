"""Evidence claims and citations (spec 12, 23).

The Evidence Registry is a hard requirement: the report writer may only use
VERIFIED claims (and explicitly-marked NEEDS_HUMAN_REVIEW). REJECTED and PENDING
quantitative claims MUST NOT become factual statements (spec 12.5).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from modelforge.common.timeutil import utcnow
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.enums import CitationStatus, ClaimStatus, ClaimType
from modelforge.schemas.problem import SourceReference


class EvidenceClaim(MFBaseModel):
    """A registered claim with provenance (spec 12.4 / Appendix D).

    A QUANTITATIVE_RESULT / MODEL_COMPARISON claim must link to an experiment and
    carry metric values that came from that experiment. A LITERATURE_STATEMENT
    must link to citations.
    """

    claim_id: str
    run_id: str
    subproblem_id: str | None = None
    claim_type: ClaimType
    statement: str
    verification_status: ClaimStatus = ClaimStatus.PENDING
    experiment_id: str | None = None
    metric_name: str | None = None
    metric_value: dict | float | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    metric_refs: list[str] = Field(default_factory=list)
    table_refs: list[str] = Field(default_factory=list)
    figure_refs: list[str] = Field(default_factory=list)
    source_map: list[SourceReference] = Field(default_factory=list)
    citation_ids: list[str] = Field(default_factory=list)
    verified_by: str | None = None
    source_notes: str = ""
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _sync_artifact_aliases(self) -> EvidenceClaim:
        """Keep legacy ``artifact_ids`` and explicit source ids compatible."""
        if self.artifact_ids and not self.source_artifact_ids:
            object.__setattr__(self, "source_artifact_ids", list(self.artifact_ids))
        elif self.source_artifact_ids and not self.artifact_ids:
            object.__setattr__(self, "artifact_ids", list(self.source_artifact_ids))
        if self.metric_name and not self.metric_refs:
            object.__setattr__(self, "metric_refs", [self.metric_name])
        return self

    @property
    def is_quantitative(self) -> bool:
        return self.claim_type in {
            ClaimType.QUANTITATIVE_RESULT,
            ClaimType.MODEL_COMPARISON,
            ClaimType.ROBUSTNESS_CONCLUSION,
        }

    @property
    def usable_by_writer(self) -> bool:
        """Spec 12.5 writer-access rule."""
        # NEEDS_HUMAN_REVIEW is usable only when explicitly marked in the draft;
        # the writer enforces that surface rule.
        return self.verification_status in {
            ClaimStatus.VERIFIED,
            ClaimStatus.NEEDS_HUMAN_REVIEW,
        }

    @property
    def all_artifact_ids(self) -> list[str]:
        return list(dict.fromkeys([*self.source_artifact_ids, *self.artifact_ids]))


class CitationRecord(MFBaseModel):
    """A citation with verification metadata (spec 23.3).

    The system MUST NOT invent citations; unresolved/rejected ones are excluded
    from export (spec 23.4).
    """

    citation_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    venue: str = ""
    doi: str = ""
    url: str = ""
    source_provider: str = "local"
    retrieved_at: datetime | None = None
    verification_status: CitationStatus = CitationStatus.UNRESOLVED
    verification_notes: str = ""
    used_in_claim_ids: list[str] = Field(default_factory=list)

    @property
    def includable_in_report(self) -> bool:
        return self.verification_status in {
            CitationStatus.VERIFIED,
            CitationStatus.PARTIALLY_VERIFIED,
        }

    def bibtex_key(self) -> str:
        first_author = self.authors[0].split()[-1].lower() if self.authors else "anon"
        return f"{first_author}{self.year or 'nd'}"
