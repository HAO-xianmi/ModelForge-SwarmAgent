"""Deterministic structural scorer.

Pure functions over a :class:`PaperDocument`: no I/O, no network, no LLM, no
randomness. Identical input ALWAYS yields identical output — this is the
reproducible backbone (>=40% of the final score) and the part that is hard to
fake with superficial padding because the detectors look for *load-bearing*
structure (real equations, baselines, sensitivity tables), not just headings.

Detectors are language-agnostic (Chinese + English) and format-agnostic
(markdown / LaTeX / plain text). Each raw count is mapped to a 0-10 dimension
score by fixed, documented thresholds.
"""

from __future__ import annotations

import re

from modelforge.schemas.evaluation import PaperDocument, StructuralMetrics

# --------------------------------------------------------------------------- #
# Detectors (return match lists so we can expose example evidence spans)
# --------------------------------------------------------------------------- #

_SUBPROBLEM = re.compile(
    r"(?:问题[一二三四五六七八]|针对问题[一二三四五六七八]?|子问题|"
    r"\bproblem\s*\d|\bpart\s*[1-9]\b|\bsub[-_ ]?problem\b|\bQ[1-9]\b|\bsub_\d)",
    re.IGNORECASE,
)
_EQUATION = re.compile(
    r"(?:\\begin\{(?:equation|align|gather)\}|\$\$|\\\[|\\frac|\\sum|\\sqrt|"
    r"\\partial|\\times|≈|×\s*\d|=\s*[^=\n]{0,40}[+\-*/^]\s*[^=\n]{0,40})"
)
_NUMBERED_EQ = re.compile(r"(?:（\s*\d+(?:[.\-]\d+)?\s*）|\(\s*\d+(?:[.\-]\d+)?\s*\))")
_TABLE = re.compile(r"(?:表\s*\d|\bTable\s*\d|\\begin\{table\}|\\begin\{tabular\})", re.IGNORECASE)
_MD_TABLE_ROW = re.compile(r"^\s*\|.+\|\s*$", re.MULTILINE)
_FIGURE = re.compile(
    r"(?:图\s*\d|\bFig(?:ure)?\.?\s*\d|\\includegraphics|!\[)", re.IGNORECASE
)
_BASELINE = re.compile(
    r"(?:baseline|基线|基准模型|对比模型|对照模型|多元线性回归|"
    r"\bvs\.?\b|相比之下|benchmark model)",
    re.IGNORECASE,
)
_SENSITIVITY = re.compile(
    r"(?:sensitivity|灵敏度|敏感性|robustness|鲁棒性|稳健性|扰动分析|"
    r"参数.{0,4}影响|应急储备.{0,8}概率)",
    re.IGNORECASE,
)
_ASSUMPTION = re.compile(
    r"(?:假设[一二三四五六七八\d]|模型假设|\bassumption\s*\d|we assume\b|"
    r"假定[一二三四五六七八\d])",
    re.IGNORECASE,
)
_SYMBOL_TABLE = re.compile(
    r"(?:符号说明|符号表|notation table|list of symbols|nomenclature|"
    r"符号\s+(?:说明|含义)|symbol\s+(?:description|meaning))",
    re.IGNORECASE,
)
_CV = re.compile(
    r"(?:cross[- ]?validation|交叉验证|\bk[- ]?fold\b|\bCV\b|留一法|折交叉)",
    re.IGNORECASE,
)
_VAL_METRIC = re.compile(
    r"(?:\bRMSE\b|\bMAE\b|\bMAPE\b|\bR2\b|R²|R\^?2|准确率|\baccuracy\b|"
    r"\bF1\b|\bAUC\b|决定系数|均方根误差)",
    re.IGNORECASE,
)
_REFERENCE_HEADER = re.compile(r"(?:参考文献|references|bibliography)", re.IGNORECASE)
_REFERENCE_ITEM = re.compile(r"(?:^\s*\[\d+\]|^\s*\d+\.\s+[A-Z一-鿿])", re.MULTILINE)

# Canonical sections we expect in a strong modeling paper (zh + en synonyms).
_CANONICAL_SECTIONS = {
    "abstract": r"(?:摘要|abstract)",
    "restatement": r"(?:问题重述|问题分析|introduction|problem statement|background)",
    "assumptions": r"(?:模型假设|假设|assumptions)",
    "model": r"(?:模型(?:的)?建立|模型建立|model (?:formulation|construction)|methods?|methodology)",
    "results": r"(?:求解|结果|results|experiments?)",
    "conclusion": r"(?:结论|模型评价|conclusion|discussion)",
    "references": r"(?:参考文献|references|bibliography)",
}


def _examples(pattern: re.Pattern[str], text: str, k: int = 3) -> list[str]:
    out: list[str] = []
    for m in pattern.finditer(text):
        s = m.group(0).strip()
        if s and s not in out:
            out.append(s[:60])
        if len(out) >= k:
            break
    return out


def extract_metrics(doc: PaperDocument) -> StructuralMetrics:
    text = doc.raw_text

    n_sub = len(set(m.group(0).lower() for m in _SUBPROBLEM.finditer(text)))
    n_eq = len(_EQUATION.findall(text)) + len(_NUMBERED_EQ.findall(text))
    n_tables = len(_TABLE.findall(text)) + (
        1 if _MD_TABLE_ROW.search(text) else 0
    )
    n_figs = len(_FIGURE.findall(text))
    n_assume = len(_ASSUMPTION.findall(text))
    n_refs = len(_REFERENCE_ITEM.findall(text)) if _REFERENCE_HEADER.search(text) else 0

    present = {
        name: bool(re.search(pat, text, re.IGNORECASE))
        for name, pat in _CANONICAL_SECTIONS.items()
    }
    completeness = sum(present.values()) / len(_CANONICAL_SECTIONS)

    evidence = {
        "subproblems": _examples(_SUBPROBLEM, text),
        "equations": _examples(_EQUATION, text),
        "tables": _examples(_TABLE, text),
        "figures": _examples(_FIGURE, text),
        "baseline": _examples(_BASELINE, text),
        "sensitivity": _examples(_SENSITIVITY, text),
        "assumptions": _examples(_ASSUMPTION, text),
        "symbol_table": _examples(_SYMBOL_TABLE, text),
        "cross_validation": _examples(_CV, text),
    }

    return StructuralMetrics(
        n_subproblems=n_sub,
        n_equations=n_eq,
        n_tables=n_tables,
        n_figures=n_figs,
        n_assumptions=n_assume,
        n_references=n_refs,
        n_sections=sum(present.values()),
        has_baseline=bool(_BASELINE.search(text)),
        has_sensitivity=bool(_SENSITIVITY.search(text)),
        has_symbol_table=bool(_SYMBOL_TABLE.search(text)),
        has_cross_validation=bool(_CV.search(text)),
        has_validation_metrics=bool(_VAL_METRIC.search(text)),
        section_completeness=round(completeness, 4),
        word_count=doc.word_count,
        evidence={k: v for k, v in evidence.items() if v},
    )


# --------------------------------------------------------------------------- #
# Count -> 0-10 score mappings (fixed, documented thresholds)
# --------------------------------------------------------------------------- #
def _threshold(value: float, steps: list[tuple[float, float]]) -> float:
    """steps = ascending [(min_value, score)]; returns score for the highest
    threshold the value meets."""
    score = 0.0
    for minv, s in steps:
        if value >= minv:
            score = s
    return score


def structural_dimension_scores(m: StructuralMetrics) -> dict[str, float]:
    """Return {dimension_id: 0-10} for the structurally-scored dimensions."""
    decomposition = _threshold(
        m.n_subproblems, [(0, 0.0), (1, 3.0), (2, 6.0), (3, 8.5), (4, 10.0)]
    )
    modeling_depth = _threshold(
        m.n_equations,
        [(0, 0.0), (1, 2.0), (3, 4.0), (6, 6.0), (11, 8.0), (21, 10.0)],
    )
    assumptions = 5.0 * min(1.0, m.n_assumptions / 3.0) + (
        5.0 if m.has_symbol_table else 0.0
    )
    validation = (5.0 if m.has_baseline else 0.0) + (
        5.0 if (m.has_cross_validation or m.has_validation_metrics) else 0.0
    )
    sensitivity = 10.0 if m.has_sensitivity else 0.0
    evidence_density = m.n_figures + m.n_tables
    results = _threshold(
        evidence_density,
        [(0, 0.0), (1, 2.5), (3, 5.0), (6, 7.0), (10, 8.5), (16, 10.0)],
    )
    writing = 5.0 * m.section_completeness + 5.0 * min(1.0, m.n_references / 5.0)

    return {
        "decomposition": round(decomposition, 4),
        "modeling_depth": round(modeling_depth, 4),
        "assumptions": round(min(10.0, assumptions), 4),
        "validation": round(min(10.0, validation), 4),
        "sensitivity": round(sensitivity, 4),
        "results": round(results, 4),
        "writing": round(min(10.0, writing), 4),
    }
