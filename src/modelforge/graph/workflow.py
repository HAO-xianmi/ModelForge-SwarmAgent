"""The workflow orchestrator (spec 13-14 / Appendix B).

Drives the blackboard through the node graph with conditional routing, loop
protection, checkpoint pauses, and state persistence + audit after every node.

A LangGraph ``StateGraph`` is built to document/validate the node topology
(``build_langgraph``); execution is driven explicitly by ``step``/``run`` so the
three human checkpoints can pause and resume the run across process boundaries
(spec 25), which a single ``graph.invoke`` cannot do cleanly.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from modelforge.common.errors import FailureType
from modelforge.common.logging import get_logger
from modelforge.graph import nodes
from modelforge.graph.control import BudgetManager, CheckpointManager, LoopGuard
from modelforge.graph.deps import WorkflowDeps
from modelforge.schemas.control import FailureState
from modelforge.schemas.enums import (
    ActorType,
    CheckpointId,
    EventType,
    RunStatus,
)
from modelforge.schemas.evaluation import JudgePanelReport
from modelforge.schemas.state import ModelingState

_log = get_logger("modelforge.workflow")

NodeFn = Callable[[ModelingState, WorkflowDeps], RunStatus]

# Status -> node function. analyze_domain is folded after parse via the inline
# RETRIEVING_METHODS return; we special-case it in the driver.
_NODES: dict[RunStatus, NodeFn] = {
    RunStatus.PARSING: nodes.parse_problem,
    RunStatus.RETRIEVING_METHODS: nodes.retrieve_methods,
    RunStatus.GENERATING_STRATEGIES: nodes.generate_strategies,
    RunStatus.CRITIQUING_STRATEGIES: nodes.skeptic_review,
    RunStatus.RUNNING_PILOTS: nodes.run_pilots,
    RunStatus.SELECTING_STRATEGY: nodes.select_strategy,
    RunStatus.PROFILING_DATA: nodes.profile_data,
    RunStatus.GENERATING_CODE: nodes.generate_code,
    RunStatus.RUNNING_SANDBOX: nodes.run_sandbox,
    RunStatus.RUNNING_BASELINES: nodes.run_baselines,
    RunStatus.RUNNING_ROBUSTNESS_TESTS: nodes.run_robustness,
    RunStatus.AUDITING_EXPERIMENTS: nodes.audit_experiments,
    RunStatus.REGISTERING_EVIDENCE: nodes.register_evidence,
    RunStatus.ARCHITECTING_REPORT: nodes.architect_report,
    RunStatus.WRITING_REPORT: nodes.write_report,
    RunStatus.VERIFYING_CITATIONS: nodes.verify_citations,
    RunStatus.RUNNING_JUDGE_PANEL: nodes.run_judge_panel,
    RunStatus.REPORT_REPAIR: nodes.repair_report,
}

# Statuses that pause for a human checkpoint.
_CHECKPOINT_STATUSES = {
    RunStatus.WAITING_FOR_CHECKPOINT_1: CheckpointId.PROBLEM_UNDERSTANDING,
    RunStatus.WAITING_FOR_CHECKPOINT_2: CheckpointId.STRATEGY_SELECTION,
    RunStatus.WAITING_FOR_CHECKPOINT_3: CheckpointId.FINAL_REPORT,
}

# Where to go after a checkpoint is approved.
_AFTER_CHECKPOINT = {
    CheckpointId.PROBLEM_UNDERSTANDING: RunStatus.RETRIEVING_METHODS,
    CheckpointId.STRATEGY_SELECTION: RunStatus.PROFILING_DATA,
    CheckpointId.FINAL_REPORT: RunStatus.EXPORTING,
}

_TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


class Workflow:
    def __init__(self, deps: WorkflowDeps) -> None:
        self.deps = deps
        self.loop_guard = LoopGuard(deps.settings)
        self.budget = BudgetManager(deps.settings)
        self.checkpoints = CheckpointManager()

    # ------------------------------------------------------------------ #
    # Driver
    # ------------------------------------------------------------------ #
    def run(self, state: ModelingState, *, max_steps: int = 200) -> ModelingState:
        """Run until a checkpoint pause or a terminal state."""
        steps = 0
        while state.status not in _TERMINAL and steps < max_steps:
            if state.status in _CHECKPOINT_STATUSES:
                self._ensure_checkpoint(state)
                # If the checkpoint is required, pause for human resolution;
                # otherwise it auto-passed and we continue from the new status.
                if state.pending_checkpoint is not None:
                    return state
                steps += 1
                continue
            if state.status is RunStatus.EXPORTING:
                return self.export(state)
            if not self.loop_guard.can_continue(state):
                self._escalate(state, "total loop budget exhausted")
                return state
            advanced = self.step(state)
            steps += 1
            if not advanced:
                break
        return state

    def step(self, state: ModelingState) -> bool:
        """Execute exactly one node and persist the result. Returns False at
        a terminal/checkpoint state (nothing to do)."""
        status = state.status
        if status in _TERMINAL or status in _CHECKPOINT_STATUSES:
            return False

        # Special compound step: PARSING also runs domain analysis inline so
        # both feed the same checkpoint-1 context.
        if status is RunStatus.PARSING:
            parse_status = nodes.parse_problem(state, self.deps)
            if parse_status is RunStatus.FAILED:
                state.status = RunStatus.FAILED
                self._persist(state, "parse_problem failed")
                self._finalize(state)
                return True
            next_status = nodes.analyze_domain(state, self.deps)
            state.status = (
                RunStatus.FAILED if next_status is RunStatus.FAILED else next_status
            )
            self._persist(state, "parse + analyze domain")
            if state.status in _TERMINAL:
                self._finalize(state)
            return True

        node = _NODES.get(status)
        if node is None:
            self._escalate(state, f"no node for status {status}")
            return True

        next_status = node(state, self.deps)
        next_status = self._route(state, status, next_status)
        state.status = next_status
        self._persist(state, f"node {status.value}")
        if next_status in _TERMINAL:
            self._finalize(state)
        return True

    # ------------------------------------------------------------------ #
    # Routing (conditional edges + loop protection, spec 14.3/14.4)
    # ------------------------------------------------------------------ #
    def _route(self, state: ModelingState, current: RunStatus, proposed: RunStatus) -> RunStatus:
        if current is RunStatus.RUNNING_JUDGE_PANEL:
            report = _latest_judge_report(state)
            if report is not None and not report.passed:
                return self._route_judge_failure(state, report)

        if proposed is RunStatus.FAILED:
            return RunStatus.FAILED

        # Sandbox failure -> debug loop (bounded).
        if current is RunStatus.RUNNING_SANDBOX and proposed is RunStatus.DEBUGGING_CODE:
            if self.loop_guard.can_debug(state):
                self.loop_guard.tick(state, "debug")
                return RunStatus.GENERATING_CODE  # regenerate/retry
            return self._escalate_status(state, "debug retries exhausted")

        # Audit failure routing (spec 14.3).
        if current is RunStatus.AUDITING_EXPERIMENTS and not (
            state.audit_summary and state.audit_summary.passed
        ):
            hints = {i.routing_hint for i in state.blocking_issues}
            if "revise_strategy" in hints and self.loop_guard.can_revise_model(state):
                self.loop_guard.tick(state, "model")
                return RunStatus.GENERATING_STRATEGIES
            if "revise_code" in hints and self.loop_guard.can_debug(state):
                self.loop_guard.tick(state, "debug")
                return RunStatus.GENERATING_CODE
            return self._escalate_status(state, "audit blocking issues unresolved")

        return proposed

    def _route_judge_failure(
        self, state: ModelingState, report: JudgePanelReport
    ) -> RunStatus:
        hint = report.routing_hints[0] if report.routing_hints else "request_human_review"

        if hint == "repair_latex":
            # Repairable LaTeX/structure defect -> deterministic REPORT_REPAIR
            # stage, bounded by the quality-revision budget so a recurring defect
            # can never loop forever (and never silently COMPLETE).
            bs = state.budget_state
            if bs.paper_revision_count >= bs.max_quality_revisions:
                return self._fail_quality_gate(
                    state,
                    "report repair budget exhausted (repair_latex kept recurring)",
                    failure_type=FailureType.BUDGET_FAILURE,
                )
            bs.paper_revision_count += 1
            bs.report_revision_count += 1
            bs.total_loop_count += 1
            state.failure_state = None
            return RunStatus.REPORT_REPAIR
        if hint == "request_human_review":
            return self._fail_quality_gate(
                state,
                "judge requested human review before export",
                failure_type=FailureType.QUALITY_GATE_FAILURE,
            )

        bs = state.budget_state
        if bs.judge_retry_count >= bs.max_quality_revisions:
            return self._fail_quality_gate(
                state,
                "quality revision budget exhausted",
                failure_type=FailureType.BUDGET_FAILURE,
            )

        bs.judge_retry_count += 1
        bs.total_loop_count += 1
        state.failure_state = None

        if hint == "reparse_problem":
            return RunStatus.PARSING
        if hint == "reroute_method":
            bs.method_reroute_count += 1
            bs.model_revision_count += 1
            return RunStatus.GENERATING_STRATEGIES
        if hint == "regenerate_code":
            bs.code_debug_count += 1
            return RunStatus.GENERATING_CODE
        if hint == "rerun_experiment":
            return RunStatus.RUNNING_SANDBOX
        if hint == "rewrite_section":
            bs.paper_revision_count += 1
            bs.report_revision_count += 1
            return RunStatus.WRITING_REPORT

        return self._fail_quality_gate(
            state,
            f"unknown judge routing hint: {hint}",
            failure_type=FailureType.QUALITY_GATE_FAILURE,
        )

    # ------------------------------------------------------------------ #
    # Checkpoints
    # ------------------------------------------------------------------ #
    def _ensure_checkpoint(self, state: ModelingState) -> None:
        if state.pending_checkpoint is not None:
            return
        kind = _CHECKPOINT_STATUSES[state.status]
        # Skip optional checkpoints when the profile does not require them
        # (practice mode) — auto-approve and advance.
        if not self.deps.compliance.checkpoint_required(kind.value):
            state.status = _AFTER_CHECKPOINT[kind]
            self._persist(state, f"auto-pass optional checkpoint {kind.value}")
            return
        context = self._checkpoint_context(state, kind)
        cp = self.checkpoints.create(state, kind, context)
        cp.previous_state_version = self.deps.run_repo.current_version(state.run_id)
        self.deps.run_repo.audit.record(
            state.run_id, EventType.CHECKPOINT_CREATED, payload={"checkpoint": kind.value}
        )
        self._persist(state, f"checkpoint {kind.value} created")

    def resume_from_checkpoint(self, state: ModelingState) -> ModelingState:
        """Continue after a checkpoint has been resolved on ``state``."""
        if state.pending_checkpoint is not None:
            return state  # still waiting
        # The resolution set status appropriately via resolve_checkpoint().
        return self.run(state)

    def _checkpoint_context(self, state: ModelingState, kind: CheckpointId) -> dict:
        if kind is CheckpointId.PROBLEM_UNDERSTANDING:
            return {
                "title": state.problem_card.title if state.problem_card else "",
                "subproblems": [s.statement for s in state.problem_card.subproblems]
                if state.problem_card
                else [],
                "families": [f.value for f in state.domain_analysis.likely_problem_families]
                if state.domain_analysis
                else [],
            }
        if kind is CheckpointId.STRATEGY_SELECTION:
            return {
                "selected_strategy_id": state.selected_strategy.strategy_id
                if state.selected_strategy
                else None,
                "candidates": [c.strategy_id for c in state.strategy_candidates],
                "pilot_success": {p.strategy_id: p.succeeded for p in state.pilot_experiments},
            }
        judge_report = _latest_judge_report(state)
        return {
            "report_markdown_id": state.report_artifacts.markdown_artifact_id
            if state.report_artifacts
            else None,
            "verified_claims": len(state.verified_claims()),
            "judge_panel_passed": judge_report.passed if judge_report else False,
            "disclosure_required": self.deps.compliance.disclosure_required(),
        }

    # ------------------------------------------------------------------ #
    # Persistence & finalization
    # ------------------------------------------------------------------ #

    def _persist(self, state: ModelingState, reason: str) -> None:
        self.deps.run_repo.save_state(
            state, actor="supervisor", actor_type=ActorType.SYSTEM, reason=reason
        )

    def _escalate(self, state: ModelingState, reason: str) -> None:
        from modelforge.common.errors import FailureType
        from modelforge.schemas.control import FailureState

        state.failure_state = FailureState(
            failure_type=FailureType.INTERNAL_ERROR,
            stage=state.status.value,
            detail=reason,
            escalated=True,
            recommended_actions=["human review required"],
        )
        state.status = RunStatus.FAILED
        self.deps.run_repo.audit.record(
            state.run_id, EventType.ESCALATION_CREATED, payload={"reason": reason}
        )
        self._persist(state, f"escalated: {reason}")
        self._finalize(state)

    def _escalate_status(self, state: ModelingState, reason: str) -> RunStatus:
        self._escalate(state, reason)
        return RunStatus.FAILED

    def _fail_quality_gate(
        self,
        state: ModelingState,
        reason: str,
        *,
        failure_type: FailureType,
    ) -> RunStatus:
        state.failure_state = FailureState(
            failure_type=failure_type,
            stage=state.status.value,
            detail=reason,
            recommended_actions=["inspect judge_panel_reports[-1].revision_plan"],
            escalated=failure_type is FailureType.BUDGET_FAILURE,
        )
        state.status = RunStatus.FAILED
        self.deps.run_repo.audit.record(
            state.run_id, EventType.ESCALATION_CREATED, payload={"reason": reason}
        )
        return RunStatus.FAILED

    def _finalize(self, state: ModelingState) -> None:
        if state.status is RunStatus.COMPLETED:
            self.deps.run_repo.audit.record(state.run_id, EventType.RUN_COMPLETED)
        elif state.status is RunStatus.FAILED:
            self.deps.run_repo.audit.record(state.run_id, EventType.RUN_FAILED)
        elif state.status is RunStatus.CANCELLED:
            self.deps.run_repo.audit.record(state.run_id, EventType.RUN_CANCELLED)

    # ------------------------------------------------------------------ #
    # Export stage (after checkpoint 3)
    # ------------------------------------------------------------------ #
    def export(self, state: ModelingState) -> ModelingState:
        """Build report files + reproducibility bundle (spec 13 export tail)."""
        from pathlib import Path

        from modelforge.schemas.enums import ArtifactType

        report = _latest_judge_report(state)
        if report is None or not report.passed:
            detail = (
                "export blocked: no passing JudgePanelReport"
                if report is None
                else f"export blocked: JudgePanel failed with score {report.final_score:.2f}"
            )
            self._fail_quality_gate(
                state,
                detail,
                failure_type=FailureType.QUALITY_GATE_FAILURE,
            )
            self._persist(state, detail)
            self._finalize(state)
            return state

        nodes.build_report_files(state, self.deps)
        disclosure_required = self.deps.compliance.disclosure_required()
        if disclosure_required:
            from modelforge.schemas.control import DisclosureInteraction

            interactions = [
                DisclosureInteraction(
                    provider=self.deps.provider.name,
                    model_identifier=self.deps.provider.model,
                    purpose="multi-agent modeling assistance",
                    stage="full workflow",
                    human_confirmation=bool(state.human_feedback),
                )
            ]
            record = self.deps.compliance.build_disclosure(state.run_id, interactions)
            md = self.deps.compliance.render_disclosure_markdown(record)
            self.deps.registry.register_text(
                state.run_id, ArtifactType.DISCLOSURE_RECORD, "ai_disclosure.md", md
            )

        export_path = (
            self.deps.settings.runs_path
            / state.run_id
            / "exports"
            / f"modelforge_run_{state.run_id}.zip"
        )
        manifest = self.deps.exporter.export_to_file(
            state, Path(export_path), disclosure_required=disclosure_required
        )
        bundle_art = self.deps.registry.register_existing_file(
            state.run_id, ArtifactType.REPRODUCIBILITY_BUNDLE, Path(export_path)
        )
        state.export_state.bundle_artifact_id = bundle_art.artifact_id
        state.export_state.bundle_path = str(export_path)
        state.export_state.disclosure_required = disclosure_required
        from modelforge.common.timeutil import utcnow

        state.export_state.exported_at = utcnow()
        state.status = RunStatus.COMPLETED
        self.deps.run_repo.audit.record(
            state.run_id,
            EventType.EXPORT_CREATED,
            payload={"manifest_experiments": len(manifest.experiments)},
        )
        self._persist(state, "export complete")
        self._finalize(state)
        return state


def build_langgraph(deps: WorkflowDeps) -> object:  # pragma: no cover - topology doc
    """Build a LangGraph StateGraph documenting the node topology (spec App. B).

    The explicit driver above is used for execution (checkpoint pause/resume);
    this graph validates the topology and supports visualization/export.
    """
    from langgraph.graph import END, StateGraph

    def _wrap(node: NodeFn) -> Callable[[ModelingState], ModelingState]:
        def _fn(state: ModelingState) -> ModelingState:
            node(state, deps)
            return state

        return _fn

    # Typed as Any: LangGraph's add_node overloads don't reconcile with a
    # pydantic-model node signature under mypy; this path is documentation only.
    graph: Any = StateGraph(ModelingState)
    for status, node in _NODES.items():
        graph.add_node(status.value, _wrap(node))
    graph.set_entry_point(RunStatus.PARSING.value)
    # Linear happy-path edges (conditional routing lives in the driver).
    import itertools

    order = list(_NODES.keys())
    for a, b in itertools.pairwise(order):
        graph.add_edge(a.value, b.value)
    graph.add_edge(order[-1].value, END)
    return graph.compile()


def _latest_judge_report(state: ModelingState) -> JudgePanelReport | None:
    return state.judge_panel_reports[-1] if state.judge_panel_reports else None
