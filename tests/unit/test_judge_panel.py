from __future__ import annotations

from pathlib import Path

from modelforge.common.errors import FailureType
from modelforge.graph.deps import WorkflowDeps
from modelforge.graph.workflow import Workflow
from modelforge.providers.llm import MockProvider
from modelforge.schemas.control import CompetitionProfile
from modelforge.schemas.enums import (
    ClaimStatus,
    ClaimType,
    ProblemFamily,
    RunStatus,
    StrategyGoal,
)
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.experiment import (
    ExperimentRecord,
    ExperimentStatus,
    ExperimentType,
)
from modelforge.schemas.problem import ProblemCard, SourceReference, SubProblem
from modelforge.schemas.report import ReportOutline, ReportSection
from modelforge.schemas.route import ModelingRoute
from modelforge.schemas.state import ModelingState, Run
from modelforge.schemas.strategy import StrategyCandidate
from modelforge.services.compliance import ComplianceEngine
from modelforge.services.evaluation.judge_panel import JudgePanel
from modelforge.services.evidence import EvidenceRegistry
from modelforge.storage.database import Database


def _verified_claim(cid: str, subproblem_id: str) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=cid,
        run_id="run_x",
        subproblem_id=subproblem_id,
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement=f"Subproblem {subproblem_id} achieved RMSE = 0.1.",
        verification_status=ClaimStatus.VERIFIED,
        experiment_id="experiment_1",
        metric_name="rmse",
        metric_value=0.1,
        source_artifact_ids=["artifact_metrics_1"],
        metric_refs=["rmse"],
        table_refs=["artifact_table_1"],
        figure_refs=["artifact_figure_1"],
    )


def _valid_latex() -> str:
    return r"\documentclass{article}\begin{document}ok\end{document}"


def test_evidence_claim_records_subproblem_and_source_references() -> None:
    reg = EvidenceRegistry()
    exp = ExperimentRecord(
        experiment_id="experiment_1",
        run_id="run_x",
        strategy_id="strategy_1",
        experiment_type=ExperimentType.FORMAL,
        status=ExperimentStatus.SUCCEEDED,
        metrics={"rmse": 0.15},
        figure_artifact_ids=["artifact_fig_1"],
        table_artifact_ids=["artifact_table_1"],
    )

    claim = reg.register_quantitative(
        "run_x",
        "P1 RMSE is 0.15",
        experiment=exp,
        metric_name="rmse",
        artifact_ids=["artifact_metrics_1"],
        subproblem_id="P1",
        metric_refs=["rmse"],
        table_refs=["artifact_table_1"],
        figure_refs=["artifact_fig_1"],
        source_map=[SourceReference(source_file="problem.txt", line_reference="P1")],
    )

    assert claim.subproblem_id == "P1"
    assert claim.source_artifact_ids == ["artifact_metrics_1"]
    assert claim.artifact_ids == ["artifact_metrics_1"]
    assert claim.metric_refs == ["rmse"]
    assert claim.table_refs == ["artifact_table_1"]
    assert claim.figure_refs == ["artifact_fig_1"]
    assert claim.source_map[0].source_file == "problem.txt"


def test_report_builder_drops_unverified_and_rejected_claims() -> None:
    from modelforge.services.report.builder import ReportBuilder

    ok = _verified_claim("claim_ok", "P1")
    pending = ok.model_copy(
        update={"claim_id": "claim_pending", "verification_status": ClaimStatus.PENDING}
    )
    rejected = ok.model_copy(
        update={"claim_id": "claim_rejected", "verification_status": ClaimStatus.REJECTED}
    )
    outline = ReportOutline(
        sections=[
            ReportSection(
                section_id="results",
                title="Results",
                required_claim_ids=["claim_ok", "claim_pending", "claim_rejected"],
            )
        ]
    )
    text = (
        "Verified [claim:claim_ok]. Pending [claim:claim_pending]. "
        "Rejected [claim:claim_rejected]."
    )

    markdown, claim_map = ReportBuilder().build_markdown(
        "T", outline, {"results": text}, [ok, pending, rejected], []
    )

    assert "[E1]" in markdown
    assert "claim_pending" not in markdown
    assert "claim_rejected" not in markdown
    assert [entry.claim_id for entry in claim_map] == ["claim_ok"]


def test_judge_panel_fails_when_any_subproblem_lacks_verified_claim() -> None:
    state = ModelingState(
        run_id="run_x",
        problem_card=ProblemCard(
            title="Forecasting",
            subproblems=[
                SubProblem(sub_id="P1", statement="Fit the model."),
                SubProblem(sub_id="P2", statement="Validate sensitivity."),
            ],
        ),
        evidence_claims=[_verified_claim("claim_p1", "P1")],
        section_texts={
            "model_P1": "Sub-problem P1 reports RMSE [claim:claim_p1].",
            "model_P2": "Sub-problem P2 is described without evidence.",
            "sensitivity": "Sensitivity analysis is included.",
        },
        report_outline=ReportOutline(
            sections=[
                ReportSection(section_id="model_P1", title="P1"),
                ReportSection(section_id="model_P2", title="P2"),
                ReportSection(section_id="sensitivity", title="Sensitivity"),
            ]
        ),
    )

    report = JudgePanel().evaluate(
        state,
        markdown="\n".join(state.section_texts.values()),
        latex_source=_valid_latex(),
    )

    assert not report.passed
    assert report.per_judge_scores["coverage"] < 8.0
    assert "rerun_experiment" in report.routing_hints
    assert any(issue.critical and "P2" in issue.message for issue in report.issues)


def test_judge_panel_marks_irrigation_qubo_as_critical() -> None:
    subproblem = SubProblem(
        sub_id="P3",
        statement=(
            "Optimize irrigation scheduling with soil moisture, weather, ET, "
            "and water balance."
        ),
        required_outputs=["irrigation schedule", "ET estimate"],
    )
    state = ModelingState(
        run_id="run_x",
        problem_card=ProblemCard(
            title="Agricultural Irrigation Optimization",
            problem_summary="Use soil moisture and weather data for irrigation.",
            subproblems=[subproblem],
        ),
        selected_strategy=StrategyCandidate(
            strategy_id="strategy_qubo",
            strategy_name="QUBO quantum benchmark",
            design_goal=StrategyGoal.PERFORMANCE_FIRST,
            problem_family=ProblemFamily.OPTIMIZATION,
            mathematical_formulation="Map irrigation to a QUBO and solve by quantum benchmark.",
            pilot_template="integer_programming",
        ),
        subproblem_selected_routes={
            "P3": ModelingRoute(
                route_id="route_qubo",
                name="QUBO quantum benchmark route",
                approach="optimization",
                family=ProblemFamily.OPTIMIZATION,
                methods=["QUBO", "variational quantum"],
                summary="Map the irrigation problem to QUBO.",
            )
        },
        evidence_claims=[_verified_claim("claim_p3", "P3")],
        section_texts={
            "model_P3": (
                "The irrigation problem is formulated as QUBO and solved with a "
                "quantum benchmark [claim:claim_p3]."
            ),
            "sensitivity": "Sensitivity analysis is included.",
        },
    )

    report = JudgePanel().evaluate(
        state,
        markdown="\n".join(state.section_texts.values()),
        latex_source=_valid_latex(),
    )

    assert not report.passed
    assert report.per_judge_scores["method_validity"] < 7.0
    assert "reroute_method" in report.routing_hints
    assert any(issue.critical and issue.judge == "method_validity" for issue in report.issues)


def test_export_without_judge_pass_fails(db: Database, runs_root: Path) -> None:
    run_id = "run_quality_export"
    state = ModelingState(
        run_id=run_id,
        status=RunStatus.EXPORTING,
        competition_profile=CompetitionProfile(
            profile_id="practice_v1",
            competition_name="Practice",
            operating_mode="practice",
        ),
    )
    deps = WorkflowDeps.build(
        db,
        ComplianceEngine(state.competition_profile),
        provider=MockProvider(),
    )
    deps.run_repo.create_run(Run(run_id=run_id), state)

    final = Workflow(deps).export(state)

    assert final.status is RunStatus.FAILED
    assert final.failure_state is not None
    assert final.failure_state.failure_type is FailureType.QUALITY_GATE_FAILURE
    assert final.export_state.bundle_path is None
