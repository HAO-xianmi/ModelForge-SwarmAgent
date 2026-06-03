"""RouteGeneratorAgent (Phase H, Slice 2b).

Generates >= N substantially-different modeling routes for a (sub-)problem, each
grounded in the domain-model KB and/or generic methods and carrying its own
assumptions, advantages, limitations, risks, and expected per-criterion metrics.

"Substantially different" = different modeling *approach* (mechanistic vs
data-driven vs optimization vs simulation vs hybrid vs network), not a superficial
hyper-parameter tweak. The agent retrieves candidates from the KB; the mock
assembles distinct-approach routes deterministically, and a real LLM proposes
them from the same grounded context.
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, SubProblem
from modelforge.schemas.route import RouteSet
from modelforge.services.method_library import get_method_library
from modelforge.services.method_library.domain_models import get_domain_model_library

MIN_ROUTES = 5


class RouteGeneratorAgent(BaseAgent[RouteSet]):
    agent_key = "route_generator"
    output_schema = RouteSet

    def generate(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        *,
        subproblem: SubProblem | None = None,
        min_routes: int = MIN_ROUTES,
    ) -> AgentResult[RouteSet]:
        families = list(domain_analysis.likely_problem_families)
        statement = subproblem.statement if subproblem else problem_card.problem_summary
        text = " ".join(
            [problem_card.title, problem_card.problem_summary, statement,
             " ".join(domain_analysis.domain_tags), " ".join(domain_analysis.key_terms)]
        )
        domain_models = get_domain_model_library().retrieve(text, families, top_k=8)
        methods = get_method_library().retrieve(problem_card, domain_analysis, top_k=8)
        context = {
            "problem_family": families[0].value if families else "unknown",
            "subproblem_id": subproblem.sub_id if subproblem else None,
            "subproblem_statement": statement[:300],
            "min_routes": min_routes,
            "domain_models": [
                {
                    "model_id": m.model_id, "name": m.name, "approach": m.category,
                    "families": [f.value for f in m.families],
                    "summary": m.summary,
                    "assumptions": m.assumptions[:3], "advantages": m.advantages[:3],
                    "limitations": m.failure_modes[:3],
                }
                for m in domain_models
            ],
            "methods": [m.method_id for m in methods],
        }
        result = self.run_structured(context, temperature=0.4, max_tokens=2048)
        if result.ok and result.output is not None and subproblem is not None:
            result.output.subproblem_id = subproblem.sub_id
            for r in result.output.routes:
                r.subproblem_id = subproblem.sub_id
        return result
