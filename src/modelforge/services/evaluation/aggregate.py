"""Aggregate judge votes and blend the two scoring layers.

- median aggregation across judges (requirement 3)
- verbatim evidence verification: a quoted span is kept only if it actually
  occurs in the paper text (requirement 5) — hallucinated spans are dropped and
  the dimension flagged ``evidence_unverified``
- final = w_struct * structural_subtotal + w_llm * llm_subtotal, default
  0.40 / 0.60 (deterministic layer >= 40%, LLM layer <= 60%)
"""

from __future__ import annotations

import re
from statistics import median

from modelforge.schemas.evaluation import (
    CompetitionJudgeReport,
    DimensionScore,
    JudgeVote,
    PaperDocument,
    StructuralMetrics,
)
from modelforge.services.evaluation.rubric import (
    DEFAULT_W_LLM,
    DEFAULT_W_STRUCT,
    RUBRIC,
    RUBRIC_VERSION,
)

_WS = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS.sub(" ", text).strip()


def verify_evidence(spans: list[str], paper_text: str) -> tuple[list[str], bool]:
    """Return (verified_spans, had_unverified). A span is verified iff it occurs
    verbatim (whitespace-insensitive) in the paper text."""
    norm_paper = _normalize(paper_text)
    verified: list[str] = []
    had_unverified = False
    for span in spans:
        s = span.strip()
        if not s:
            continue
        if s in paper_text or _normalize(s) in norm_paper:
            verified.append(s)
        else:
            had_unverified = True
    return verified, had_unverified


def _median_or_none(values: list[float]) -> float | None:
    return float(median(values)) if values else None


def aggregate(
    doc: PaperDocument,
    metrics: StructuralMetrics,
    structural_scores: dict[str, float],
    votes: list[JudgeVote],
    *,
    provider: str,
    w_struct: float = DEFAULT_W_STRUCT,
    w_llm: float = DEFAULT_W_LLM,
    notes: list[str] | None = None,
) -> CompetitionJudgeReport:
    notes = list(notes or [])
    dim_scores: list[DimensionScore] = []

    struct_weight_sum = 0.0
    struct_weighted = 0.0
    llm_weight_sum = 0.0
    llm_weighted = 0.0

    for dim in RUBRIC:
        did = dim.dimension_id
        struct = structural_scores.get(did) if dim.has_structural else None

        # Median LLM score across judges that scored this dimension.
        llm_vals = [v.scores[did] for v in votes if did in v.scores]
        llm = _median_or_none(llm_vals) if dim.llm else None

        # Verify + collect evidence spans across judges.
        raw_spans: list[str] = []
        justification = ""
        for v in votes:
            raw_spans.extend(v.evidence.get(did, []))
            if not justification and v.justifications.get(did):
                justification = v.justifications[did]
        verified, had_unverified = verify_evidence(raw_spans, doc.raw_text)

        # Per-dimension display blend of whichever layers are present.
        if struct is not None and llm is not None:
            final = w_struct * struct + w_llm * llm
        elif struct is not None:
            final = struct
        elif llm is not None:
            final = llm
        else:
            final = 0.0

        if struct is not None:
            struct_weight_sum += dim.weight
            struct_weighted += dim.weight * struct
        if llm is not None:
            llm_weight_sum += dim.weight
            llm_weighted += dim.weight * llm

        dim_scores.append(
            DimensionScore(
                dimension_id=did,
                name=dim.name,
                structural_score=struct,
                llm_score=llm,
                final_score=round(final, 4),
                weight=dim.weight,
                evidence=verified[:4],
                justification=justification,
                evidence_unverified=had_unverified,
            )
        )

    structural_subtotal = (
        struct_weighted / struct_weight_sum if struct_weight_sum else 0.0
    )
    llm_subtotal = llm_weighted / llm_weight_sum if llm_weight_sum else None

    if llm_subtotal is None:
        notes.append("LLM layer unavailable; final score uses structural layer only")
        final_score = structural_subtotal
    else:
        final_score = w_struct * structural_subtotal + w_llm * llm_subtotal

    return CompetitionJudgeReport(
        paper_id=doc.paper_id,
        title=doc.title,
        final_score=round(final_score, 4),
        structural_subtotal=round(structural_subtotal, 4),
        llm_subtotal=round(llm_subtotal, 4) if llm_subtotal is not None else 0.0,
        w_struct=w_struct,
        w_llm=w_llm,
        n_judges=len(votes),
        provider=provider,
        dimension_scores=dim_scores,
        structural_metrics=metrics,
        rubric_version=RUBRIC_VERSION,
        notes=notes,
        problem_slug=doc.problem_slug,
        tier=doc.tier,
    )
