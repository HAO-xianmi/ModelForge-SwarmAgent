"""`modelforge benchmark` — calibrate the rubric and evaluate papers.

The benchmark suite lives in the top-level ``benchmark/`` package (suite data +
harness). We add the repo root to ``sys.path`` so this command works from a
source checkout without installing the suite as a wheel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from rich.console import Console

# Windows consoles default to a legacy codepage (e.g. gbk) that cannot encode
# the report's unicode (CJK evidence spans, math symbols). Force UTF-8 so the
# CLI never crashes on output; degrade unencodable chars rather than raising.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

benchmark_app = typer.Typer(
    add_completion=False,
    help="Calibrate the CompetitionJudge rubric and score modeling papers.",
)
console = Console()


@benchmark_app.command()
def calibrate(
    provider: str = typer.Option("mock", help="mock (default, deterministic) | real | openai | anthropic | deepseek"),
    judges: int = typer.Option(3, help="number of LLM judges in the panel"),
    margin: float = typer.Option(2.0, help="required min(award) - max(weak) separation"),
    out: Path | None = typer.Option(None, help="write a JSON result to this path"),
) -> None:
    """Score the labeled corpus and report the award-vs-weak separation."""
    from benchmark.reports import calibration_to_json, render_calibration_markdown
    from benchmark.runner import calibrate as run_calibrate

    cal = run_calibrate(provider=provider, n_judges=judges, margin=margin)
    console.print(render_calibration_markdown(cal), markup=False, highlight=False)
    if out is not None:
        out.write_text(calibration_to_json(cal), encoding="utf-8")
        console.print(f"[green]Wrote[/green] {out}")
    if not cal.passed:
        console.print("[red]Calibration gate FAILED[/red]")
        raise typer.Exit(1)


@benchmark_app.command()
def evaluate(
    paper: Path,
    provider: str = typer.Option("mock", help="mock | real | openai | anthropic | deepseek"),
    judges: int = typer.Option(3),
    out: Path | None = typer.Option(None, help="write a JSON report to this path"),
) -> None:
    """Score a single paper file and print its CompetitionJudge report."""
    from benchmark.reports import render_report_markdown, report_to_json
    from benchmark.runner import evaluate_paper

    report = evaluate_paper(paper, provider=provider, n_judges=judges)
    console.print(render_report_markdown(report), markup=False, highlight=False)
    if out is not None:
        out.write_text(report_to_json(report), encoding="utf-8")
        console.print(f"[green]Wrote[/green] {out}")


@benchmark_app.command(name="list")
def list_suite() -> None:
    """List benchmark problems and corpus tiers."""
    from benchmark.datasets import discover_corpus, list_problems, pending_tiers

    console.print("[bold]Problems:[/bold] " + ", ".join(list_problems()))
    for e in discover_corpus():
        console.print(f"  [{e.tier}] {e.paper_id}  ({e.problem_slug})")
    for tier, msg in pending_tiers().items():
        console.print(f"  [{tier}] [yellow]pending[/yellow] — {msg}")
