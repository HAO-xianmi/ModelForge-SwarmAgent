"""CompetitionWriterAgent (Phase H, Slice 3a).

A stronger writer that turns the KB-grounded domain model (governing equations,
assumptions, implementation hints) + the selected route into COHERENT
competition-paper prose — deriving and explaining each model, weaving its
equations into a narrative, and citing verified numbers. This is where Slice 2's
knowledge finally becomes content.

Evidence-gated: quantitative numbers come ONLY from verified claims (cited as
[claim:id], rendered to clean [E1] markers; the builder strips any raw id). With
a real provider this produces genuine modeling prose; the mock falls back to the
same clean scaffolding as PaperWriterAgent (D-H5: the mock must NOT dump raw
equations — that regresses a reasoning judge).
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.agents.paper_writer import SectionDraft
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.report import ReportSection


class CompetitionWriterAgent(BaseAgent[SectionDraft]):
    agent_key = "competition_writer"
    output_schema = SectionDraft

    def write_section(
        self,
        section: ReportSection,
        claim_index: dict[str, EvidenceClaim],
        *,
        assumptions: list[str] | None = None,
        variables: list[str] | None = None,
        domain_model: dict | None = None,
        route_name: str | None = None,
    ) -> AgentResult[SectionDraft]:
        usable_claims = [
            {"claim_id": cid, "statement": claim_index[cid].statement}
            for cid in section.required_claim_ids
            if cid in claim_index and claim_index[cid].usable_by_writer
        ]
        dm = domain_model or {}
        context = {
            "section_id": section.section_id,
            "title": section.title,
            "purpose": section.purpose,
            "claims": usable_claims,
            "figure_ids": section.required_figure_ids,
            "table_ids": section.required_table_ids,
            "word_budget": section.word_budget,
            "assumptions": assumptions or [],
            "variables": variables or [],
            "route_name": route_name or "",
            # Full KB content for a model section — the real writer weaves these
            # equations + assumptions into a derivation; the mock ignores them.
            "domain_model": {
                "name": dm.get("name", ""),
                "summary": dm.get("summary", ""),
                "governing_equations": dm.get("governing_equations", []),
                "assumptions": dm.get("assumptions", []),
                "implementation_hints": dm.get("implementation_hints", []),
                "validation_methods": dm.get("validation_methods", []),
                "references": dm.get("references", []),
            },
        }
        return self.run_structured(context, temperature=0.35, max_tokens=1400)
