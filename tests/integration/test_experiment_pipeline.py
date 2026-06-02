"""Integration: the full experiment pipeline runs REAL experiments and the
auditor gates on real evidence. Pilots, formal run, baseline, robustness, audit.
"""

from __future__ import annotations

import pytest

from modelforge.common.ids import new_run_id
from modelforge.schemas.enums import ExperimentStatus, ExperimentType, ProblemFamily, StrategyGoal
from modelforge.schemas.strategy import MethodStackEntry, StrategyCandidate
from modelforge.services.codegen import CodeGenerator
from modelforge.services.experiments import (
    BaselineRunner,
    ExperimentAuditor,
    ExperimentRunner,
    PilotService,
    RobustnessRunner,
)

pytestmark = pytest.mark.integration


def _strategy(family=ProblemFamily.PREDICTION, method="random_forest") -> StrategyCandidate:
    template = {
        ProblemFamily.PREDICTION: "prediction",
        ProblemFamily.CLASSIFICATION: "classification",
        ProblemFamily.OPTIMIZATION: "optimization",
        ProblemFamily.GRAPH: "graph",
    }[family]
    return StrategyCandidate(
        strategy_id="strategy_perf_001",
        strategy_name="Test strategy",
        design_goal=StrategyGoal.PERFORMANCE_FIRST,
        problem_family=family,
        pilot_template=template,
        method_stack=[MethodStackEntry(method_id=method, role="core_model")],
    )


@pytest.fixture()
def exp_runner(registry):
    return ExperimentRunner(registry)


def test_pilot_runs_and_reports_metrics(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    pilot = PilotService(exp_runner).run_pilot(rid, _strategy())
    assert pilot.status is ExperimentStatus.SUCCEEDED
    assert "rmse" in pilot.metrics
    assert pilot.experiment_id
    assert "synthetic" in " ".join(pilot.warnings)  # no dataset provided


def test_pilot_skipped_when_not_pilotable(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    bad = StrategyCandidate(
        strategy_id="s_bad",
        strategy_name="No template",
        design_goal=StrategyGoal.INNOVATION_FIRST,
    )
    pilot = PilotService(exp_runner).run_pilot(rid, bad)
    assert pilot.status is ExperimentStatus.SKIPPED


def test_formal_run_registers_figures_tables_logs(exp_runner, registry, make_run_dir) -> None:
    from modelforge.schemas.enums import ArtifactType

    rid = new_run_id()
    make_run_dir(rid)
    code = CodeGenerator().generate(
        "strategy_perf_001", "prediction", ProblemFamily.PREDICTION, model_kind="random_forest"
    )
    record = exp_runner.run(
        rid, code, experiment_type=ExperimentType.FORMAL, train_test_split=True
    )
    assert record.status is ExperimentStatus.SUCCEEDED
    assert record.figure_artifact_ids  # prediction_vs_actual.png registered
    assert record.log_artifact_ids
    assert record.dependencies
    figures = registry.list_for_run(rid, ArtifactType.FIGURE)
    assert figures and all(f.experiment_id == record.experiment_id for f in figures)


def test_baseline_runs_for_prediction(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    baseline = BaselineRunner(exp_runner).run(rid, _strategy())
    assert baseline.status is ExperimentStatus.SUCCEEDED
    assert "rmse" in baseline.metrics
    assert baseline.is_waiver is False


def test_robustness_summarizes_seed_spread(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    result = RobustnessRunner(exp_runner).run(rid, _strategy(), seeds=(1, 2, 3))
    assert result.status is ExperimentStatus.SUCCEEDED
    assert "rmse_std" in result.summary
    assert result.summary["n_runs"] == 3.0


def test_auditor_passes_with_complete_evidence(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    strategy = _strategy()
    code = CodeGenerator().generate(
        strategy.strategy_id, "prediction", ProblemFamily.PREDICTION, model_kind="random_forest"
    )
    formal = exp_runner.run(
        rid, code, experiment_type=ExperimentType.FORMAL, train_test_split=True
    )
    baseline = BaselineRunner(exp_runner).run(rid, strategy)
    robustness = RobustnessRunner(exp_runner).run(rid, strategy, seeds=(1, 2))
    summary = ExperimentAuditor().audit(strategy, formal, [baseline], [robustness])
    assert summary.passed is True
    assert summary.checks["code_executed"] is True
    assert summary.checks["train_test_split"] is True


def test_auditor_blocks_missing_split(exp_runner, make_run_dir) -> None:
    rid = new_run_id()
    make_run_dir(rid)
    strategy = _strategy()
    code = CodeGenerator().generate(
        strategy.strategy_id, "prediction", ProblemFamily.PREDICTION
    )
    # Formal run WITHOUT marking train/test split for a predictive task.
    formal = exp_runner.run(
        rid, code, experiment_type=ExperimentType.FORMAL, train_test_split=False
    )
    summary = ExperimentAuditor().audit(strategy, formal, [], [])
    assert summary.passed is False
    routings = {i.routing_hint for i in summary.blocking_issues}
    assert "revise_strategy" in routings  # missing split
    assert any("baseline" in i.description for i in summary.blocking_issues)


def test_auditor_blocks_when_code_failed(exp_runner) -> None:
    # No formal experiment at all -> blocking.
    summary = ExperimentAuditor().audit(_strategy(), None, [], [])
    assert summary.passed is False
    assert summary.checks["code_executed"] is False
