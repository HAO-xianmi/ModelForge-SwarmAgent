"""End-to-end workflow test: a full prediction run from input to export.

Uses the deterministic MockProvider (no API key) and the real subprocess sandbox
(real experiments). Exercises the whole backbone: ingest -> parse -> domain ->
checkpoint 1 -> methods -> strategies -> skeptic -> pilots -> select ->
checkpoint 2 -> profile -> code -> sandbox -> baselines -> robustness -> audit ->
evidence -> report -> citations -> judge -> checkpoint 3 -> export.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from modelforge.common.config import LLMBackend, OperatingMode
from modelforge.graph.coordinator import RunCoordinator
from modelforge.providers.llm import MockProvider
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile
from modelforge.storage.database import Database

pytestmark = pytest.mark.e2e


TINY_PREDICTION_CSV = (
    "f0,f1,f2,target\n"
    + "\n".join(
        f"{i * 0.1:.3f},{(i % 5) * 0.2:.3f},{(i % 3) * 0.3:.3f},{i * 0.5 + (i % 4):.3f}"
        for i in range(60)
    )
    + "\n"
)

PROBLEM_TEXT = (
    "We need to forecast a continuous target value from three numeric features. "
    "Build a regression model, validate it, and report RMSE."
)


@pytest.fixture()
def coordinator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunCoordinator:
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(runs))
    monkeypatch.setenv("MODELFORGE_LLM", LLMBackend.MOCK.value)
    from modelforge.common import config

    config.get_settings.cache_clear()
    db = Database(f"sqlite:///{(tmp_path / 'e2e.db').as_posix()}")
    db.create_all()
    coord = RunCoordinator(db)
    yield coord
    config.get_settings.cache_clear()


def _resolve_all_checkpoints(coord: RunCoordinator, run_id: str) -> None:
    """Approve each pending checkpoint until the run is terminal."""
    for _ in range(10):
        state = coord.get_state(run_id)
        assert state is not None
        if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            return
        if state.pending_checkpoint is not None:
            coord.resolve_checkpoint(
                run_id,
                state.pending_checkpoint.checkpoint_id,
                CheckpointAction.APPROVE,
            )
        else:
            # Not paused and not terminal — drive forward.
            coord.start(run_id)
    raise AssertionError("run did not terminate within checkpoint budget")


def test_practice_mode_runs_to_completion_without_checkpoints(coordinator) -> None:
    """In practice mode, no checkpoints are required: one start() completes it."""
    run = coordinator.create_run(
        mode=OperatingMode.PRACTICE.value, competition_profile="practice"
    )
    coordinator.add_files(
        run.run_id,
        [
            UploadedFile("problem.txt", PROBLEM_TEXT.encode()),
            UploadedFile("data.csv", TINY_PREDICTION_CSV.encode()),
        ],
    )
    state = coordinator.start(run.run_id)
    # Practice mode auto-passes checkpoints, so the run reaches the final
    # checkpoint status (export is triggered by resolving it, or auto in
    # practice). Drive any remaining steps.
    if state.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
        _resolve_all_checkpoints(coordinator, run.run_id)
    final = coordinator.get_state(run.run_id)
    assert final is not None
    assert final.status is RunStatus.COMPLETED, final.failure_state

    # Real evidence exists and came from a real experiment.
    assert final.experiment_records
    formal = final.experiment_records[-1]
    assert formal.metrics  # produced by executed code
    assert final.verified_claims()  # evidence registered + verified
    assert final.judge_panel_reports and final.judge_panel_reports[-1].passed

    # A report and a reproducibility bundle were produced.
    assert final.report_artifacts is not None
    assert final.report_artifacts.markdown_artifact_id
    assert final.export_state.bundle_path
    bundle = Path(final.export_state.bundle_path)
    assert bundle.exists()


def test_bundle_contains_required_files(coordinator) -> None:
    run = coordinator.create_run(competition_profile="practice")
    coordinator.add_files(
        run.run_id,
        [
            UploadedFile("problem.txt", PROBLEM_TEXT.encode()),
            UploadedFile("data.csv", TINY_PREDICTION_CSV.encode()),
        ],
    )
    state = coordinator.start(run.run_id)
    if state.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
        _resolve_all_checkpoints(coordinator, run.run_id)
    final = coordinator.get_state(run.run_id)
    assert final.status is RunStatus.COMPLETED, final.failure_state

    data = Path(final.export_state.bundle_path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        judge_reports = zf.read("quality/judge_panel_reports.json")
    assert "report.md" in names
    assert "report.tex" in names
    assert "reproducibility_manifest.json" in names
    assert "artifact_manifest.json" in names
    assert "quality/judge_panel_reports.json" in names
    assert b'"passed": true' in judge_reports
    assert any(n.startswith("figures/") for n in names)
    assert any(n.startswith("code/") for n in names)


def test_contest_mode_pauses_at_checkpoints(coordinator) -> None:
    """Contest profile requires checkpoints: the run pauses for human approval."""
    run = coordinator.create_run(
        mode=OperatingMode.CONTEST_COMPLIANT.value, competition_profile="generic_contest"
    )
    coordinator.add_files(
        run.run_id,
        [
            UploadedFile("problem.txt", PROBLEM_TEXT.encode()),
            UploadedFile("data.csv", TINY_PREDICTION_CSV.encode()),
        ],
    )
    state = coordinator.start(run.run_id)
    # First pause: checkpoint 1.
    assert state.status is RunStatus.WAITING_FOR_CHECKPOINT_1
    assert state.pending_checkpoint is not None

    _resolve_all_checkpoints(coordinator, run.run_id)
    final = coordinator.get_state(run.run_id)
    assert final.status is RunStatus.COMPLETED, final.failure_state
    # Human approvals recorded in the bundle manifest.
    assert len(final.human_feedback) == 3  # three checkpoints resolved
    # Disclosure required in contest mode.
    assert final.export_state.disclosure_required is True


def test_mock_provider_does_not_fabricate_metrics(coordinator) -> None:
    """The mock drives reasoning; metrics come only from real execution."""
    provider = MockProvider()
    # The mock's strategy/judge outputs never contain experiment metric values
    # we did not compute. We assert the registered claims point at a real
    # experiment id (provenance), not a free-floating number.
    run = coordinator.create_run(competition_profile="practice")
    coordinator.add_files(
        run.run_id,
        [UploadedFile("data.csv", TINY_PREDICTION_CSV.encode())],
    )
    state = coordinator.start(run.run_id)
    if state.status not in (RunStatus.COMPLETED, RunStatus.FAILED):
        _resolve_all_checkpoints(coordinator, run.run_id)
    final = coordinator.get_state(run.run_id)
    assert final.status is RunStatus.COMPLETED, final.failure_state
    for claim in final.evidence_claims:
        if claim.is_quantitative and claim.metric_value is not None:
            assert claim.experiment_id is not None  # tied to a real run
    assert provider.name == "mock"
