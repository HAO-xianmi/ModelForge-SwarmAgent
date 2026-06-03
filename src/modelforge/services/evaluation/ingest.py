"""Build a normalized :class:`PaperDocument` from raw text.

Language-agnostic: handles Chinese, English, and mixed papers in markdown, LaTeX,
or plain text. PDF -> text extraction is a documented one-time prep step done
OUTSIDE the scoring hot path (PDF extraction varies by library/version, which
would break repeatability), so this module consumes already-extracted text.
"""

from __future__ import annotations

import re
from pathlib import Path

from modelforge.schemas.evaluation import PaperDocument

_CJK = re.compile(r"[一-鿿]")
_WORD = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


def detect_language(text: str) -> str:
    cjk = len(_CJK.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    total = cjk + latin
    if total == 0:
        return "mixed"
    cjk_frac = cjk / total
    if cjk_frac > 0.6:
        return "zh"
    if cjk_frac < 0.1:
        return "en"
    return "mixed"


def count_words(text: str) -> int:
    """Word count that treats each CJK character as a word (no spaces in zh)."""
    return len(_WORD.findall(text))


def _first_title(text: str) -> str:
    for line in text.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            return s[:120]
    return "Untitled paper"


def ingest_text(
    raw_text: str,
    *,
    paper_id: str,
    title: str | None = None,
    source_format: str = "txt",
    problem_slug: str | None = None,
    tier: str | None = None,
    source: str | None = None,
) -> PaperDocument:
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    return PaperDocument(
        paper_id=paper_id,
        title=title or _first_title(text),
        raw_text=text,
        source_format=source_format,
        language=detect_language(text),
        word_count=count_words(text),
        problem_slug=problem_slug,
        tier=tier,
        source=source,
    )


def ingest_paper(
    path: str | Path,
    *,
    paper_id: str | None = None,
    problem_slug: str | None = None,
    tier: str | None = None,
    source: str | None = None,
) -> PaperDocument:
    p = Path(path)
    fmt = {".md": "md", ".tex": "tex", ".markdown": "md"}.get(p.suffix.lower(), "txt")
    return ingest_text(
        p.read_text(encoding="utf-8"),
        paper_id=paper_id or p.stem,
        source_format=fmt,
        problem_slug=problem_slug,
        tier=tier,
        source=source,
    )
