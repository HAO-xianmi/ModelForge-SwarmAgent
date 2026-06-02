"""Phase B: domain schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from modelforge.common.ids import (
    new_claim_id,
    new_run_id,
)
from modelforge.schemas.artifacts import ArtifactRecord, AuditEvent
from modelforge.schemas.control import CompetitionProfile
from modelforge.schemas.enums import (
    ArtifactType,
    CitationStatus,
    ClaimStatus,
    ClaimType,
    EventType,
    IssueSeverity,
    JudgeDecision,
    ProblemFamily,
    RunStatus,
    StrategyGoal,
)
from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.problem import ProblemCard
from modelforge.schemas.state import ModelingState, Run
from modelforge.schemas.strategy import (
    SkepticCandidateReview,
    SkepticIssue,
    SkepticReport,
    StrategyCandidate,
)


def test_modeling_state_minimal_roundtrip() -> None:
    rid = new_run_id()
    state = ModelingState(run_id=rid)
    assert state.status is RunStatus.CREATED
    dumped = state.model_dump(mode="json")
    restored = ModelingState.model_validate(dumped)
    assert restored.run_id == rid
    # StrEnum serializes to its string value
    assert dumped["status"] == "CREATED"


def test_run_serialization() -> None:
    run = Run(run_id=new_run_id(), mode="practice")
    j = run.model_dump(mode="json")
    assert j["status"] == "CREATED"
    assert isinstance(j["created_at"], str)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProblemCard(title="x", unknown_field=123)  # type: ignore[call-arg]


def test_artifact_record_defaults_immutable() -> None:
    art = ArtifactRecord(
        artifact_id="artifact_problem_card_abc",
        run_id="run_x",
        artifact_type=ArtifactType.PROBLEM_CARD,
        filename="problem_card.json",
        storage_uri="file://runs/run_x/problem/problem_card.json",
        content_hash="deadbeef",
    )
    assert art.immutable is True


def test_audit_event_type_validation() -> None:
    ev = AuditEvent(
        event_id="event_1",
        run_id="run_x",
        event_type=EventType.PROBLEM_PARSED,
    )
    assert ev.event_type is EventType.PROBLEM_PARSED
    with pytest.raises(ValidationError):
        AuditEvent(event_id="e", run_id="r", event_type="NOT_A_REAL_EVENT")  # type: ignore[arg-type]


def test_confidence_bounds() -> None:
    ProblemCard(title="ok", confidence=0.5)
    with pytest.raises(ValidationError):
        ProblemCard(title="bad", confidence=1.5)


def test_strategy_is_pilotable() -> None:
    s = StrategyCandidate(
        strategy_id="strategy_x",
        strategy_name="X",
        design_goal=StrategyGoal.PERFORMANCE_FIRST,
        problem_family=ProblemFamily.PREDICTION,
        pilot_template="linear_regression",
    )
    assert s.is_pilotable is True
    s2 = StrategyCandidate(
        strategy_id="strategy_y",
        strategy_name="Y",
        design_goal=StrategyGoal.PERFORMANCE_FIRST,
    )
    assert s2.is_pilotable is False


def test_skeptic_must_not_silently_approve() -> None:
    review = SkepticCandidateReview(
        strategy_id="strategy_x",
        issues=[
            SkepticIssue(
                severity=IssueSeverity.BLOCKER,
                category="data_leakage",
                description="target leaks into features",
            )
        ],
    )
    assert review.has_blocker is True
    report = SkepticReport(reviews=[review])
    assert report.for_strategy("strategy_x") is review


def test_evidence_claim_writer_access_rule() -> None:
    verified = EvidenceClaim(
        claim_id=new_claim_id(),
        run_id="run_x",
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement="RMSE=0.15",
        verification_status=ClaimStatus.VERIFIED,
    )
    pending = EvidenceClaim(
        claim_id=new_claim_id(),
        run_id="run_x",
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement="RMSE=0.10",
        verification_status=ClaimStatus.PENDING,
    )
    rejected = EvidenceClaim(
        claim_id=new_claim_id(),
        run_id="run_x",
        claim_type=ClaimType.MODEL_COMPARISON,
        statement="beats baseline",
        verification_status=ClaimStatus.REJECTED,
    )
    assert verified.usable_by_writer is True
    assert pending.usable_by_writer is False
    assert rejected.usable_by_writer is False


def test_citation_inclusion_rule_and_bibkey() -> None:
    cit = CitationRecord(
        citation_id="citation_1",
        title="A Modeling Method",
        authors=["Jane Q. Public"],
        year=2020,
        verification_status=CitationStatus.VERIFIED,
    )
    assert cit.includable_in_report is True
    assert cit.bibtex_key() == "public2020"
    unresolved = CitationRecord(
        citation_id="citation_2", title="Ghost", verification_status=CitationStatus.UNRESOLVED
    )
    assert unresolved.includable_in_report is False


def test_judge_report_decision_enum() -> None:
    from modelforge.schemas.strategy import JudgeReport

    jr = JudgeReport(decision=JudgeDecision.SELECT, selected_strategy_id="strategy_x")
    assert jr.decision is JudgeDecision.SELECT


def test_competition_profile_capability_defaults() -> None:
    practice = CompetitionProfile(
        profile_id="practice_v1",
        competition_name="Practice",
        operating_mode="practice",
    )
    # practice: default-allow
    assert practice.capability_enabled("code_generation") is True

    contest = CompetitionProfile(
        profile_id="contest_v1",
        competition_name="Contest",
        operating_mode="contest_compliant",
        allowed_capabilities={"code_generation": True},
        restricted_actions=["export_without_final_approval"],
    )
    assert contest.capability_enabled("code_generation") is True
    assert contest.capability_enabled("unlisted_capability") is False
    assert contest.action_restricted("export_without_final_approval") is True


def test_verified_claims_filter_on_state() -> None:
    state = ModelingState(run_id="run_x")
    state.evidence_claims = [
        EvidenceClaim(
            claim_id="c1",
            run_id="run_x",
            claim_type=ClaimType.DATA_DESCRIPTION,
            statement="ok",
            verification_status=ClaimStatus.VERIFIED,
        ),
        EvidenceClaim(
            claim_id="c2",
            run_id="run_x",
            claim_type=ClaimType.DATA_DESCRIPTION,
            statement="no",
            verification_status=ClaimStatus.REJECTED,
        ),
    ]
    verified = state.verified_claims()
    assert [c.claim_id for c in verified] == ["c1"]
