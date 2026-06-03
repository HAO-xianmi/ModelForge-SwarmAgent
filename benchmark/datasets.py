"""Pluggable calibration-dataset registry.

A dataset entry is a labeled paper: ``(tier, problem_slug, source, path)``.
Adding a paper = drop a text file under ``corpus/<tier>/`` + a ``labels.json``
entry; no code change. Empty tiers (e.g. ``average``) are skipped gracefully.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from modelforge.schemas.evaluation import KNOWN_TIERS
from modelforge.services.evaluation.ingest import ingest_paper

BENCHMARK_ROOT = Path(__file__).resolve().parent
CORPUS_ROOT = BENCHMARK_ROOT / "corpus"
PROBLEMS_ROOT = BENCHMARK_ROOT / "problems"
LABELS_PATH = CORPUS_ROOT / "labels.json"


@dataclass(frozen=True)
class CorpusEntry:
    paper_id: str
    tier: str
    problem_slug: str
    source: str
    path: Path


def load_labels() -> dict:
    if not LABELS_PATH.exists():
        return {"papers": [], "tiers_pending": {}}
    return json.loads(LABELS_PATH.read_text(encoding="utf-8"))


def discover_corpus() -> list[CorpusEntry]:
    """Return labeled corpus entries whose files exist on disk."""
    labels = load_labels()
    entries: list[CorpusEntry] = []
    for rec in labels.get("papers", []):
        path = CORPUS_ROOT / rec["file"]
        if not path.exists():
            continue
        entries.append(
            CorpusEntry(
                paper_id=Path(rec["file"]).stem,
                tier=rec.get("tier", "unknown"),
                problem_slug=rec.get("problem_slug", "unknown"),
                source=rec.get("source", ""),
                path=path,
            )
        )
    return entries


def populated_tiers() -> list[str]:
    seen = {e.tier for e in discover_corpus()}
    return [t for t in KNOWN_TIERS if t in seen]


def pending_tiers() -> dict[str, str]:
    return load_labels().get("tiers_pending", {})


def load_corpus_documents():
    """Yield (entry, PaperDocument) for every discovered corpus paper."""
    for e in discover_corpus():
        doc = ingest_paper(
            e.path,
            paper_id=e.paper_id,
            problem_slug=e.problem_slug,
            tier=e.tier,
            source=e.source,
        )
        yield e, doc


def list_problems() -> list[str]:
    if not PROBLEMS_ROOT.exists():
        return []
    return sorted(p.name for p in PROBLEMS_ROOT.iterdir() if p.is_dir())
