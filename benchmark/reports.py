"""Render CompetitionJudgeReport / calibration results to markdown + JSON."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from modelforge.schemas.evaluation import CompetitionJudgeReport

if TYPE_CHECKING:
    from benchmark.runner import CalibrationResult


def report_to_json(report: CompetitionJudgeReport) -> str:
    return json.dumps(report.model_dump(), ensure_ascii=False, indent=2)


def render_report_markdown(report: CompetitionJudgeReport) -> str:
    lines = [
        f"# Judge report: {report.title}",
        "",
        f"- paper_id: `{report.paper_id}`  tier: `{report.tier or 'unknown'}`  "
        f"problem: `{report.problem_slug or 'unknown'}`",
        f"- provider: `{report.provider}`  judges: {report.n_judges}  "
        f"rubric: v{report.rubric_version}",
        f"- **final: {report.final_score:.2f} / 10**  "
        f"(structural {report.structural_subtotal:.2f} x {report.w_struct:.2f} + "
        f"LLM {report.llm_subtotal:.2f} x {report.w_llm:.2f})",
        "",
        "| dimension | struct | llm | final | evidence? |",
        "|---|---|---|---|---|",
    ]
    for d in report.dimension_scores:
        s = "-" if d.structural_score is None else f"{d.structural_score:.1f}"
        llm = "-" if d.llm_score is None else f"{d.llm_score:.1f}"
        flag = "! unverified" if d.evidence_unverified else ("yes" if d.evidence else "-")
        lines.append(f"| {d.name} | {s} | {llm} | {d.final_score:.1f} | {flag} |")
    m = report.structural_metrics
    lines += [
        "",
        "## Structural signals (deterministic)",
        f"- subproblems: {m.n_subproblems}  equations: {m.n_equations}  "
        f"tables: {m.n_tables}  figures: {m.n_figures}",
        f"- assumptions: {m.n_assumptions}  references: {m.n_references}  "
        f"section_completeness: {m.section_completeness:.2f}",
        f"- baseline: {m.has_baseline}  sensitivity: {m.has_sensitivity}  "
        f"symbol_table: {m.has_symbol_table}  CV: {m.has_cross_validation}  "
        f"val_metrics: {m.has_validation_metrics}",
    ]
    if report.notes:
        lines += ["", "## Notes", *[f"- {n}" for n in report.notes]]
    return "\n".join(lines) + "\n"


def render_calibration_markdown(cal: CalibrationResult) -> str:
    verdict = "PASS" if cal.passed else "FAIL"
    lines = [
        "# CompetitionJudge calibration",
        "",
        f"- provider: `{cal.provider}`  judges: {cal.n_judges}  "
        f"margin: {cal.margin}",
        f"- **separation (min award - max weak): "
        f"{'n/a' if cal.separation is None else f'{cal.separation:.2f}'}**  "
        f"(needs >= {cal.margin})",
        f"- separation_ok: {cal.separation_ok}  ordering_ok: {cal.ordering_ok}",
        f"- **verdict: {verdict}**",
        "",
        "## Scores by tier",
        "| tier | n | mean | min | max |",
        "|---|---|---|---|---|",
    ]
    for tier in ("award", "average", "weak"):
        ts = cal.by_tier.get(tier)
        if ts and ts.n:
            lines.append(
                f"| {tier} | {ts.n} | {ts.mean:.2f} | {ts.min:.2f} | {ts.max:.2f} |"
            )
        else:
            pend = cal.pending.get(tier)
            lines.append(f"| {tier} | 0 | — | — | — | {('(' + pend + ')') if pend else ''}")
    lines += ["", "## Per-paper", "| paper | tier | final |", "|---|---|---|"]
    ranked = sorted(cal.reports, key=lambda r: r.final_score, reverse=True)
    for r in ranked:
        lines.append(f"| {r.paper_id} | {r.tier or '?'} | {r.final_score:.2f} |")
    if cal.notes:
        lines += ["", "## Notes", *[f"- {n}" for n in cal.notes]]
    return "\n".join(lines) + "\n"


def calibration_to_json(cal: CalibrationResult) -> str:
    payload = {
        "provider": cal.provider,
        "n_judges": cal.n_judges,
        "margin": cal.margin,
        "separation": cal.separation,
        "separation_ok": cal.separation_ok,
        "ordering_ok": cal.ordering_ok,
        "passed": cal.passed,
        "by_tier": {
            t: {"n": ts.n, "mean": ts.mean, "min": ts.min, "max": ts.max,
                "scores": ts.scores}
            for t, ts in cal.by_tier.items()
        },
        "pending": cal.pending,
        "notes": cal.notes,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
