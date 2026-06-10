"""REPORT_REPAIR closed loop: judge ``repair_latex`` hints route to a
deterministic report-repair stage (bounded by the quality-revision budget)
instead of failing outright, then return to the judge panel.
"""

from __future__ import annotations

from pathlib import Path

from modelforge.common.errors import FailureType
from modelforge.graph import nodes
from modelforge.graph.deps import WorkflowDeps
from modelforge.graph.workflow import Workflow
from modelforge.providers.llm import MockProvider
from modelforge.schemas.control import CompetitionProfile
from modelforge.schemas.enums import (
    ClaimStatus,
    ClaimType,
    RunStatus,
)
from modelforge.schemas.evaluation import JudgeIssue, JudgePanelReport
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.problem import ProblemCard, SubProblem
from modelforge.schemas.report import ReportOutline, ReportSection
from modelforge.schemas.state import ModelingState, Run
from modelforge.services.compliance import ComplianceEngine
from modelforge.storage.database import Database


def _deps(db: Database) -> WorkflowDeps:
    profile = CompetitionProfile(
        profile_id="practice_v1",
        competition_name="Practice",
        operating_mode="practice",
    )
    return WorkflowDeps.build(db, ComplianceEngine(profile), provider=MockProvider())


def _verified_claim(cid: str, subproblem_id: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=cid,
        run_id="run_repair",
        subproblem_id=subproblem_id,
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement=f"Subproblem {subproblem_id} achieved RMSE = 0.1.",
        verification_status=ClaimStatus.VERIFIED,
        experiment_id="experiment_1",
        metric_name="rmse",
        metric_value=0.1,
        source_artifact_ids=["artifact_metrics_1"],
        metric_refs=["rmse"],
    )


def _repair_latex_report() -> JudgePanelReport:
    """A failing report whose only complaint is a repairable LaTeX defect."""
    return JudgePanelReport(
        final_score=6.5,
        passed=False,
        per_judge_scores={"latex_build": 0.0, "coverage": 9.0},
        issues=[
            JudgeIssue(
                judge="latex_build",
                severity="critical",
                message="LaTeX environment begin/end counts do not match",
                routing_hint="repair_latex",
                critical=True,
            )
        ],
        revision_plan=["latex_build: broken structure -> repair_latex"],
        routing_hints=["repair_latex"],
    )


def _state_with_repair_report() -> ModelingState:
    state = ModelingState(
        run_id="run_repair",
        status=RunStatus.RUNNING_JUDGE_PANEL,
        problem_card=ProblemCard(
            title="Forecasting",
            subproblems=[SubProblem(sub_id="P1", statement="Fit the model.")],
        ),
        evidence_claims=[_verified_claim("claim_p1", "P1")],
        section_texts={"model_P1": "Sub-problem P1 reports RMSE [claim:claim_p1]."},
        report_outline=ReportOutline(
            sections=[ReportSection(section_id="model_P1", title="P1")]
        ),
    )
    state.judge_panel_reports.append(_repair_latex_report())
    return state


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #
def test_repair_latex_routes_to_report_repair_within_budget(db: Database) -> None:
    state = _state_with_repair_report()
    wf = Workflow(_deps(db))

    nxt = wf._route(state, RunStatus.RUNNING_JUDGE_PANEL, RunStatus.WAITING_FOR_CHECKPOINT_3)

    assert nxt is RunStatus.REPORT_REPAIR
    assert state.failure_state is None
    # The repair attempt is charged against the quality-revision budget.
    assert state.budget_state.paper_revision_count == 1


def test_repair_latex_budget_exhaustion_is_budget_failure(db: Database) -> None:
    state = _state_with_repair_report()
    state.budget_state.paper_revision_count = state.budget_state.max_quality_revisions
    wf = Workflow(_deps(db))

    nxt = wf._route(state, RunStatus.RUNNING_JUDGE_PANEL, RunStatus.WAITING_FOR_CHECKPOINT_3)

    assert nxt is RunStatus.FAILED
    assert state.failure_state is not None
    assert state.failure_state.failure_type is FailureType.BUDGET_FAILURE


# --------------------------------------------------------------------------- #
# Repair node behavior
# --------------------------------------------------------------------------- #
def test_repair_report_node_returns_to_judge_panel(db: Database) -> None:
    state = _state_with_repair_report()
    deps = _deps(db)

    nxt = nodes.repair_report(state, deps)

    assert nxt is RunStatus.RUNNING_JUDGE_PANEL
    assert state.failure_state is None


def test_repair_report_rebuilds_wellformed_latex(db: Database) -> None:
    state = _state_with_repair_report()
    # A claim-id leak and a stray section text that the judge flagged.
    state.section_texts["model_P1"] = (
        "Sub-problem P1 reports RMSE [claim:claim_p1] (claim_deadbeef1234 leaked)."
    )
    deps = _deps(db)

    nodes.repair_report(state, deps)

    assert state.report_artifacts is not None
    latex = deps.registry.read_bytes(
        state.report_artifacts.latex_artifact_id or ""
    ).decode("utf-8")
    assert "\\documentclass" in latex
    assert "\\begin{document}" in latex
    assert "\\end{document}" in latex
    assert latex.count("\\begin{") == latex.count("\\end{")
    assert "claim_deadbeef1234" not in latex


def test_repair_report_fails_on_empty_outline(db: Database) -> None:
    state = _state_with_repair_report()
    state.report_outline = ReportOutline(sections=[])
    deps = _deps(db)

    nxt = nodes.repair_report(state, deps)

    assert nxt is RunStatus.FAILED
    assert state.failure_state is not None
    # Unfixable content is a fast QUALITY_GATE dead-end, not a budget loop.
    assert state.failure_state.failure_type is FailureType.QUALITY_GATE_FAILURE
    assert "outline" in state.failure_state.detail.lower()


def test_repair_report_fails_on_empty_sections(db: Database) -> None:
    state = _state_with_repair_report()
    state.section_texts = {}
    deps = _deps(db)

    nxt = nodes.repair_report(state, deps)

    assert nxt is RunStatus.FAILED
    assert state.failure_state is not None
    assert state.failure_state.failure_type is FailureType.QUALITY_GATE_FAILURE
    assert "section" in state.failure_state.detail.lower()


# --------------------------------------------------------------------------- #
# End-to-end repair loop via the driver
# --------------------------------------------------------------------------- #
def _persisted_state(db: Database) -> ModelingState:
    state = _state_with_repair_report()
    state.competition_profile = CompetitionProfile(
        profile_id="practice_v1",
        competition_name="Practice",
        operating_mode="practice",
    )
    return state


def _panel_passable_state() -> ModelingState:
    """A report that passes every judge except a repairable LaTeX defect."""
    from modelforge.schemas.enums import ProblemFamily, StrategyGoal
    from modelforge.schemas.strategy import StrategyCandidate

    section = (
        "Under stated assumptions, sub-problem P1 fits a regression model and "
        "reports RMSE [claim:claim_p1]. A baseline comparison and a sensitivity "
        "(robustness) analysis confirm the result is stable."
    )
    state = ModelingState(
        run_id="run_repair",
        status=RunStatus.RUNNING_JUDGE_PANEL,
        competition_profile=CompetitionProfile(
            profile_id="practice_v1",
            competition_name="Practice",
            operating_mode="practice",
        ),
        problem_card=ProblemCard(
            title="Forecasting",
            subproblems=[SubProblem(sub_id="P1", statement="Fit the model.")],
        ),
        selected_strategy=StrategyCandidate(
            strategy_id="strategy_1",
            strategy_name="Gradient-boosted regression",
            design_goal=StrategyGoal.PERFORMANCE_FIRST,
            problem_family=ProblemFamily.PREDICTION,
            mathematical_formulation="Minimize squared error over boosted trees.",
            pilot_template="prediction",
        ),
        evidence_claims=[_verified_claim("claim_p1", "P1")],
        section_texts={"model_P1": section},
        report_outline=ReportOutline(
            sections=[ReportSection(section_id="model_P1", title="P1")]
        ),
    )
    state.judge_panel_reports.append(_repair_latex_report())
    return state


def test_repair_then_pass_allows_export(db: Database, runs_root: Path) -> None:
    """A run that fails on repairable LaTeX, repairs, then passes the judge
    panel must reach a passing report and be exportable (not COMPLETED-blocked)."""
    state = _panel_passable_state()
    deps = _deps(db)
    deps.run_repo.create_run(Run(run_id=state.run_id), state)
    wf = Workflow(deps)

    # Repair pass: route -> REPORT_REPAIR -> repair node rebuilds clean latex.
    nxt = wf._route(state, RunStatus.RUNNING_JUDGE_PANEL, RunStatus.WAITING_FOR_CHECKPOINT_3)
    assert nxt is RunStatus.REPORT_REPAIR
    state.status = nxt
    advanced = wf.step(state)
    assert advanced
    assert state.status is RunStatus.RUNNING_JUDGE_PANEL

    # Re-run the judge panel deterministically; with clean latex + a covered
    # subproblem the panel passes and we head to checkpoint 3.
    final = wf.step(state)
    assert final
    assert state.status is RunStatus.WAITING_FOR_CHECKPOINT_3
    assert state.judge_panel_reports[-1].passed


def test_repair_budget_exhaustion_never_completes(db: Database, runs_root: Path) -> None:
    """When ``repair_latex`` keeps recurring, each attempt charges the
    quality-revision budget; once it is exhausted the run ends in BUDGET_FAILURE
    — never COMPLETED."""
    state = _persisted_state(db)
    deps = _deps(db)
    deps.run_repo.create_run(Run(run_id=state.run_id), state)
    wf = Workflow(deps)
    max_revisions = state.budget_state.max_quality_revisions

    # Simulate the judge re-emitting repair_latex on each return to the panel.
    last_status = RunStatus.REPORT_REPAIR
    for _ in range(max_revisions + 3):
        # Always replace the latest report with a fresh repair_latex failure.
        state.judge_panel_reports.append(_repair_latex_report())
        last_status = wf._route(
            state, RunStatus.RUNNING_JUDGE_PANEL, RunStatus.WAITING_FOR_CHECKPOINT_3
        )
        if last_status is RunStatus.FAILED:
            break
        assert last_status is RunStatus.REPORT_REPAIR

    assert last_status is RunStatus.FAILED
    assert state.failure_state is not None
    assert state.failure_state.failure_type is FailureType.BUDGET_FAILURE
    # The budget was actually consumed across repeated attempts.
    assert state.budget_state.paper_revision_count >= max_revisions
