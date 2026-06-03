"""AssumptionIntelligenceAgent (Phase H, Slice 3b).

Produces a small set of explicit, NUMBERED, load-bearing assumptions — each with
a justification and a statement of what it simplifies — replacing the generic
"data is representative" placeholder. Grounded in the retrieved domain models'
assumptions so they are domain-appropriate.
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.competition import AssumptionSet
from modelforge.schemas.problem import DomainAnalysis, ProblemCard
from modelforge.services.method_library.domain_models import get_domain_model_library


class AssumptionIntelligenceAgent(BaseAgent[AssumptionSet]):
    agent_key = "assumption_agent"
    output_schema = AssumptionSet

    def generate(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        *,
        max_assumptions: int = 5,
    ) -> AgentResult[AssumptionSet]:
        text = " ".join(
            [problem_card.problem_summary, " ".join(domain_analysis.key_terms)]
        )
        models = get_domain_model_library().retrieve(
            text, domain_analysis.likely_problem_families, top_k=4
        )
        context = {
            "title": problem_card.title,
            "problem_summary": problem_card.problem_summary[:400],
            "existing_assumptions": problem_card.assumptions_to_confirm,
            "domain_assumptions": [a for m in models for a in m.assumptions][:8],
            "max_assumptions": max_assumptions,
        }
        return self.run_structured(context, temperature=0.3, max_tokens=1200)
