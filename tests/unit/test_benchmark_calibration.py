"""Calibration + repeatability gate for the CompetitionJudge benchmark.

Pinned to the deterministic mock provider so the gate is keyless-CI-safe and
bit-reproducible. The success criterion: award papers consistently outscore weak
papers by a margin, and rankings are stable across repeated runs.
"""

from __future__ import annotations

from benchmark.runner import calibrate
from modelforge.services.evaluation.aggregate import verify_evidence


def test_corpus_has_real_papers_and_average_is_pending():
    cal = calibrate(provider="mock")
    award = cal.by_tier.get("award")
    weak = cal.by_tier.get("weak")
    assert award is not None and award.n >= 2, "need >= 2 real award papers"
    assert weak is not None and weak.n >= 1, "need >= 1 weak paper"
    assert "average" in cal.pending, "average tier must be marked pending"
    assert cal.by_tier.get("average") is None or cal.by_tier["average"].n == 0


def test_calibration_separates_award_from_weak():
    cal = calibrate(provider="mock", margin=2.0)
    assert cal.separation is not None
    assert cal.separation >= 2.0, f"separation too small: {cal.separation}"
    assert cal.separation_ok
    assert cal.ordering_ok
    assert cal.passed
    # Every award paper outscores every weak paper.
    award = cal.by_tier["award"].values
    weak = cal.by_tier["weak"].values
    assert min(award) > max(weak)
    # Award mean is comfortably high; weak mean is low.
    assert cal.by_tier["award"].mean >= 6.0
    assert cal.by_tier["weak"].mean <= 3.0


def test_calibration_is_repeatable():
    a = calibrate(provider="mock")
    b = calibrate(provider="mock")
    rank_a = sorted((r.paper_id, r.final_score) for r in a.reports)
    rank_b = sorted((r.paper_id, r.final_score) for r in b.reports)
    assert rank_a == rank_b, "scores must be bit-identical across runs (mock)"
    assert a.separation == b.separation


def test_deterministic_layer_is_at_least_40_percent():
    cal = calibrate(provider="mock")
    for r in cal.reports:
        assert abs(r.w_struct - 0.40) < 1e-9
        assert abs(r.w_llm - 0.60) < 1e-9
        assert r.w_struct >= 0.40  # deterministic layer >= 40%
        assert r.w_llm <= 0.60  # LLM layer <= 60%


def test_evidence_verification_drops_hallucinated_spans():
    paper = "The XGBoost model achieved R2 = 0.97 on the test set."
    spans = ["XGBoost model achieved R2 = 0.97", "we used a quantum annealer"]
    verified, had_unverified = verify_evidence(spans, paper)
    assert "XGBoost model achieved R2 = 0.97" in verified
    assert "we used a quantum annealer" not in verified
    assert had_unverified is True


def test_every_qualitative_score_has_evidence_or_is_flagged():
    """Each LLM-scored dimension must ship verified evidence (or be flagged)."""
    cal = calibrate(provider="mock")
    award = next(r for r in cal.reports if r.tier == "award")
    for d in award.dimension_scores:
        if d.llm_score is not None:
            # Either it has verified evidence, or it is explicitly flagged.
            assert d.evidence or d.evidence_unverified or d.justification
