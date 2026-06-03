"""Benchmark harness: calibrate the rubric and evaluate papers.

Default provider is the deterministic **mock** so calibration is repeatable and
keyless-CI-safe (a real LLM panel is opt-in via ``provider="real"``). The
separation gate asserts that award papers outscore weak papers by a margin over
the *populated* tiers, so an empty ``average`` tier never blocks the run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean

from modelforge.providers.llm.base import LLMProvider
from modelforge.providers.llm.mock import MockProvider
from modelforge.schemas.evaluation import (
    TIER_AVERAGE,
    TIER_AWARD,
    TIER_WEAK,
    CompetitionJudgeReport,
)
from modelforge.services.evaluation.ingest import ingest_paper
from modelforge.services.evaluation.judge import CompetitionJudge

from benchmark.datasets import discover_corpus, load_corpus_documents, pending_tiers

DEFAULT_MARGIN = 2.0


def make_provider(name: str = "mock") -> LLMProvider:
    """Resolve a provider by name. 'mock' (default) is deterministic/keyless;
    'real' uses the configured backend; or name a specific backend."""
    name = (name or "mock").lower()
    if name == "mock":
        return MockProvider()
    from modelforge.common.config import LLMBackend
    from modelforge.providers.llm.factory import get_llm_provider

    if name == "real":
        return get_llm_provider()
    return get_llm_provider(LLMBackend(name))


@dataclass
class TierStats:
    tier: str
    scores: list[tuple[str, float]] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.scores)

    @property
    def values(self) -> list[float]:
        return [s for _, s in self.scores]

    @property
    def mean(self) -> float:
        return mean(self.values) if self.values else 0.0

    @property
    def min(self) -> float:
        return min(self.values) if self.values else 0.0

    @property
    def max(self) -> float:
        return max(self.values) if self.values else 0.0


@dataclass
class CalibrationResult:
    provider: str
    n_judges: int
    margin: float
    reports: list[CompetitionJudgeReport]
    by_tier: dict[str, TierStats]
    separation: float | None  # min(award) - max(weak), populated tiers only
    separation_ok: bool
    ordering_ok: bool
    pending: dict[str, str]
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.separation_ok and self.ordering_ok


def calibrate(
    *,
    provider: str = "mock",
    n_judges: int = 3,
    margin: float = DEFAULT_MARGIN,
) -> CalibrationResult:
    prov = make_provider(provider)
    judge = CompetitionJudge(prov, n_judges=n_judges)

    reports: list[CompetitionJudgeReport] = []
    by_tier: dict[str, TierStats] = {}
    for entry, doc in load_corpus_documents():
        report = judge.score(doc)
        reports.append(report)
        by_tier.setdefault(entry.tier, TierStats(entry.tier)).scores.append(
            (entry.paper_id, report.final_score)
        )

    notes: list[str] = []
    award = by_tier.get(TIER_AWARD)
    weak = by_tier.get(TIER_WEAK)
    average = by_tier.get(TIER_AVERAGE)

    separation: float | None = None
    separation_ok = False
    if award and weak:
        separation = round(award.min - weak.max, 4)
        separation_ok = separation >= margin
    else:
        notes.append("separation not evaluable: need both award and weak tiers")

    # Ordering: every award > every weak; and award.mean > average.mean > weak.mean
    # over whichever tiers are populated.
    ordering_ok = True
    if award and weak:
        ordering_ok = all(a > w for a in award.values for w in weak.values)
    if average and average.n:
        if award and not (award.mean > average.mean):
            ordering_ok = False
        if weak and not (average.mean > weak.mean):
            ordering_ok = False
    else:
        notes.append("average tier empty (pending real samples); ordering checked over award vs weak")

    return CalibrationResult(
        provider=getattr(prov, "name", provider),
        n_judges=n_judges,
        margin=margin,
        reports=reports,
        by_tier=by_tier,
        separation=separation,
        separation_ok=separation_ok,
        ordering_ok=ordering_ok,
        pending=pending_tiers(),
        notes=notes,
    )


def evaluate_paper(
    path: str | Path,
    *,
    provider: str = "mock",
    n_judges: int = 3,
    problem_slug: str | None = None,
) -> CompetitionJudgeReport:
    prov = make_provider(provider)
    judge = CompetitionJudge(prov, n_judges=n_judges)
    doc = ingest_paper(path, problem_slug=problem_slug)
    return judge.score(doc)


def corpus_size() -> int:
    return len(discover_corpus())


def generate_and_score(
    slug: str, *, provider: str = "mock", n_judges: int = 3
) -> CompetitionJudgeReport:
    """Generate a report for a benchmark problem via the rebuilt path and score it."""
    from modelforge.services.evaluation.ingest import ingest_text

    from benchmark.datasets import PROBLEMS_ROOT
    from benchmark.generate import generate_report_for_slug

    prov = make_provider(provider)
    markdown, _audit = generate_report_for_slug(slug, prov, PROBLEMS_ROOT)
    judge = CompetitionJudge(prov, n_judges=n_judges)
    return judge.score(
        ingest_text(markdown, paper_id=f"generated_{slug}", problem_slug=slug)
    )


def generate_all(
    *, provider: str = "mock", n_judges: int = 3
) -> dict[str, CompetitionJudgeReport]:
    """Generate + score a report for every benchmark problem category."""
    from benchmark.datasets import list_problems

    return {
        slug: generate_and_score(slug, provider=provider, n_judges=n_judges)
        for slug in list_problems()
    }
