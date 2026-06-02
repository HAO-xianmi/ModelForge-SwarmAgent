"""Run a bundled example end to end.

Usage:
    python examples/run_example.py simple_prediction
    python examples/run_example.py allocation_optimization
    python examples/run_example.py network_analysis

Uses the mock LLM provider (no API key) and the local subprocess sandbox, so it
runs anywhere with the Python dependencies installed. Prints the real metrics
and the path to the reproducibility bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console

from modelforge.graph.coordinator import RunCoordinator, default_database
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile

EXAMPLES = ("simple_prediction", "allocation_optimization", "network_analysis")


def main(name: str) -> int:
    console = Console()
    if name not in EXAMPLES:
        console.print(f"[red]Unknown example:[/red] {name}. Choose from {EXAMPLES}")
        return 2

    example_dir = Path(__file__).parent / name
    uploads = []
    for filename in ("problem.txt", "data.csv"):
        path = example_dir / filename
        if path.exists():
            uploads.append(UploadedFile(filename=filename, data=path.read_bytes()))

    db = default_database()
    db.create_all()
    coord = RunCoordinator(db)
    run = coord.create_run(mode="practice", competition_profile="practice")
    console.print(f"[cyan]Example:[/cyan] {name}  ->  run {run.run_id}")
    coord.add_files(run.run_id, uploads)

    state = coord.start(run.run_id)
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
        console.print(f"[red]Ended with {state.status.value}[/red]")
        if state.failure_state:
            console.print(state.failure_state.detail)
        return 1

    formal = next(
        (e for e in state.experiment_records if e.experiment_type.value == "FORMAL"), None
    )
    console.print("[green]Completed.[/green]")
    if formal:
        console.print(f"  metrics (real execution): {formal.metrics}")
    console.print(f"  verified claims: {len(state.verified_claims())}")
    console.print(f"  bundle: {state.export_state.bundle_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "simple_prediction"))
