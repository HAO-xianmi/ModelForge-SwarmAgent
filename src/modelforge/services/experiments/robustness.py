"""Robustness / sensitivity runner (spec 21.2).

Re-runs the strategy's experiment under perturbations and summarizes stability.
The default test is repeated-seed variation, which every template supports
(deterministic per seed, so varying the seed measures sensitivity to the random
split / initialization). Metric spread (std) across seeds is the stability
summary. Real execution only; an explicit waiver is produced when no robustness
test is meaningful.
"""

from __future__ import annotations

import statistics

from modelforge.schemas.enums import ExperimentType, ProblemFamily
from modelforge.schemas.experiment import ExperimentStatus, RobustnessResult
from modelforge.schemas.strategy import StrategyCandidate
from modelforge.services.codegen import CodeGenerator
from modelforge.services.experiments.runner import ExperimentRunner

# The metric whose stability we summarize, per family.
_STABILITY_METRIC = {
    ProblemFamily.PREDICTION: "rmse",
    ProblemFamily.CLASSIFICATION: "accuracy",
    ProblemFamily.CLUSTERING: "silhouette",
    ProblemFamily.OPTIMIZATION: "objective_value",
    ProblemFamily.EVALUATION: "top_score",
    ProblemFamily.GRAPH: "n_nodes",
}

_DEFAULT_SEEDS = (7, 17, 23, 42, 101)


class RobustnessRunner:
    def __init__(self, runner: ExperimentRunner, generator: CodeGenerator | None = None) -> None:
        self.runner = runner
        self.generator = generator or CodeGenerator()

    def run(
        self,
        run_id: str,
        strategy: StrategyCandidate,
        input_files: dict[str, bytes] | None = None,
        seeds: tuple[int, ...] = _DEFAULT_SEEDS,
    ) -> RobustnessResult:
        metric_name = _STABILITY_METRIC.get(strategy.problem_family)
        if metric_name is None or not strategy.is_pilotable:
            return RobustnessResult(
                test_name="repeated_seeds",
                strategy_id=strategy.strategy_id,
                status=ExperimentStatus.SKIPPED,
                is_waiver=True,
                waiver_reason=(
                    "no meaningful repeated-seed robustness metric for family "
                    f"'{strategy.problem_family.value}'"
                ),
            )

        model_kind = strategy.method_stack[0].method_id if strategy.method_stack else ""
        variants: list[dict] = []
        values: list[float] = []
        for seed in seeds:
            code = self.generator.generate(
                f"{strategy.strategy_id}_robust",
                strategy.pilot_template,
                strategy.problem_family,
                model_kind=model_kind,
                seed=seed,
            )
            record = self.runner.run(
                run_id,
                code,
                experiment_type=ExperimentType.ROBUSTNESS,
                input_files=input_files,
                seed=seed,
            )
            if record.status is ExperimentStatus.SUCCEEDED and metric_name in record.metrics:
                value = record.metrics[metric_name]
                values.append(value)
                variants.append({"seed": seed, "metric": metric_name, "value": value})

        if not values:
            return RobustnessResult(
                test_name="repeated_seeds",
                strategy_id=strategy.strategy_id,
                status=ExperimentStatus.FAILED,
                variants=variants,
            )

        summary = {
            f"{metric_name}_mean": statistics.fmean(values),
            f"{metric_name}_std": statistics.pstdev(values) if len(values) > 1 else 0.0,
            f"{metric_name}_min": min(values),
            f"{metric_name}_max": max(values),
            "n_runs": float(len(values)),
        }
        return RobustnessResult(
            test_name="repeated_seeds",
            strategy_id=strategy.strategy_id,
            variants=variants,
            summary=summary,
            status=ExperimentStatus.SUCCEEDED,
        )
