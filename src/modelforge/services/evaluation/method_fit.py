"""Deterministic pre-codegen method-fit gate.

The gate catches obvious method/domain mismatches before the workflow spends
sandbox time. It is intentionally conservative: clear hard mismatches fail;
weaker completeness issues lower the score and leave an audit trail.
"""

from __future__ import annotations

from typing import Any

from modelforge.schemas.evaluation import MethodFitReport
from modelforge.schemas.problem import ProblemCard, RetrievedMethod, SubProblem
from modelforge.schemas.route import ModelingRoute
from modelforge.schemas.strategy import StrategyCandidate

_IRRIGATION_TERMS = (
    "irrigation",
    "soil",
    "moisture",
    "weather",
    "rainfall",
    "water balance",
    "evapotranspiration",
    " et ",
    "et0",
    "penman",
    "fao-56",
    "\u704c\u6e89",
    "\u571f\u58e4",
    "\u6c34\u5206",
    "\u84b8\u6563",
)
_IRRIGATION_GOOD_METHOD_TERMS = (
    "fao-56",
    "penman",
    "monteith",
    "soil water balance",
    "water balance",
    "evapotranspiration",
    "et0",
    "scheduling",
    "irrigation schedule",
    "rainfall",
    "soil moisture",
)
_IRRIGATION_BAD_DEFAULT_TERMS = (
    "qubo",
    "qboost",
    "quantum",
    "variational quantum",
    "adaboost",
    "state-of-the-art",
    "benchmark task",
    "benchmark dataset",
    "benchmark datasets",
)
_EVALUATION_TERMS = ("topsis", "entropy", "criteria", "rank", "score", "evaluation")
_NETWORK_TERMS = ("network", "graph", "flow", "centrality", "min-cost", "minimum cost")
_GENERIC_HYPE_TERMS = (
    "state-of-the-art",
    "novel method",
    "architectural innovations",
    "benchmark",
)


class MethodFitGate:
    """Score whether a candidate method can validly solve one subproblem."""

    def evaluate(
        self,
        problem_card: ProblemCard,
        subproblem: SubProblem,
        candidate: ModelingRoute | StrategyCandidate | dict[str, Any],
        *,
        available_input_files: list[str] | None = None,
        method_library_hits: list[RetrievedMethod] | None = None,
    ) -> MethodFitReport:
        candidate_text = _candidate_text(candidate, method_library_hits or [])
        task_text = _task_text(problem_card, subproblem)
        candidate_id = _candidate_id(candidate)
        issues: list[str] = []
        revisions: list[str] = []
        score = 10.0
        critical = False

        if _is_irrigation_context(task_text):
            bad = _hits(candidate_text, _IRRIGATION_BAD_DEFAULT_TERMS)
            explicitly_requested = _hits(task_text, _IRRIGATION_BAD_DEFAULT_TERMS)
            if bad and not explicitly_requested:
                critical = True
                score -= 5.5
                issues.append(
                    "irrigation/soil/weather/ET context is mismatched with "
                    f"default method terms: {', '.join(bad)}"
                )
                revisions.append(
                    "reroute to FAO-56 Penman-Monteith, soil water balance, "
                    "or irrigation scheduling optimization"
                )
            if not _hits(candidate_text, _IRRIGATION_GOOD_METHOD_TERMS):
                score -= 1.5
                issues.append("candidate does not map to irrigation water-balance terms")
                revisions.append("name the ET, soil-water-balance, or scheduling variables")

        missing_outputs = _missing_required_outputs(subproblem, candidate_text)
        if missing_outputs:
            score -= min(2.0, 0.75 * len(missing_outputs))
            issues.append(
                "candidate does not clearly produce required outputs: "
                + ", ".join(missing_outputs)
            )
            revisions.append("bind route outputs to the subproblem required_outputs")

        if not _has_data_mapping(candidate_text, available_input_files or []):
            score -= 1.0
            issues.append("candidate does not cite available data or justify a no-data model")
            revisions.append("reference input files/data fields or mark the model as theoretical")

        if _generic_hype_without_mapping(candidate_text, task_text):
            critical = True
            score -= 3.0
            issues.append("candidate uses high-level method claims without domain mapping")
            revisions.append(
                "replace generic benchmark prose with variables, equations, and data links"
            )

        if _is_evaluation_context(task_text) and _hits(candidate_text, _EVALUATION_TERMS):
            score += 0.5
        if _is_network_context(task_text) and _hits(candidate_text, _NETWORK_TERMS):
            score += 0.5

        score = max(0.0, min(10.0, round(score, 2)))
        passed = not critical and score >= 6.0
        return MethodFitReport(
            subproblem_id=subproblem.sub_id,
            candidate_id=candidate_id,
            passed=passed,
            score=score,
            issues=issues,
            required_revisions=list(dict.fromkeys(revisions)),
            routing_hint=_routing_hint(passed, score, critical, issues),
        )


def _task_text(problem_card: ProblemCard, subproblem: SubProblem) -> str:
    parts = [
        problem_card.title,
        problem_card.problem_summary,
        problem_card.objective_summary,
        " ".join(problem_card.objectives),
        " ".join(problem_card.constraints),
        " ".join(problem_card.global_constraints),
        " ".join(problem_card.variables),
        " ".join(problem_card.decision_variables),
        subproblem.statement,
        subproblem.objective,
        " ".join(subproblem.required_outputs),
        " ".join(subproblem.constraints),
        " ".join(subproblem.expected_equations),
    ]
    return " ".join(p for p in parts if p).lower()


def _candidate_text(
    candidate: ModelingRoute | StrategyCandidate | dict[str, Any],
    method_library_hits: list[RetrievedMethod],
) -> str:
    parts: list[str] = []
    if isinstance(candidate, ModelingRoute):
        parts.extend(
            [
                candidate.route_id,
                candidate.name,
                candidate.approach,
                candidate.family.value,
                candidate.model_family,
                candidate.summary,
                candidate.why_fit,
                " ".join(candidate.methods),
                " ".join(candidate.data_needed),
                " ".join(candidate.outputs),
                " ".join(candidate.method_ids),
                " ".join(candidate.domain_model_ids),
                " ".join(candidate.assumptions),
                " ".join(candidate.risks),
            ]
        )
    elif isinstance(candidate, StrategyCandidate):
        parts.extend(
            [
                candidate.strategy_id,
                candidate.strategy_name,
                candidate.problem_family.value,
                candidate.pilot_template,
                candidate.mathematical_formulation,
                " ".join(candidate.subproblem_mapping),
                " ".join(candidate.assumptions),
                " ".join(candidate.variable_definitions),
                " ".join(candidate.data_requirements),
                " ".join(candidate.preprocessing_plan),
                " ".join(candidate.experiment_plan),
                " ".join(candidate.expected_artifacts),
                " ".join(candidate.known_limitations),
            ]
        )
        for entry in candidate.method_stack:
            parts.extend([entry.method_id, entry.role, entry.rationale])
    else:
        parts.append(_flatten_dict(candidate))

    method_ids = set(_method_ids(candidate))
    for method in method_library_hits:
        if method.method_id in method_ids:
            parts.extend(
                [
                    method.method_id,
                    method.name,
                    method.summary,
                    " ".join(method.use_cases),
                    " ".join(method.required_data),
                    " ".join(method.assumptions),
                ]
            )
    return " ".join(p for p in parts if p).lower()


def _flatten_dict(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_dict(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_dict(v) for v in value)
    return str(value)


def _candidate_id(candidate: ModelingRoute | StrategyCandidate | dict[str, Any]) -> str:
    if isinstance(candidate, ModelingRoute):
        return candidate.route_id
    if isinstance(candidate, StrategyCandidate):
        return candidate.strategy_id
    return str(candidate.get("route_id") or candidate.get("strategy_id") or "candidate")


def _method_ids(candidate: ModelingRoute | StrategyCandidate | dict[str, Any]) -> list[str]:
    if isinstance(candidate, ModelingRoute):
        return [*candidate.method_ids, *candidate.methods]
    if isinstance(candidate, StrategyCandidate):
        return [entry.method_id for entry in candidate.method_stack]
    raw = candidate.get("method_ids") or candidate.get("methods") or []
    return [str(x) for x in raw]


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term.strip() for term in terms if term in text]


def _is_irrigation_context(text: str) -> bool:
    return bool(_hits(text, _IRRIGATION_TERMS))


def _is_evaluation_context(text: str) -> bool:
    return bool(_hits(text, _EVALUATION_TERMS))


def _is_network_context(text: str) -> bool:
    return bool(_hits(text, _NETWORK_TERMS))


def _missing_required_outputs(subproblem: SubProblem, candidate_text: str) -> list[str]:
    missing = []
    for output in subproblem.required_outputs:
        words = [w for w in output.lower().replace("/", " ").split() if len(w) >= 3]
        if words and not any(w in candidate_text for w in words):
            missing.append(output)
    return missing


def _has_data_mapping(candidate_text: str, available_input_files: list[str]) -> bool:
    no_data_markers = ("no data", "theoretical", "analytical", "closed form")
    if _hits(candidate_text, no_data_markers):
        return True
    if any(Pathish(name).stem in candidate_text for name in available_input_files):
        return True
    data_markers = ("data", "weather", "soil", "rainfall", "criteria", "edge", "network")
    return bool(_hits(candidate_text, data_markers))


def _generic_hype_without_mapping(candidate_text: str, task_text: str) -> bool:
    if not _hits(candidate_text, _GENERIC_HYPE_TERMS):
        return False
    if _is_irrigation_context(task_text):
        return not _hits(candidate_text, _IRRIGATION_GOOD_METHOD_TERMS)
    if _is_evaluation_context(task_text):
        return not _hits(candidate_text, _EVALUATION_TERMS)
    if _is_network_context(task_text):
        return not _hits(candidate_text, _NETWORK_TERMS)
    domain_words = {w for w in task_text.split() if len(w) >= 6}
    return not any(w in candidate_text for w in domain_words)


def _routing_hint(passed: bool, score: float, critical: bool, issues: list[str]) -> str:
    if passed:
        return "proceed"
    if critical:
        return "reroute_method"
    if score < 4.0:
        return "request_human_review"
    if any("data" in issue for issue in issues):
        return "reparse_problem"
    return "reroute_method"


class Pathish(str):
    @property
    def stem(self) -> str:
        name = self.replace("\\", "/").rsplit("/", 1)[-1]
        return name.rsplit(".", 1)[0].lower()
