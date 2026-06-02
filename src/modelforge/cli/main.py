"""ModelForge-Swarm CLI (spec milestone 20).

Commands: init, create-run, upload, start, status, events, artifacts,
checkpoints, resolve-checkpoint, export, demo, doctor.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from modelforge.cli import doctor as doctor_mod
from modelforge.graph.coordinator import RunCoordinator, default_database
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile

app = typer.Typer(
    add_completion=False,
    help="ModelForge-Swarm: an auditable multi-agent copilot for mathematical modeling.",
)
console = Console()


def _coordinator() -> RunCoordinator:
    return RunCoordinator(default_database())


@app.command()
def init() -> None:
    """Initialize the database and runs directory."""
    db = default_database()
    db.create_all()
    from modelforge.common.config import get_settings

    settings = get_settings()
    settings.runs_path.mkdir(parents=True, exist_ok=True)
    console.print(f"[green]Initialized[/green] db + runs dir at {settings.runs_path}")


@app.command(name="create-run")
def create_run(
    mode: str = typer.Option("practice", help="practice | contest_compliant | research"),
    profile: str = typer.Option("practice", help="competition profile id"),
    budget: str = typer.Option("standard", help="budget profile"),
) -> None:
    """Create a new run and print its id."""
    coord = _coordinator()
    run = coord.create_run(mode=mode, competition_profile=profile, budget_profile=budget)
    console.print(f"[green]Created run[/green] {run.run_id} (mode={mode}, profile={profile})")


@app.command()
def upload(run_id: str, files: list[Path]) -> None:
    """Upload one or more input files to a run."""
    coord = _coordinator()
    uploads = [UploadedFile(filename=p.name, data=p.read_bytes()) for p in files]
    state = coord.add_files(run_id, uploads)
    n = len(state.input_manifest.files) if state.input_manifest else 0
    console.print(f"[green]Uploaded[/green] {len(uploads)} file(s); run now has {n} input file(s)")


@app.command()
def start(run_id: str) -> None:
    """Start (or continue) the workflow until a checkpoint or completion."""
    coord = _coordinator()
    state = coord.start(run_id)
    _print_status(state.status, run_id)
    if state.pending_checkpoint is not None:
        console.print(
            f"[yellow]Paused at checkpoint[/yellow] "
            f"{state.pending_checkpoint.checkpoint_id}\n"
            f"Resolve with: modelforge resolve-checkpoint {run_id} "
            f"{state.pending_checkpoint.checkpoint_id} APPROVE"
        )


@app.command()
def status(run_id: str) -> None:
    """Show a run's status, stage, budget, and counts."""
    coord = _coordinator()
    state = coord.get_state(run_id)
    if state is None:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(1)
    table = Table(title=f"Run {run_id}")
    table.add_column("field")
    table.add_column("value")
    table.add_row("status", state.status.value)
    table.add_row("mode", state.mode)
    table.add_row("strategies", str(len(state.strategy_candidates)))
    table.add_row("experiments", str(len(state.experiment_records)))
    table.add_row("verified claims", str(len(state.verified_claims())))
    table.add_row("input tokens", str(state.budget_state.input_tokens))
    table.add_row("est. cost (USD)", f"{state.budget_state.estimated_cost_usd:.4f}")
    table.add_row("sandbox runtime (s)", f"{state.budget_state.sandbox_runtime_seconds:.1f}")
    if state.pending_checkpoint:
        table.add_row("pending checkpoint", state.pending_checkpoint.checkpoint_id)
    if state.failure_state:
        table.add_row("failure", state.failure_state.detail)
    console.print(table)


@app.command()
def events(run_id: str, limit: int = typer.Option(40)) -> None:
    """Show recent audit events for a run."""
    coord = _coordinator()
    evts = coord.run_repo.audit.list_for_run(run_id)[-limit:]
    table = Table(title=f"Events for {run_id}")
    table.add_column("time")
    table.add_column("event")
    table.add_column("actor")
    for e in evts:
        table.add_row(e.timestamp.strftime("%H:%M:%S"), e.event_type.value, e.actor_id)
    console.print(table)


@app.command()
def artifacts(run_id: str) -> None:
    """List registered artifacts for a run."""
    from modelforge.storage.repositories import ArtifactRegistry

    coord = _coordinator()
    registry = ArtifactRegistry(coord.db)
    table = Table(title=f"Artifacts for {run_id}")
    table.add_column("type")
    table.add_column("filename")
    table.add_column("size")
    for a in registry.list_for_run(run_id):
        table.add_row(a.artifact_type.value, a.filename, str(a.size_bytes))
    console.print(table)


@app.command()
def checkpoints(run_id: str) -> None:
    """Show the pending checkpoint (if any) and resolved history."""
    coord = _coordinator()
    state = coord.get_state(run_id)
    if state is None:
        console.print(f"[red]Run not found:[/red] {run_id}")
        raise typer.Exit(1)
    if state.pending_checkpoint:
        console.print(f"[yellow]Pending:[/yellow] {state.pending_checkpoint.checkpoint_id}")
        console.print(state.pending_checkpoint.context)
    else:
        console.print("[green]No pending checkpoint.[/green]")
    for fb in state.human_feedback:
        console.print(f"  resolved {fb.checkpoint_id}: {fb.action.value} by {fb.user_id}")


@app.command(name="resolve-checkpoint")
def resolve_checkpoint(
    run_id: str,
    checkpoint_id: str,
    action: str = typer.Argument("APPROVE"),
    comments: str = typer.Option(""),
) -> None:
    """Resolve a pending checkpoint (APPROVE, REJECT_AND_RETRY, CANCEL_RUN, ...)."""
    coord = _coordinator()
    try:
        cp_action = CheckpointAction(action)
    except ValueError:
        console.print(f"[red]Invalid action:[/red] {action}")
        raise typer.Exit(1) from None
    state = coord.resolve_checkpoint(run_id, checkpoint_id, cp_action, comments=comments)
    _print_status(state.status, run_id)
    if state.pending_checkpoint is not None:
        console.print(f"[yellow]Next checkpoint:[/yellow] {state.pending_checkpoint.checkpoint_id}")


@app.command()
def export(run_id: str, out: Path | None = typer.Option(None)) -> None:
    """Show (or copy) the reproducibility bundle path for a completed run."""
    coord = _coordinator()
    state = coord.get_state(run_id)
    if state is None or not state.export_state.bundle_path:
        console.print("[red]No export available[/red] (run not completed?)")
        raise typer.Exit(1)
    src = Path(state.export_state.bundle_path)
    if out is not None:
        out.write_bytes(src.read_bytes())
        console.print(f"[green]Copied bundle to[/green] {out}")
    else:
        console.print(f"[green]Bundle:[/green] {src}")


@app.command()
def doctor() -> None:
    """Run environment diagnostics."""
    checks = doctor_mod.run_checks()
    table = Table(title="ModelForge-Swarm Doctor")
    table.add_column("check")
    table.add_column("status")
    table.add_column("detail")
    for c in checks:
        color = {"OK": "green", "WARN": "yellow", "FAIL": "red"}[c["status"]]
        table.add_row(c["name"], f"[{color}]{c['status']}[/{color}]", c["detail"])
    console.print(table)
    if not doctor_mod.all_required_pass(checks):
        console.print("[red]One or more required checks failed.[/red]")
        raise typer.Exit(1)
    console.print("[green]All required checks passed.[/green]")


@app.command()
def demo(
    keep: bool = typer.Option(False, help="keep the demo run directory after finishing"),
) -> None:
    """Run a built-in prediction example end to end and print the result."""
    from modelforge.cli.demo import run_demo

    run_demo(console, keep=keep)


def _print_status(status: RunStatus, run_id: str) -> None:
    color = {
        RunStatus.COMPLETED: "green",
        RunStatus.FAILED: "red",
        RunStatus.CANCELLED: "yellow",
    }.get(status, "cyan")
    console.print(f"Run {run_id}: [{color}]{status.value}[/{color}]")


if __name__ == "__main__":  # pragma: no cover
    app()
