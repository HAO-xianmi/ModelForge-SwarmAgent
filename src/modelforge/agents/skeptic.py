"""SkepticAgent (spec 8.5)."""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.strategy import SkepticReport, StrategyCandidate


class SkepticAgent(BaseAgent[SkepticReport]):
    agent_key = "skeptic"
    output_schema = SkepticReport

    def review(self, candidates: list[StrategyCandidate]) -> AgentResult[SkepticReport]:
        context = {
            "strategy_ids": [c.strategy_id for c in candidates],
            "strategies": [
                {
                    "strategy_id": c.strategy_id,
                    "design_goal": c.design_goal.value,
                    "method_stack": [m.method_id for m in c.method_stack],
                    "assumptions": c.assumptions,
                }
                for c in candidates
            ],
        }
        return self.run_structured(context, temperature=0.3)
