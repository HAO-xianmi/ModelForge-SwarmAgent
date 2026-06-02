"""Run coordinator (spec 7.5) — the top-level orchestration API.

Creates runs, ingests inputs, starts/advances the workflow, and resolves
checkpoints. This is what the CLI and FastAPI call; it owns the lifecycle and
keeps the blackboard persisted via the run repository.
"""

from __future__ import annotations

from modelforge.common.config import OperatingMode, get_settings
from modelforge.common.ids import new_run_id
from modelforge.graph.deps import WorkflowDeps
from modelforge.graph.workflow import Workflow
from modelforge.schemas.control import HumanFeedback
from modelforge.schemas.enums import (
    ActorType,
    CheckpointAction,
    CheckpointId,
    EventType,
    RunStatus,
)
from modelforge.schemas.state import ModelingState, Run
from modelforge.services.compliance import ComplianceEngine, load_profile
from modelforge.services.ingestion import UploadedFile
from modelforge.storage.database import Database
from modelforge.storage.repositories import RunRepository
from modelforge.storage.run_directory import RunDirectory


class RunCoordinator:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.run_repo = RunRepository(db)

    # ------------------------------------------------------------------ #
    def create_run(
        self,
        *,
        mode: str = OperatingMode.PRACTICE.value,
        competition_profile: str = "practice",
        budget_profile: str = "standard",
    ) -> Run:
        run_id = new_run_id()
        RunDirectory(run_id).create()
        profile = load_profile(competition_profile)
        run = Run(
            run_id=run_id,
            mode=mode,
            competition_profile_id=profile.profile_id,
            budget_profile=budget_profile,
        )
        state = ModelingState(run_id=run_id, mode=mode, competition_profile=profile)
        self.run_repo.create_run(run, state)
        return run

    def add_files(self, run_id: str, uploads: list[UploadedFile]) -> ModelingState:
        state = self._load(run_id)
        deps = self._deps(state)
        manifest = deps.ingestion.ingest(run_id, uploads)
        # Merge with any existing manifest.
        if state.input_manifest is None:
            state.input_manifest = manifest
        else:
            state.input_manifest.files.extend(manifest.files)
            state.input_manifest.problem_text = (
                state.input_manifest.problem_text + "\n\n" + manifest.problem_text
            ).strip()
            state.input_manifest.total_size_bytes += manifest.total_size_bytes
        self.run_repo.audit.record(
            run_id, EventType.INGESTION_COMPLETED, payload={"files": len(manifest.files)}
        )
        self.run_repo.save_state(
            state, actor="ingestion", actor_type=ActorType.SERVICE, reason="files ingested"
        )
        return state

    def start(self, run_id: str) -> ModelingState:
        state = self._load(run_id)
        if state.status is RunStatus.CREATED:
            state.status = RunStatus.PARSING
        deps = self._deps(state)
        workflow = Workflow(deps)
        state = workflow.run(state)
        return state

    def resolve_checkpoint(
        self,
        run_id: str,
        checkpoint_id: str,
        action: CheckpointAction,
        *,
        user_id: str = "user",
        comments: str = "",
        edits: dict | None = None,
    ) -> ModelingState:
        state = self._load(run_id)
        deps = self._deps(state)
        workflow = Workflow(deps)
        feedback = HumanFeedback(
            checkpoint_id=checkpoint_id,
            user_id=user_id,
            action=action,
            comments=comments,
            edits=edits or {},
        )
        cp = workflow.checkpoints.resolve(state, feedback)
        self.run_repo.audit.record(
            run_id,
            EventType.CHECKPOINT_RESOLVED,
            actor_type=ActorType.HUMAN,
            actor_id=user_id,
            payload={"checkpoint": cp.kind.value, "action": action.value},
        )

        # Apply the decision to the run status.
        next_status = self._status_after_checkpoint(state, cp.kind, action, edits or {})
        state.status = next_status
        self.run_repo.save_state(
            state,
            actor=user_id,
            actor_type=ActorType.HUMAN,
            reason=f"checkpoint {cp.kind.value} resolved: {action.value}",
        )
        if action is CheckpointAction.CANCEL_RUN:
            return state

        # Continue execution (or run export after the final checkpoint).
        if cp.kind is CheckpointId.FINAL_REPORT and next_status is RunStatus.EXPORTING:
            return workflow.export(state)
        return workflow.run(state)

    def cancel(self, run_id: str) -> ModelingState:
        state = self._load(run_id)
        state.status = RunStatus.CANCELLED
        self.run_repo.audit.record(run_id, EventType.RUN_CANCELLED)
        self.run_repo.save_state(
            state, actor="user", actor_type=ActorType.HUMAN, reason="run cancelled"
        )
        return state

    # ------------------------------------------------------------------ #
    def get_state(self, run_id: str) -> ModelingState | None:
        return self.run_repo.load_state(run_id)

    def _load(self, run_id: str) -> ModelingState:
        state = self.run_repo.load_state(run_id)
        if state is None:
            raise ValueError(f"run not found: {run_id}")
        return state

    def _deps(self, state: ModelingState) -> WorkflowDeps:
        profile = state.competition_profile or load_profile("practice")
        compliance = ComplianceEngine(profile)
        return WorkflowDeps.build(self.db, compliance)

    def _status_after_checkpoint(
        self,
        state: ModelingState,
        kind: CheckpointId,
        action: CheckpointAction,
        edits: dict,
    ) -> RunStatus:
        if action is CheckpointAction.CANCEL_RUN:
            return RunStatus.CANCELLED
        if action is CheckpointAction.REJECT_AND_RETRY:
            # Return to the stage that produced the checkpoint's inputs.
            return {
                CheckpointId.PROBLEM_UNDERSTANDING: RunStatus.PARSING,
                CheckpointId.STRATEGY_SELECTION: RunStatus.GENERATING_STRATEGIES,
                CheckpointId.FINAL_REPORT: RunStatus.WRITING_REPORT,
            }[kind]
        # APPROVE / APPROVE_WITH_EDITS / RETURN_TO_STAGE -> advance.
        if action is CheckpointAction.APPROVE_WITH_EDITS:
            self._apply_edits(state, kind, edits)
        return {
            CheckpointId.PROBLEM_UNDERSTANDING: RunStatus.RETRIEVING_METHODS,
            CheckpointId.STRATEGY_SELECTION: RunStatus.PROFILING_DATA,
            CheckpointId.FINAL_REPORT: RunStatus.EXPORTING,
        }[kind]

    def _apply_edits(self, state: ModelingState, kind: CheckpointId, edits: dict) -> None:
        if kind is CheckpointId.STRATEGY_SELECTION and "selected_strategy_id" in edits:
            chosen = state.strategy_by_id(edits["selected_strategy_id"])
            if chosen is not None:
                state.selected_strategy = chosen


def default_database() -> Database:
    db = Database(get_settings().database_url)
    db.create_all()
    return db
