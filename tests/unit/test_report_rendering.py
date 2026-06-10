"""Slice 1c: competition-grade rendering + no claim-token leakage.

Covers root cause #6 (renderer could only emit headings/images) and the visible
leakage bug (report.pdf printed `claim_efa52f7c7a6b` into the body).
"""

from __future__ import annotations

from modelforge.agents.base import AgentContext
from modelforge.agents.paper_writer import PaperWriterAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.enums import ClaimStatus, ClaimType
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.report import ReportOutline, ReportSection
from modelforge.services.report.builder import (
    ReportBuilder,
    _markdown_to_latex,
    _strip_leaked_tokens,
)


# --------------------------------------------------------------------------- #
# Renderer
# --------------------------------------------------------------------------- #
def test_renderer_preserves_inline_and_display_math():
    md = "## Model\n\nThe relation is $y = a x + b$.\n\n$$\nE = m c^2\n$$\n"
    tex = _markdown_to_latex(md)
    assert "$y = a x + b$" in tex
    assert r"\[" in tex and r"\]" in tex
    assert "E = m c^2" in tex


def test_renderer_converts_markdown_table():
    md = "| Symbol | Description |\n|---|---|\n| $x$ | input |\n"
    tex = _markdown_to_latex(md)
    assert r"\begin{tabular}" in tex
    assert "Symbol" in tex and "input" in tex


def test_renderer_subsections_and_lists():
    tex = _markdown_to_latex("### Sub\n\n- first\n- second\n")
    assert r"\subsection*{Sub}" in tex
    assert r"\begin{itemize}" in tex and r"\item" in tex


# --------------------------------------------------------------------------- #
# Leakage
# --------------------------------------------------------------------------- #
def test_strip_leaked_tokens_removes_ids():
    s = "Result is good [claim_efa52f7c7a6b] and stable claim_deadbeef [ev:claim_x]."
    out = _strip_leaked_tokens(s)
    assert "claim_efa52f7c7a6b" not in out
    assert "claim_deadbeef" not in out
    assert "[ev:" not in out


def test_build_markdown_no_claim_tokens_leak():
    claim = EvidenceClaim(
        claim_id="claim_abc123",
        run_id="r",
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement="RMSE is 0.0112",
        verification_status=ClaimStatus.VERIFIED,
    )
    outline = ReportOutline(sections=[
        ReportSection(section_id="results", title="Results", required_claim_ids=["claim_abc123"])
    ])
    # Writer text cites the claim AND (simulating a sloppy LLM) leaks a raw id.
    texts = {"results": "We report RMSE [claim:claim_abc123]; see run claim_deadbeef999."}
    md, claim_map = ReportBuilder().build_markdown("T", outline, texts, [claim], [])
    assert "claim_abc123" not in md
    assert "claim_deadbeef999" not in md
    assert "[ev:" not in md
    assert "[E1]" in md  # clean reader-facing marker
    assert any(e.claim_id == "claim_abc123" for e in claim_map)


# --------------------------------------------------------------------------- #
# Writer content
# --------------------------------------------------------------------------- #
def _writer():
    return PaperWriterAgent(AgentContext(run_id="r", provider=MockProvider()))


def _sec(sid: str, title: str = "S") -> ReportSection:
    return ReportSection(section_id=sid, title=title)


def test_writer_enumerates_assumptions():
    res = _writer().write_section(
        _sec("assumptions", "Model Assumptions"), {},
        assumptions=["flat terrain", "uniform soil"],
    )
    assert "Assumption 1:" in res.output.text and "Assumption 2:" in res.output.text


def test_writer_emits_symbol_table():
    res = _writer().write_section(
        _sec("nomenclature", "Nomenclature"), {}, variables=["It", "Vk"]
    )
    assert "| Symbol | Description | Units |" in res.output.text


def test_writer_model_section_has_equation():
    res = _writer().write_section(_sec("model_P1", "Sub-problem P1 Model"), {})
    assert "$$" in res.output.text


def test_writer_sensitivity_has_table_and_relationship():
    res = _writer().write_section(_sec("sensitivity", "Sensitivity"), {})
    txt = res.output.text.lower()
    assert "sensitivity" in txt and "parameter" in txt
    assert "|" in res.output.text  # a table
