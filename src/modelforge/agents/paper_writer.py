"""PaperWriterAgent (spec 8.10).

Drafts each section's prose using ONLY the verified claims the architect assigned
to it. The agent passes the verified claim text/ids into context; the writer
cites them as ``[claim:<id>]``. It never adds new experimental values — numbers
come exclusively from the verified claims. Any section whose claims are missing
is written with an explicit "needs human review" marker rather than fabricated.
"""

from __future__ import annotations

from modelforge.agents.base import AgentContext, AgentResult, BaseAgent
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.report import ReportSection


class SectionDraft(MFBaseModel):
    section_id: str
    text: str


class PaperWriterAgent(BaseAgent[SectionDraft]):
    agent_key = "paper_writer"
    output_schema = SectionDraft

    def __init__(self, ctx: AgentContext) -> None:
        super().__init__(ctx)

    def write_section(
        self,
        section: ReportSection,
        claim_index: dict[str, EvidenceClaim],
    ) -> AgentResult[SectionDraft]:
        # Only claims that exist AND are writer-usable are passed in.
        usable_claims = [
            {"claim_id": cid, "statement": claim_index[cid].statement}
            for cid in section.required_claim_ids
            if cid in claim_index and claim_index[cid].usable_by_writer
        ]
        context = {
            "section_id": section.section_id,
            "title": section.title,
            "purpose": section.purpose,
            "claims": usable_claims,
            "figure_ids": section.required_figure_ids,
            "table_ids": section.required_table_ids,
            "word_budget": section.word_budget,
        }
        return self.run_structured(context, temperature=0.3, max_tokens=1024)
