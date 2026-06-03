"""CompetitionJudge evaluation framework (paper-level multi-judge panel).

Public surface:
    CompetitionJudge   — orchestrator: PaperDocument -> CompetitionJudgeReport
    ingest_text        — build a PaperDocument from raw text
    RUBRIC, RUBRIC_VERSION
"""

from __future__ import annotations

from modelforge.services.evaluation.ingest import ingest_paper, ingest_text
from modelforge.services.evaluation.judge import CompetitionJudge
from modelforge.services.evaluation.rubric import RUBRIC, RUBRIC_VERSION

__all__ = [
    "RUBRIC",
    "RUBRIC_VERSION",
    "CompetitionJudge",
    "ingest_paper",
    "ingest_text",
]
