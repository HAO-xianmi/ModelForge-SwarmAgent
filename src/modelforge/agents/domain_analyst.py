"""DomainAnalystAgent (spec 8.2)."""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.problem import DomainAnalysis, ProblemCard


class DomainAnalystAgent(BaseAgent[DomainAnalysis]):
    agent_key = "domain_analyst"
    output_schema = DomainAnalysis

    def analyze(self, problem_card: ProblemCard) -> AgentResult[DomainAnalysis]:
        context = {
            "title": problem_card.title,
            "problem_summary": problem_card.problem_summary,
            "objectives": problem_card.objectives,
            "datasets": [d.name for d in problem_card.datasets],
        }
        return self.run_structured(context)
