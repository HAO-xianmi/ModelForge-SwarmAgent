"""Deterministic hard final-quality gate.

The JudgePanel runs after report drafting and citation verification. It is not an
LLM advisory review: each sub-judge uses reproducible state/text checks, emits
structured routing hints, and blocks export unless the hard pass conditions are
met.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from modelforge.schemas.enums import ClaimStatus, ClaimType
from modelforge.schemas.evaluation import JudgeIssue, JudgePanelReport
from modelforge.schemas.state import ModelingState

_CLAIM_REF = re.compile(r"\[claim:([a-zA-Z0-9_]+)\]")
_RAW_CLAIM_ID = re.compile(r"\bclaim_[0-9a-fA-F]{4,}\b")

_IRRIGATION_TERMS = (
    "irrigation",
    "soil moisture",
    "water balance",
    "evapotranspiration",
    "rainfall",
    "weather",
    "et0",
    "penman",
    "\u704c\u6e89",
    "\u571f\u58e4",
    "\u84b8\u6563",
)
_IRRIGATION_BAD_TERMS = (
    "qubo",
    "qboost",
    "quantum",
    "variational quantum",
    "benchmark dataset",
    "benchmark task",
)
_IRRIGATION_GOOD_TERMS = (
    "fao-56",
    "penman",
    "monteith",
    "soil water balance",
    "water balance",
    "evapotranspiration",
    "irrigation schedule",
    "rainfall",
    "soil moisture",
)


@dataclass
class _JudgeResult:
    score: float
    issues: list[JudgeIssue] = field(default_factory=list)


class _SubJudge(Protocol):
    judge_id: str

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        ...


class ProblemCoverageJudge:
    judge_id = "coverage"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        if state.problem_card is None:
            return _JudgeResult(
                0.0,
                [
                    _issue(
                        self.judge_id,
                        "missing problem card; cannot verify report coverage",
                        "reparse_problem",
                        critical=True,
                    )
                ],
            )

        subproblems = state.problem_card.subproblems
        verified = [
            c for c in state.evidence_claims
            if c.verification_status is ClaimStatus.VERIFIED
        ]
        if not subproblems:
            if verified:
                return _JudgeResult(8.0)
            return _JudgeResult(
                0.0,
                [
                    _issue(
                        self.judge_id,
                        "no subproblems and no verified evidence claim",
                        "reparse_problem",
                        critical=True,
                    )
                ],
            )

        issues: list[JudgeIssue] = []
        covered = 0
        text = markdown.lower()
        for sp in subproblems:
            sub_claims = [c for c in verified if c.subproblem_id == sp.sub_id]
            has_section = sp.sub_id.lower() in text or f"model_{sp.sub_id}".lower() in text
            if sub_claims:
                covered += 1
            else:
                issues.append(
                    _issue(
                        self.judge_id,
                        f"subproblem {sp.sub_id} has no verified claim",
                        "rerun_experiment",
                        subproblem_id=sp.sub_id,
                        critical=True,
                    )
                )
            if not has_section:
                issues.append(
                    _issue(
                        self.judge_id,
                        f"subproblem {sp.sub_id} is not clearly represented in the draft",
                        "rewrite_section",
                        subproblem_id=sp.sub_id,
                    )
                )

        score = round(10.0 * covered / len(subproblems), 2)
        if issues and all(not i.critical for i in issues):
            score = min(score, 7.5)
        return _JudgeResult(score, issues)


class MethodValidityJudge:
    judge_id = "method_validity"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        issues: list[JudgeIssue] = []
        scores: list[float] = []
        for report in state.method_fit_reports:
            scores.append(report.score)
            if not report.passed:
                critical = _contains_irrigation_bad(" ".join(report.issues))
                issues.append(
                    _issue(
                        self.judge_id,
                        (
                            f"method-fit failed for {report.subproblem_id or 'global'}: "
                            + "; ".join(report.issues)
                        ),
                        report.routing_hint,
                        subproblem_id=report.subproblem_id,
                        critical=critical,
                    )
                )

        task_text = _problem_text(state)
        candidate_text = _candidate_text(state)
        report_text = markdown.lower()
        if _is_irrigation(task_text):
            bad = _hits(candidate_text + " " + report_text, _IRRIGATION_BAD_TERMS)
            good = _hits(candidate_text + " " + report_text, _IRRIGATION_GOOD_TERMS)
            if bad and not good:
                issues.append(
                    _issue(
                        self.judge_id,
                        (
                            "irrigation/soil/weather task is routed or written as "
                            f"{', '.join(bad)} without water-balance domain mapping"
                        ),
                        "reroute_method",
                        critical=True,
                    )
                )
                scores.append(2.0)

        if state.selected_strategy is None and not state.subproblem_selected_routes:
            issues.append(
                _issue(
                    self.judge_id,
                    "no selected strategy or selected subproblem routes",
                    "reroute_method",
                )
            )
            scores.append(5.0)

        score = min(scores) if scores else 8.0
        if any(i.critical for i in issues):
            score = min(score, 2.0)
        return _JudgeResult(round(score, 2), issues)


class EvidenceConsistencyJudge:
    judge_id = "evidence_consistency"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        verified = {
            c.claim_id: c
            for c in state.evidence_claims
            if c.verification_status is ClaimStatus.VERIFIED
        }
        issues: list[JudgeIssue] = []
        if not verified:
            issues.append(
                _issue(
                    self.judge_id,
                    "report has no verified evidence claims",
                    "rerun_experiment",
                    critical=True,
                )
            )

        for cid in _CLAIM_REF.findall(markdown):
            if cid not in verified:
                issues.append(
                    _issue(
                        self.judge_id,
                        f"draft references unverified or rejected claim {cid}",
                        "rewrite_section",
                        critical=True,
                    )
                )

        text_without_claim_refs = _CLAIM_REF.sub("", markdown)
        if _RAW_CLAIM_ID.search(text_without_claim_refs):
            issues.append(
                _issue(
                    self.judge_id,
                    "internal claim ids leaked into report text",
                    "rewrite_section",
                    critical=True,
                )
            )

        strict_metric_claims = {
            ClaimType.QUANTITATIVE_RESULT,
            ClaimType.MODEL_COMPARISON,
        }
        for claim in verified.values():
            if claim.claim_type in strict_metric_claims:
                missing = []
                if claim.experiment_id is None:
                    missing.append("experiment_id")
                if claim.metric_name is None or claim.metric_value is None:
                    missing.append("metric")
                if not (claim.source_artifact_ids or claim.artifact_ids):
                    missing.append("source_artifact_ids")
                if missing:
                    issues.append(
                        _issue(
                            self.judge_id,
                            f"verified claim {claim.claim_id} lacks {', '.join(missing)}",
                            "rerun_experiment",
                            subproblem_id=claim.subproblem_id,
                            critical=True,
                        )
                    )
            elif claim.claim_type is ClaimType.ROBUSTNESS_CONCLUSION:
                missing = []
                if not claim.metric_refs:
                    missing.append("metric_refs")
                if not (claim.source_artifact_ids or claim.artifact_ids):
                    missing.append("source_artifact_ids")
                if missing:
                    issues.append(
                        _issue(
                            self.judge_id,
                            f"verified robustness claim {claim.claim_id} lacks "
                            + ", ".join(missing),
                            "rerun_experiment",
                            subproblem_id=claim.subproblem_id,
                            critical=True,
                        )
                    )

        score = 10.0 - sum(3.0 if i.critical else 1.0 for i in issues)
        return _JudgeResult(round(max(0.0, score), 2), issues)


class WritingQualityJudge:
    judge_id = "writing_quality"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        issues: list[JudgeIssue] = []
        score = 10.0
        if state.report_outline is not None:
            missing = [
                s.section_id
                for s in state.report_outline.sections
                if not state.section_texts.get(s.section_id, "").strip()
            ]
            if missing:
                score -= min(4.0, len(missing))
                issues.append(
                    _issue(
                        self.judge_id,
                        "empty report sections: " + ", ".join(missing[:5]),
                        "rewrite_section",
                    )
                )

        lower = markdown.lower()
        checks = {
            "assumptions": ("assumption", "\u5047\u8bbe"),
            "sensitivity": ("sensitivity", "robustness", "\u7075\u654f"),
            "baseline": ("baseline", "vs baseline", "comparison", "\u5bf9\u6bd4"),
        }
        for name, terms in checks.items():
            if not any(term in lower for term in terms):
                score -= 0.8
                issues.append(
                    _issue(
                        self.judge_id,
                        f"draft lacks a clear {name} discussion",
                        "rewrite_section",
                    )
                )

        if _word_count(markdown) < 80:
            score -= 1.5
            issues.append(
                _issue(
                    self.judge_id,
                    "draft is too short for a final modeling report",
                    "rewrite_section",
                )
            )
        return _JudgeResult(round(max(0.0, score), 2), issues)


class LatexBuildJudge:
    judge_id = "latex_build"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        issues: list[JudgeIssue] = []
        required = ("\\documentclass", "\\begin{document}", "\\end{document}")
        if not latex_source.strip() or not all(token in latex_source for token in required):
            issues.append(
                _issue(
                    self.judge_id,
                    "LaTeX source is missing required document structure",
                    "repair_latex",
                    critical=True,
                )
            )
        if latex_source.count("\\begin{") != latex_source.count("\\end{"):
            issues.append(
                _issue(
                    self.judge_id,
                    "LaTeX environment begin/end counts do not match",
                    "repair_latex",
                    critical=True,
                )
            )
        if _RAW_CLAIM_ID.search(_CLAIM_REF.sub("", latex_source)):
            issues.append(
                _issue(
                    self.judge_id,
                    "LaTeX source leaks internal claim ids",
                    "repair_latex",
                    critical=True,
                )
            )
        score = 0.0 if issues else 10.0
        return _JudgeResult(score, issues)


class AdversarialJudge:
    judge_id = "adversarial"

    def evaluate(
        self,
        state: ModelingState,
        markdown: str,
        latex_source: str,
    ) -> _JudgeResult:
        issues: list[JudgeIssue] = []
        lower = markdown.lower()
        if _is_irrigation(_problem_text(state)) and _contains_irrigation_bad(lower):
            issues.append(
                _issue(
                    self.judge_id,
                    "adversarial check found irrigation QUBO/quantum/benchmark framing",
                    "reroute_method",
                    critical=True,
                )
            )
        if "state-of-the-art" in lower and not state.verified_claims():
            issues.append(
                _issue(
                    self.judge_id,
                    "unsupported state-of-the-art claim without verified evidence",
                    "rewrite_section",
                    critical=True,
                )
            )
        if "sensitivity" not in lower and "robustness" not in lower:
            issues.append(
                _issue(
                    self.judge_id,
                    "adversarial check found no sensitivity or robustness evidence",
                    "rewrite_section",
                )
            )
        if "baseline" not in lower and "comparison" not in lower:
            issues.append(
                _issue(
                    self.judge_id,
                    "adversarial check found no baseline/comparison discussion",
                    "rerun_experiment",
                )
            )
        score = 10.0 - sum(5.0 if i.critical else 1.0 for i in issues)
        return _JudgeResult(round(max(0.0, score), 2), issues)


class JudgePanel:
    """Run all deterministic final-panel judges and apply hard pass conditions."""

    def __init__(self, judges: list[_SubJudge] | None = None) -> None:
        self.judges = judges or [
            ProblemCoverageJudge(),
            MethodValidityJudge(),
            EvidenceConsistencyJudge(),
            WritingQualityJudge(),
            LatexBuildJudge(),
            AdversarialJudge(),
        ]

    def evaluate(
        self,
        state: ModelingState,
        *,
        markdown: str,
        latex_source: str,
    ) -> JudgePanelReport:
        threshold = _profile_threshold(state)
        per_scores: dict[str, float] = {}
        issues: list[JudgeIssue] = []
        for judge in self.judges:
            result = judge.evaluate(state, markdown, latex_source)
            per_scores[judge.judge_id] = result.score
            issues.extend(result.issues)

        final_score = (
            round(sum(per_scores.values()) / len(per_scores), 2)
            if per_scores
            else 0.0
        )
        routing_hints = _ordered_unique(
            issue.routing_hint for issue in issues if issue.routing_hint
        )
        revision_plan = [
            f"{issue.judge}: {issue.message} -> {issue.routing_hint}"
            for issue in issues
        ]
        critical = any(issue.critical or issue.severity == "critical" for issue in issues)
        passed = (
            final_score >= threshold
            and per_scores.get("coverage", 0.0) >= 8.0
            and per_scores.get("method_validity", 0.0) >= 7.0
            and per_scores.get("evidence_consistency", 0.0) >= 8.0
            and per_scores.get("latex_build", 0.0) >= 8.0
            and not critical
        )
        return JudgePanelReport(
            final_score=final_score,
            passed=passed,
            per_judge_scores=per_scores,
            issues=issues,
            revision_plan=revision_plan,
            routing_hints=routing_hints or ([] if passed else ["request_human_review"]),
            threshold=threshold,
        )


def _issue(
    judge: str,
    message: str,
    routing_hint: str,
    *,
    subproblem_id: str | None = None,
    critical: bool = False,
) -> JudgeIssue:
    return JudgeIssue(
        judge=judge,
        severity="critical" if critical else "major",
        message=message,
        routing_hint=routing_hint,
        subproblem_id=subproblem_id,
        critical=critical,
    )


def _profile_threshold(state: ModelingState) -> float:
    raw = getattr(state.competition_profile, "threshold", None)
    if isinstance(raw, (int, float)):
        return float(raw)
    return 7.0


def _ordered_unique(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in out:
            out.append(text)
    return out


def _problem_text(state: ModelingState) -> str:
    card = state.problem_card
    if card is None:
        return ""
    parts = [
        card.title,
        card.problem_summary,
        card.objective_summary,
        " ".join(card.objectives),
        " ".join(card.constraints),
        " ".join(card.variables),
        " ".join(card.forbidden_misreadings),
    ]
    for sp in card.subproblems:
        parts.extend(
            [
                sp.sub_id,
                sp.statement,
                sp.objective,
                " ".join(sp.required_outputs),
                " ".join(sp.constraints),
                " ".join(sp.expected_equations),
                sp.risk_of_misread,
            ]
        )
    return " ".join(p for p in parts if p).lower()


def _candidate_text(state: ModelingState) -> str:
    parts: list[str] = []
    if state.selected_strategy is not None:
        s = state.selected_strategy
        parts.extend(
            [
                s.strategy_id,
                s.strategy_name,
                s.problem_family.value,
                s.mathematical_formulation,
                " ".join(s.subproblem_mapping),
                " ".join(s.assumptions),
                " ".join(s.data_requirements),
                " ".join(s.experiment_plan),
                " ".join(s.expected_artifacts),
                " ".join(s.known_limitations),
            ]
        )
        for entry in s.method_stack:
            parts.extend([entry.method_id, entry.role, entry.rationale])
    for route in state.subproblem_selected_routes.values():
        parts.extend(
            [
                route.route_id,
                route.name,
                route.approach,
                route.family.value,
                route.model_family,
                route.summary,
                route.why_fit,
                " ".join(route.methods),
                " ".join(route.data_needed),
                " ".join(route.outputs),
                " ".join(route.method_ids),
                " ".join(route.domain_model_ids),
                " ".join(route.assumptions),
            ]
        )
    return " ".join(p for p in parts if p).lower()


def _is_irrigation(text: str) -> bool:
    return bool(_hits(text, _IRRIGATION_TERMS))


def _contains_irrigation_bad(text: str) -> bool:
    return bool(_hits(text.lower(), _IRRIGATION_BAD_TERMS))


def _hits(text: str, terms: tuple[str, ...]) -> list[str]:
    lower = text.lower()
    return [term for term in terms if term in lower]


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


__all__ = [
    "AdversarialJudge",
    "EvidenceConsistencyJudge",
    "JudgePanel",
    "LatexBuildJudge",
    "MethodValidityJudge",
    "ProblemCoverageJudge",
    "WritingQualityJudge",
]
