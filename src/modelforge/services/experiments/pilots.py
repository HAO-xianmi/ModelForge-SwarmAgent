"""Pilot experiments (spec 18).

Runs a fast, low-cost experiment for each pilotable strategy to establish
feasibility before the (expensive) formal pipeline and final strategy selection.
Pilots use a reduced timeout. Metrics come only from real execution.
"""

from __future__ import annotations

from modelforge.common.ids import new_pilot_id
from modelforge.common.logging import get_logger
from modelforge.schemas.enums import ExperimentStatus, ExperimentType
from modelforge.schemas.strategy import PilotExperiment, StrategyCandidate
from modelforge.services.codegen import CodeGenerator
from modelforge.services.experiments.runner import ExperimentRunner

_log = get_logger("modelforge.pilots")

_PILOT_TIMEOUT = 60  # seconds; pilots must be quick (spec 18.2)


class PilotService:
    def __init__(self, runner: ExperimentRunner, generator: CodeGenerator | None = None) -> None:
        self.runner = runner
        self.generator = generator or CodeGenerator()

    def run_pilot(
        self,
        run_id: str,
        strategy: StrategyCandidate,
        input_files: dict[str, bytes] | None = None,
    ) -> PilotExperiment:
        pilot_id = new_pilot_id(strategy.strategy_id)
        if not strategy.is_pilotable:
            return PilotExperiment(
                pilot_id=pilot_id,
                strategy_id=strategy.strategy_id,
                status=ExperimentStatus.SKIPPED,
                failure_reason="strategy has no runnable pilot template",
                recommendation="revise",
            )

        model_kind = _model_kind_for(strategy)
        code = self.generator.generate(
            strategy.strategy_id,
            strategy.pilot_template,
            strategy.problem_family,
            model_kind=model_kind,
        )
        record = self.runner.run(
            run_id,
            code,
            experiment_type=ExperimentType.PILOT,
            input_files=input_files,
            timeout_seconds=_PILOT_TIMEOUT,
            train_test_split=strategy.problem_family.value in ("prediction", "classification"),
        )

        succeeded = record.status is ExperimentStatus.SUCCEEDED
        return PilotExperiment(
            pilot_id=pilot_id,
            strategy_id=strategy.strategy_id,
            status=record.status,
            runtime_seconds=record.runtime_seconds,
            sample_size=int(record.metrics.get("n_test", record.metrics.get("n_samples", 0))),
            metrics=record.metrics,
            warnings=_warnings(record.metrics),
            artifact_ids=record.figure_artifact_ids + record.table_artifact_ids,
            experiment_id=record.experiment_id,
            failure_reason=record.failure_reason,
            recommendation="pass" if succeeded else "revise",
        )

    def run_all(
        self,
        run_id: str,
        strategies: list[StrategyCandidate],
        input_files: dict[str, bytes] | None = None,
    ) -> list[PilotExperiment]:
        return [self.run_pilot(run_id, s, input_files) for s in strategies]


def _model_kind_for(strategy: StrategyCandidate) -> str:
    """Derive a concrete model kind from the strategy's primary method."""
    if strategy.method_stack:
        return strategy.method_stack[0].method_id
    return ""


def _warnings(metrics: dict[str, float]) -> list[str]:
    out: list[str] = []
    if metrics.get("synthetic_data") == 1.0:
        out.append("pilot ran on synthetic data (no dataset provided)")
    return out
