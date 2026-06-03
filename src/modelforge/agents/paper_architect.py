"""PaperArchitectAgent (spec 8.9).

Designs the outline from VERIFIED evidence only. After the model proposes
sections, the agent filters every ``required_*_id`` down to ids that actually
exist in the verified evidence/figure/table/citation sets — enforcing the
invariant that no section requests unsupported claims.
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.problem import ProblemCard
from modelforge.schemas.report import ReportOutline


class PaperArchitectAgent(BaseAgent[ReportOutline]):
    agent_key = "paper_architect"
    output_schema = ReportOutline

    def architect(
        self,
        title: str,
        verified_claims: list[EvidenceClaim],
        figure_ids: list[str],
        table_ids: list[str],
        citations: list[CitationRecord],
        problem_card: ProblemCard | None = None,
    ) -> AgentResult[ReportOutline]:
        claim_ids = [c.claim_id for c in verified_claims]
        citation_ids = [c.citation_id for c in citations if c.includable_in_report]
        # Thread the problem decomposition through so the outline addresses each
        # sub-problem with its own model section (instead of a generic skeleton).
        subproblems = (
            [
                {"sub_id": sp.sub_id, "statement": sp.statement, "objective": sp.objective}
                for sp in problem_card.subproblems
            ]
            if problem_card
            else []
        )
        context = {
            "title": title,
            "claim_ids": claim_ids,
            "figure_ids": figure_ids,
            "table_ids": table_ids,
            "citation_ids": citation_ids,
            "subproblems": subproblems,
            "assumptions": problem_card.assumptions_to_confirm if problem_card else [],
            "variables": (
                (problem_card.variables or problem_card.decision_variables)
                if problem_card
                else []
            ),
            "objectives": problem_card.objectives if problem_card else [],
        }
        result = self.run_structured(context, temperature=0.2)
        if result.ok and result.output is not None:
            self._filter_to_existing(
                result.output, set(claim_ids), set(figure_ids), set(table_ids),
                set(citation_ids),
            )
        return result

    @staticmethod
    def _filter_to_existing(
        outline: ReportOutline,
        claim_ids: set[str],
        figure_ids: set[str],
        table_ids: set[str],
        citation_ids: set[str],
    ) -> None:
        for section in outline.sections:
            section.required_claim_ids = [c for c in section.required_claim_ids if c in claim_ids]
            section.required_figure_ids = [
                f for f in section.required_figure_ids if f in figure_ids
            ]
            section.required_table_ids = [t for t in section.required_table_ids if t in table_ids]
            section.required_citation_ids = [
                c for c in section.required_citation_ids if c in citation_ids
            ]
