"""StrategyJudgeAgent (spec 8.6).

The decision MUST reference actual pilot evidence when available — the agent
passes pilot success + metrics into the context, and the prompt forbids
inventing metrics or ignoring failed experiments.
"""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.strategy import (
    JudgeReport,
    PilotExperiment,
    SkepticReport,
    StrategyCandidate,
)


class StrategyJudgeAgent(BaseAgent[JudgeReport]):
    agent_key = "strategy_judge"
    output_schema = JudgeReport

    def judge(
        self,
        candidates: list[StrategyCandidate],
        skeptic_report: SkepticReport | None,
        pilots: list[PilotExperiment],
    ) -> AgentResult[JudgeReport]:
        context = {
            "strategy_ids": [c.strategy_id for c in candidates],
            "pilots": [
                {
                    "strategy_id": p.strategy_id,
                    "pilot_id": p.pilot_id,
                    "succeeded": p.succeeded,
                    "metrics": p.metrics,
                    "runtime_seconds": p.runtime_seconds,
                }
                for p in pilots
            ],
            "skeptic_recommendations": (
                {r.strategy_id: r.recommendation for r in skeptic_report.reviews}
                if skeptic_report
                else {}
            ),
        }
        return self.run_structured(context, temperature=0.1)
