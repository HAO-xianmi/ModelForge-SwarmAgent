"""ProblemParserAgent (spec 8.1)."""

from __future__ import annotations

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.problem import InputManifest, ProblemCard


class ProblemParserAgent(BaseAgent[ProblemCard]):
    agent_key = "problem_parser"
    output_schema = ProblemCard

    def parse(self, manifest: InputManifest) -> AgentResult[ProblemCard]:
        # The problem text is untrusted DATA; the prompt instructs the model to
        # treat it as such and not follow embedded instructions (spec 30.3).
        context = {
            "problem_text": manifest.problem_text[:8000],
            "datasets": [f.normalized_name for f in manifest.by_role("data")],
            "file_roles": {f.normalized_name: f.role for f in manifest.files},
        }
        return self.run_structured(context)
