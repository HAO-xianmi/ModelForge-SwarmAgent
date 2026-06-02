"""Built-in demo: a small prediction run end to end (spec milestone 24)."""

from __future__ import annotations

from rich.console import Console

from modelforge.graph.coordinator import RunCoordinator, default_database
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile

_DEMO_CSV = (
    "f0,f1,f2,target\n"
    + "\n".join(
        f"{i * 0.1:.3f},{(i % 5) * 0.2:.3f},{(i % 3) * 0.3:.3f},"
        f"{2.0 * (i * 0.1) - 1.5 * ((i % 5) * 0.2) + (i % 4) * 0.1:.3f}"
        for i in range(80)
    )
    + "\n"
)

_DEMO_PROBLEM = (
    "A retailer wants to forecast a continuous demand signal from three numeric "
    "predictors. Build and validate a regression model and report its RMSE, with "
    "a baseline comparison and a sensitivity analysis."
)


def run_demo(console: Console, *, keep: bool = False) -> str:
    """Run the demo and return the run id."""
    db = default_database()
    db.create_all()
    coord = RunCoordinator(db)

    console.print("[bold cyan]ModelForge-Swarm demo[/bold cyan] — small prediction problem\n")
    run = coord.create_run(mode="practice", competition_profile="practice")
    console.print(f"Created run [bold]{run.run_id}[/bold]")

    coord.add_files(
        run.run_id,
        [
            UploadedFile("problem.txt", _DEMO_PROBLEM.encode()),
            UploadedFile("data.csv", _DEMO_CSV.encode()),
        ],
    )
    console.print("Ingested problem + dataset; running workflow (real sandbox execution)...")

    state = coord.start(run.run_id)
    # Practice mode auto-passes checkpoints; drive any remaining.
    for _ in range(8):
        if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            break
        if state.pending_checkpoint is not None:
            state = coord.resolve_checkpoint(
                run.run_id, state.pending_checkpoint.checkpoint_id, CheckpointAction.APPROVE
            )
        else:
            state = coord.start(run.run_id)

    if state.status is not RunStatus.COMPLETED:
        console.print(f"[red]Run ended with status {state.status.value}[/red]")
        if state.failure_state:
            console.print(state.failure_state.detail)
        return run.run_id

    console.print("\n[green]Run completed.[/green]")
    formal = next(
        (e for e in state.experiment_records if e.experiment_type.value == "FORMAL"), None
    )
    if formal and formal.metrics:
        console.print(f"  Formal experiment metrics (from real execution): {formal.metrics}")
    console.print(f"  Verified evidence claims: {len(state.verified_claims())}")
    console.print(f"  Estimated cost (USD): {state.budget_state.estimated_cost_usd:.4f}")
    console.print(f"  Sandbox runtime (s): {state.budget_state.sandbox_runtime_seconds:.1f}")
    if state.export_state.bundle_path:
        console.print(f"\n  Reproducibility bundle: [bold]{state.export_state.bundle_path}[/bold]")
    if not keep:
        console.print("\n(Use --keep to retain the run directory.)")
    return run.run_id
