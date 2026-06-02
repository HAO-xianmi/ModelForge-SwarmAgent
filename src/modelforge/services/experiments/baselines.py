"""Baseline runner (spec 21.1).

For each strategy a meaningful baseline is run via a real experiment (e.g. a
mean predictor / linear regression for prediction, majority class / logistic
regression for classification, a greedy allocation for optimization). When no
meaningful baseline exists, an explicit waiver record is produced (never a
silent skip).
"""

from __future__ import annotations

from modelforge.schemas.enums import ExperimentType, ProblemFamily
from modelforge.schemas.experiment import BaselineResult, ExperimentStatus
from modelforge.schemas.strategy import StrategyCandidate
from modelforge.services.codegen import CodeGenerator
from modelforge.services.experiments.runner import ExperimentRunner

# Baseline method per family (a deliberately simple model).
_BASELINE = {
    ProblemFamily.PREDICTION: ("prediction", "linear_regression", "Linear regression baseline"),
    ProblemFamily.CLASSIFICATION: (
        "classification",
        "logistic_regression",
        "Logistic regression baseline",
    ),
    ProblemFamily.CLUSTERING: ("clustering", "kmeans", "K-means (k=3) baseline"),
    ProblemFamily.OPTIMIZATION: ("optimization", "", "Greedy/relaxed allocation baseline"),
    ProblemFamily.GRAPH: ("graph", "shortest_path", "Shortest-path baseline"),
    ProblemFamily.EVALUATION: ("evaluation", "entropy_weight", "Entropy-weight baseline"),
}


class BaselineRunner:
    def __init__(self, runner: ExperimentRunner, generator: CodeGenerator | None = None) -> None:
        self.runner = runner
        self.generator = generator or CodeGenerator()

    def run(
        self,
        run_id: str,
        strategy: StrategyCandidate,
        input_files: dict[str, bytes] | None = None,
    ) -> BaselineResult:
        spec = _BASELINE.get(strategy.problem_family)
        if spec is None:
            return BaselineResult(
                baseline_name="no_meaningful_baseline",
                strategy_id=strategy.strategy_id,
                status=ExperimentStatus.SKIPPED,
                is_waiver=True,
                waiver_reason=(
                    f"no standard baseline defined for family "
                    f"'{strategy.problem_family.value}'"
                ),
            )
        template, model_kind, name = spec
        # Avoid a baseline identical to the strategy's own primary method.
        if strategy.method_stack and strategy.method_stack[0].method_id == model_kind:
            model_kind = _alt_baseline(strategy.problem_family, model_kind)

        code = self.generator.generate(
            f"{strategy.strategy_id}_baseline",
            template,
            strategy.problem_family,
            model_kind=model_kind,
        )
        record = self.runner.run(
            run_id,
            code,
            experiment_type=ExperimentType.BASELINE,
            input_files=input_files,
            train_test_split=strategy.problem_family.value in ("prediction", "classification"),
        )
        return BaselineResult(
            baseline_name=name,
            strategy_id=strategy.strategy_id,
            experiment_id=record.experiment_id,
            metrics=record.metrics,
            status=record.status,
        )


def _alt_baseline(family: ProblemFamily, taken: str) -> str:
    if family is ProblemFamily.CLASSIFICATION:
        return "decision_tree" if taken != "decision_tree" else "logistic_regression"
    if family is ProblemFamily.PREDICTION:
        return "random_forest" if taken != "random_forest" else "linear_regression"
    return taken
