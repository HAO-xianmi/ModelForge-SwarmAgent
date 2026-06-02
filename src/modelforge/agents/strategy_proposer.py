"""StrategyProposerAgent (spec 8.4).

Three instances run independently with different design goals. Each proposer is
isolated — it does not see the others' drafts before submitting (spec 17.2).
The agent injects the retrieved-method ids + a method->template map so the
proposed strategy is guaranteed to have a runnable pilot.
"""

from __future__ import annotations

from modelforge.agents.base import AgentContext, AgentResult, BaseAgent
from modelforge.schemas.enums import StrategyGoal
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, RetrievedMethod
from modelforge.schemas.strategy import StrategyCandidate
from modelforge.services.method_library import get_method_library


class StrategyProposerAgent(BaseAgent[StrategyCandidate]):
    agent_key = "strategy_proposer"
    output_schema = StrategyCandidate

    def __init__(self, ctx: AgentContext, design_goal: StrategyGoal) -> None:
        super().__init__(ctx)
        self.design_goal = design_goal

    def propose(
        self,
        problem_card: ProblemCard,
        domain_analysis: DomainAnalysis,
        methods: list[RetrievedMethod],
    ) -> AgentResult[StrategyCandidate]:
        library = get_method_library()
        method_ids = [m.method_id for m in methods]
        template_for_method = {
            m.method_id: m.pilot_template for m in methods if m.pilot_template
        }
        # Fill in templates for any library method not in the retrieved subset.
        for mid in method_ids:
            if mid not in template_for_method:
                lib_method = library.get(mid)
                if lib_method:
                    template_for_method[mid] = lib_method.pilot_template

        context = {
            "design_goal": self.design_goal.value,
            "problem_family": domain_analysis.primary_family.value,
            "strategy_id": f"strategy_{self.design_goal.value}_001",
            "candidate_methods": method_ids,
            "template_for_method": template_for_method,
            "objectives": problem_card.objectives,
        }
        result = self.run_structured(context, temperature=0.4)
        # Defense in depth: guarantee a runnable template even if the model omits it.
        if result.ok and result.output is not None and not result.output.pilot_template:
            fallback = template_for_method.get(
                result.output.method_stack[0].method_id
                if result.output.method_stack
                else "",
                domain_analysis.primary_family.value,
            )
            result.output.pilot_template = fallback or domain_analysis.primary_family.value
        return result
