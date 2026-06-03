"""CompetitionJudge orchestrator.

Wires the layers: PaperDocument -> structural metrics + structural scores ->
stabilized LLM panel -> aggregate (median + evidence verification + blend) ->
CompetitionJudgeReport.

This is the reusable engine. A later spec wires it into the existing
``run_judge_panel`` workflow node (the "full multi-judge panel" it promises);
the benchmark harness uses it offline.
"""

from __future__ import annotations

from modelforge.providers.llm.base import LLMProvider
from modelforge.providers.llm.factory import get_llm_provider
from modelforge.schemas.evaluation import CompetitionJudgeReport, PaperDocument
from modelforge.services.evaluation.aggregate import aggregate
from modelforge.services.evaluation.llm_judge import LLMJudgePanel
from modelforge.services.evaluation.rubric import DEFAULT_W_LLM, DEFAULT_W_STRUCT
from modelforge.services.evaluation.structural import (
    extract_metrics,
    structural_dimension_scores,
)


class CompetitionJudge:
    def __init__(
        self,
        provider: LLMProvider | None = None,
        *,
        n_judges: int = 3,
        w_struct: float = DEFAULT_W_STRUCT,
        w_llm: float = DEFAULT_W_LLM,
    ) -> None:
        self.provider = provider or get_llm_provider()
        self.panel = LLMJudgePanel(self.provider, n_judges=n_judges)
        self.w_struct = w_struct
        self.w_llm = w_llm

    def score(self, doc: PaperDocument) -> CompetitionJudgeReport:
        metrics = extract_metrics(doc)
        structural_scores = structural_dimension_scores(metrics)
        votes, notes = self.panel.vote(doc, metrics, structural_scores)
        return aggregate(
            doc,
            metrics,
            structural_scores,
            votes,
            provider=getattr(self.provider, "name", "unknown"),
            w_struct=self.w_struct,
            w_llm=self.w_llm,
            notes=notes,
        )
