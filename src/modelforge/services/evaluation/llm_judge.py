"""Stabilized LLM judge panel.

Implements the five requirements for the LLM scoring layer:
  1. temperature = 0
  2. multiple judges (distinct personas / models)
  3. median aggregation (done in aggregate.py)
  4. evidence-backed justification (each score ships quoted spans)
  5. every span is later verified verbatim against the paper (aggregate.py)

Uses the existing ``LLMProvider`` Protocol and the versioned ``competition_judge``
prompt in the registry, so with the mock default the panel is deterministic and
keyless CI keeps working. With real providers, distinct personas produce genuine
inter-judge variation even at temperature 0.
"""

from __future__ import annotations

from modelforge.prompts.registry import get_prompt
from modelforge.providers.llm.base import (
    LLMProvider,
    Message,
    parse_structured,
)
from modelforge.schemas.base import MFBaseModel
from modelforge.schemas.evaluation import (
    JudgeVote,
    PaperDocument,
    StructuralMetrics,
)
from modelforge.services.evaluation.rubric import RUBRIC

# Distinct judging personas — the "multiple judges". Each emphasizes a different
# facet of real competition judging, yielding genuine variation with real models.
PERSONAS: list[tuple[str, str]] = [
    (
        "mcm_finalist",
        "You judge like an MCM/ICM finalist coach. Reward correct problem "
        "decomposition, justified model choice, and validation that beats a "
        "baseline. Penalize one generic model stretched across a multi-part "
        "problem.",
    ),
    (
        "cumcm_advisor",
        "You judge like a CUMCM national advisor. Weigh 假设合理性 (reasonable "
        "assumptions), 建模创造性 (modeling creativity), 结果正确性 (result "
        "correctness), 表述清晰 (clear exposition). Penalize results that do not "
        "match the problem domain.",
    ),
    (
        "red_team",
        "You judge like a skeptical red-team reviewer. Hunt for overfitting, "
        "data leakage, domain mismatch, unsupported numbers, and missing "
        "sensitivity analysis. Be hard to impress.",
    ),
]

# Cap paper text passed to the model to control token cost; the structural layer
# already saw the full document, so this only bounds the LLM's reading window.
_MAX_PAPER_CHARS = 18000


class _RawVote(MFBaseModel):
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    justifications: dict[str, str] = {}


class LLMJudgePanel:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        n_judges: int = 3,
        max_paper_chars: int = _MAX_PAPER_CHARS,
    ) -> None:
        self.provider = provider
        self.n_judges = max(1, n_judges)
        self.max_paper_chars = max_paper_chars

    def _personas(self) -> list[tuple[str, str]]:
        if self.n_judges <= len(PERSONAS):
            return PERSONAS[: self.n_judges]
        # Cycle if more judges than personas requested.
        return [PERSONAS[i % len(PERSONAS)] for i in range(self.n_judges)]

    def vote(
        self,
        doc: PaperDocument,
        metrics: StructuralMetrics,
        structural_scores: dict[str, float],
    ) -> tuple[list[JudgeVote], list[str]]:
        """Return (votes, notes). One vote per judge; notes flag failures."""
        prompt = get_prompt("competition_judge")
        dims = [
            {"dimension_id": d.dimension_id, "name": d.name, "criteria": d.llm_criteria}
            for d in RUBRIC
        ]
        context = {
            "title": doc.title,
            "paper_text": doc.raw_text[: self.max_paper_chars],
            "dimensions": dims,
            # Hints only (judge the paper). The mock uses these to grade.
            "detected_signals": metrics.model_dump(exclude={"evidence"}),
            "structural_scores": structural_scores,
            "evidence_pool": metrics.evidence,
        }
        is_mock = getattr(self.provider, "name", "") == "mock"
        votes: list[JudgeVote] = []
        notes: list[str] = []
        for judge_id, persona in self._personas():
            if is_mock:
                system, user = prompt.render("competition_judge", context)
            else:
                system, user = prompt.render_for_real_llm(context)
            system = f"{system}\n\nJudge persona: {persona}"
            try:
                resp = self.provider.complete(
                    [Message(role="system", content=system),
                     Message(role="user", content=user)],
                    temperature=0.0,
                    max_tokens=2048,
                )
                raw = parse_structured(resp.text, _RawVote)
            except Exception as exc:  # noqa: BLE001 — one bad judge must not abort
                notes.append(f"judge {judge_id} failed: {type(exc).__name__}")
                continue
            votes.append(
                JudgeVote(
                    judge_id=judge_id,
                    scores={k: _clamp(v) for k, v in raw.scores.items()},
                    evidence=raw.evidence,
                    justifications=raw.justifications,
                )
            )
        if not votes:
            notes.append("all judges failed; LLM layer unavailable")
        return votes, notes


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(10.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
