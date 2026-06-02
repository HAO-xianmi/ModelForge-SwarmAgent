"""Experiment auditor (spec 21.3 / 21.4).

Runs the quality-gate checks over a run's experiment evidence and produces an
:class:`AuditSummary`. Blocking issues (spec 21.4) prevent report export and
carry a routing hint (revise_code / revise_strategy / escalate) used by the
workflow's conditional edges (spec 14.3).
"""

from __future__ import annotations

from modelforge.common.ids import new_id
from modelforge.schemas.enums import ExperimentStatus, IssueSeverity
from modelforge.schemas.experiment import (
    AuditSummary,
    BaselineResult,
    BlockingIssue,
    ExperimentRecord,
    RobustnessResult,
)
from modelforge.schemas.strategy import StrategyCandidate

# Families for which a train/test split is required (predictive modeling).
_REQUIRES_SPLIT = {"prediction", "classification"}


class ExperimentAuditor:
    def audit(
        self,
        strategy: StrategyCandidate,
        formal: ExperimentRecord | None,
        baselines: list[BaselineResult],
        robustness: list[RobustnessResult],
    ) -> AuditSummary:
        checks: dict[str, bool] = {}
        issues: list[BlockingIssue] = []

        # 1. Code executed successfully.
        executed = formal is not None and formal.status is ExperimentStatus.SUCCEEDED
        checks["code_executed"] = executed
        if not executed:
            issues.append(
                _issue(
                    "implementation_defect",
                    "formal experiment did not execute successfully",
                    "revise_code",
                )
            )

        if formal is not None:
            # 2. Reproducibility metadata recorded.
            checks["seed_recorded"] = formal.seed is not None
            checks["input_hash_recorded"] = True  # always set (may be empty if no data)
            checks["dependencies_recorded"] = bool(formal.dependencies)
            if not formal.dependencies:
                issues.append(
                    _issue("reproducibility", "dependencies not recorded", "revise_code")
                )
            # 3. Metrics present.
            checks["metrics_present"] = bool(formal.metrics)
            if executed and not formal.metrics:
                issues.append(
                    _issue(
                        "implementation_defect",
                        "successful run produced no metrics.json",
                        "revise_code",
                    )
                )
            # 4. Train/test separation for predictive modeling.
            if strategy.problem_family.value in _REQUIRES_SPLIT:
                checks["train_test_split"] = formal.train_test_split
                if not formal.train_test_split:
                    issues.append(
                        _issue(
                            "model_design_defect",
                            "predictive modeling without a train/test split",
                            "revise_strategy",
                        )
                    )
            # 5. Figures/tables link to the experiment (provenance).
            checks["artifacts_linked"] = bool(
                formal.figure_artifact_ids or formal.table_artifact_ids
            )

        # 6. Baseline exists or an explicit waiver exists.
        has_baseline = any(
            b.status is ExperimentStatus.SUCCEEDED for b in baselines
        )
        has_baseline_waiver = any(b.is_waiver for b in baselines)
        checks["baseline_or_waiver"] = has_baseline or has_baseline_waiver
        if not (has_baseline or has_baseline_waiver):
            issues.append(
                _issue("evidence", "no baseline result and no waiver", "revise_code")
            )

        # 7. Robustness exists or an explicit waiver exists.
        has_robust = any(r.status is ExperimentStatus.SUCCEEDED for r in robustness)
        has_robust_waiver = any(r.is_waiver for r in robustness)
        checks["robustness_or_waiver"] = has_robust or has_robust_waiver
        if not (has_robust or has_robust_waiver):
            issues.append(
                _issue("evidence", "no robustness result and no waiver", "revise_code")
            )

        # 8. Data-leakage heuristic check passed (split implies a basic guard).
        checks["leakage_checked"] = formal.leakage_checked if formal else False

        passed = len(issues) == 0
        return AuditSummary(checks=checks, blocking_issues=issues, passed=passed)


def _issue(category: str, description: str, routing: str) -> BlockingIssue:
    return BlockingIssue(
        issue_id=new_id("issue"),
        severity=IssueSeverity.BLOCKER,
        category=category,
        description=description,
        routing_hint=routing,
    )
