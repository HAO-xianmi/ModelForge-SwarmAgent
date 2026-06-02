"""Phase G: the three bundled examples run end to end (mock LLM, real sandbox).

This protects the examples (prediction / optimization / graph) and exercises
those problem families through the FULL workflow, not just codegen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelforge.graph.coordinator import RunCoordinator
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile
from modelforge.storage.database import Database

pytestmark = pytest.mark.e2e

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture()
def coordinator(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("MODELFORGE_LLM", "mock")
    from modelforge.common import config

    config.get_settings.cache_clear()
    db = Database(f"sqlite:///{(tmp_path / 'ex.db').as_posix()}")
    db.create_all()
    yield RunCoordinator(db)
    config.get_settings.cache_clear()


def _run_example(coord: RunCoordinator, name: str):
    example_dir = EXAMPLES_DIR / name
    uploads = []
    for filename in ("problem.txt", "data.csv"):
        path = example_dir / filename
        if path.exists():
            uploads.append(UploadedFile(filename=filename, data=path.read_bytes()))
    run = coord.create_run(mode="practice", competition_profile="practice")
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
    return coord.get_state(run.run_id)


@pytest.mark.parametrize(
    "name,family,metric",
    [
        ("simple_prediction", "prediction", "rmse"),
        ("allocation_optimization", "optimization", "objective_value"),
        ("network_analysis", "graph", "n_nodes"),
    ],
)
def test_example_runs_to_completion(coordinator, name, family, metric) -> None:
    state = _run_example(coordinator, name)
    assert state.status is RunStatus.COMPLETED, (name, state.failure_state)
    assert state.selected_strategy is not None
    assert state.selected_strategy.problem_family.value == family, (
        f"{name}: expected family {family}, got "
        f"{state.selected_strategy.problem_family.value}"
    )
    formal = next(
        (e for e in state.experiment_records if e.experiment_type.value == "FORMAL"), None
    )
    assert formal is not None and metric in formal.metrics, (
        f"{name}: missing metric {metric}; got {sorted(formal.metrics) if formal else None}"
    )
    # On real (non-synthetic) data.
    assert formal.metrics.get("synthetic_data") == 0.0
    assert state.export_state.bundle_path
    assert Path(state.export_state.bundle_path).exists()
