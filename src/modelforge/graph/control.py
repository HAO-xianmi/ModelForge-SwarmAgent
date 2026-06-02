"""Control-plane components: budget manager, loop guard, checkpoint manager.

These enforce bounded autonomy (spec 4.6 / 7.3 / 14.4): every loop has a cap, a
budget, and an escalation path. The CheckpointManager creates and resolves the
human-in-the-loop checkpoints (spec 7.2 / 25).
"""

from __future__ import annotations

from modelforge.common.config import Settings, get_settings
from modelforge.common.ids import new_id
from modelforge.schemas.control import Checkpoint, HumanFeedback
from modelforge.schemas.enums import (
    CheckpointAction,
    CheckpointId,
    CheckpointStatus,
)
from modelforge.schemas.state import ModelingState


class BudgetManager:
    """Tracks and enforces token/cost/runtime budgets (spec 7.3)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def record_model_calls(self, state: ModelingState, calls: list) -> None:
        for call in calls:
            state.budget_state.add_tokens(
                call.input_tokens, call.output_tokens, call.estimated_cost
            )

    def record_runtime(self, state: ModelingState, seconds: float) -> None:
        state.budget_state.sandbox_runtime_seconds += seconds


class LoopGuard:
    """Enforces per-loop retry caps + a total-loop cap (spec 14.4).

    Returns True if the named loop may proceed, False if its cap is exhausted
    (the caller then escalates). Counters live on the blackboard's budget_state.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def can_debug(self, state: ModelingState) -> bool:
        return state.budget_state.code_debug_count < self.settings.max_debug_retries

    def can_revise_model(self, state: ModelingState) -> bool:
        return state.budget_state.model_revision_count < self.settings.max_model_revisions

    def can_revise_report(self, state: ModelingState) -> bool:
        return state.budget_state.report_revision_count < self.settings.max_report_revisions

    def can_continue(self, state: ModelingState) -> bool:
        return state.budget_state.total_loop_count < self.settings.max_total_loops

    def tick(self, state: ModelingState, loop: str) -> None:
        bs = state.budget_state
        bs.total_loop_count += 1
        if loop == "debug":
            bs.code_debug_count += 1
        elif loop == "model":
            bs.model_revision_count += 1
        elif loop == "report":
            bs.report_revision_count += 1
        elif loop == "citation":
            bs.citation_retry_count += 1


class CheckpointManager:
    """Creates pending checkpoints and applies human resolutions (spec 7.2)."""

    def create(
        self, state: ModelingState, kind: CheckpointId, context: dict
    ) -> Checkpoint:
        version = None  # the run repo assigns versions; recorded on resolve
        checkpoint = Checkpoint(
            checkpoint_id=f"{kind.value}_{new_id('cp')}",
            kind=kind,
            run_id=state.run_id,
            status=CheckpointStatus.PENDING,
            context=context,
            previous_state_version=version,
        )
        state.pending_checkpoint = checkpoint
        return checkpoint

    def resolve(
        self,
        state: ModelingState,
        feedback: HumanFeedback,
    ) -> Checkpoint:
        """Apply a human decision to the pending checkpoint."""
        checkpoint = state.pending_checkpoint
        if checkpoint is None or checkpoint.checkpoint_id != feedback.checkpoint_id:
            raise ValueError("no matching pending checkpoint")
        checkpoint.status = (
            CheckpointStatus.CANCELLED
            if feedback.action is CheckpointAction.CANCEL_RUN
            else CheckpointStatus.RESOLVED
        )
        checkpoint.action = feedback.action
        checkpoint.actor_id = feedback.user_id
        checkpoint.comments = feedback.comments
        checkpoint.edited_fields = feedback.edits
        state.human_feedback.append(feedback)
        state.pending_checkpoint = None
        return checkpoint
