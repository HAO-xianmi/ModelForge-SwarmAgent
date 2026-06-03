"""Slice 2d: the generate harness runs the rebuilt path for every category.

Validates the report-GENERATION path (parse -> domain -> routes + tournament ->
architect -> writer -> builder) produces a clean, decomposed, leak-free report
for each benchmark problem. KB *content* injection is deferred to the Slice 3
real writer, so here we only assert structure + audit + no leakage.
"""

from __future__ import annotations

from pathlib import Path

from modelforge.providers.llm.mock import MockProvider
from benchmark.datasets import list_problems
from benchmark.generate import generate_report, generate_report_for_slug

_ROOT = Path(__file__).resolve().parents[2] / "benchmark" / "problems"


def test_generate_runs_for_every_category():
    prov = MockProvider()
    for slug in list_problems():
        md, audit = generate_report_for_slug(slug, prov, _ROOT)
        assert md.strip(), f"{slug} produced empty report"
        assert "## " in md  # has sections


def test_irrigation_report_is_decomposed_and_leak_free():
    md, audit = generate_report_for_slug("irrigation", MockProvider(), _ROOT)
    assert md.lower().count("sub-problem") >= 3  # multiple sub-problem sections
    assert "claim_" not in md  # no internal id leakage
    assert "[ev:" not in md


def test_generate_records_route_tournament_audit():
    _md, audit = generate_report_for_slug("irrigation", MockProvider(), _ROOT)
    assert audit, "no route-tournament audit trail recorded"
    assert any("selected" in line for line in audit)


def test_generate_extracts_subproblems_from_problem_text():
    md, _ = generate_report(
        "# Test Problem\n\n**Q1 (a).** First part.\n\n**Q2 (b).** Second part.\n",
        MockProvider(),
    )
    assert "Sub-problem P1" in md and "Sub-problem P2" in md


def test_generated_report_has_references_and_exports_to_latex():
    from modelforge.services.report.builder import ReportBuilder
    md, _ = generate_report_for_slug("irrigation", MockProvider(), _ROOT)
    assert "## References" in md  # citation tracking
    tex = ReportBuilder().build_latex("Irrigation", md, [])
    # LaTeX export is compilable-shaped and leak-free.
    assert r"\documentclass" in tex and r"\section*{" in tex
    assert "claim_" not in tex
