"""SensitivityPlannerAgent (Phase H, Slice 3c).

Designs the parameter->outcome sensitivity experiment a competition paper needs:
which key parameters to perturb, over what range, what outcomes to record, and
the method (one-at-a-time / Monte-Carlo / leave-one-out). Grounded in the
retrieved domain models' sensitivity_methods.
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.competition import SensitivityPlan
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, SubProblem
from modelforge.services.method_library.domain_models import get_domain_model_library


class SensitivityPlannerAgent(BaseAgent[SensitivityPlan]):
    agent_key = "sensitivity_planner"
    output_schema = SensitivityPlan

    def plan(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        *,
        subproblem: SubProblem | None = None,
    ) -> AgentResult[SensitivityPlan]:
        statement = subproblem.statement if subproblem else problem_card.problem_summary
        models = get_domain_model_library().retrieve(
            statement, domain_analysis.likely_problem_families, top_k=2
        )
        context = {
            "subproblem_id": subproblem.sub_id if subproblem else None,
            "statement": statement[:300],
            "sensitivity_methods": [s for m in models for s in m.sensitivity_methods][:6],
            "model_names": [m.name for m in models],
        }
        return self.run_structured(context, temperature=0.3, max_tokens=900)
