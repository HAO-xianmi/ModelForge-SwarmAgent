"""Phase D: evidence registry, citation registry, compliance engine."""

from __future__ import annotations

import pytest

from modelforge.common.errors import PolicyViolationError, QualityGateError
from modelforge.schemas.control import DisclosureInteraction
from modelforge.schemas.enums import (
    CitationStatus,
    ClaimStatus,
    ClaimType,
    ExperimentStatus,
    ExperimentType,
)
from modelforge.schemas.evidence import CitationRecord
from modelforge.schemas.experiment import ExperimentRecord
from modelforge.services.citations.registry import (
    CitationRegistry,
    CrossrefResolver,
    RemoteResolver,
    RemoteUnavailable,
)
from modelforge.services.compliance import ComplianceEngine, load_profile
from modelforge.services.evidence import EvidenceRegistry


def _experiment(metrics: dict[str, float], status=ExperimentStatus.SUCCEEDED) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id="experiment_1",
        run_id="run_x",
        strategy_id="s1",
        experiment_type=ExperimentType.FORMAL,
        status=status,
        metrics=metrics,
    )


# --------------------------------------------------------------------------- #
# Evidence registry
# --------------------------------------------------------------------------- #
def test_quantitative_claim_requires_real_metric() -> None:
    reg = EvidenceRegistry()
    exp = _experiment({"rmse": 0.15})
    claim = reg.register_quantitative(
        "run_x", "RMSE is 0.15", experiment=exp, metric_name="rmse"
    )
    assert claim.metric_value == 0.15
    assert claim.verification_status is ClaimStatus.PENDING


def test_quantitative_claim_rejects_unmeasured_metric() -> None:
    reg = EvidenceRegistry()
    exp = _experiment({"rmse": 0.15})
    with pytest.raises(QualityGateError):
        reg.register_quantitative(
            "run_x", "MAE is 0.1", experiment=exp, metric_name="mae"
        )


def test_verify_marks_verified_when_metric_present() -> None:
    reg = EvidenceRegistry()
    exp = _experiment({"rmse": 0.15})
    claim = reg.register_quantitative("run_x", "RMSE 0.15", experiment=exp, metric_name="rmse")
    verified = reg.verify(claim, [exp])
    assert verified.verification_status is ClaimStatus.VERIFIED
    assert verified.verified_by == "experiment_auditor"


def test_verify_rejects_when_experiment_failed() -> None:
    reg = EvidenceRegistry()
    exp_ok = _experiment({"rmse": 0.15})
    claim = reg.register_quantitative("run_x", "RMSE 0.15", experiment=exp_ok, metric_name="rmse")
    # The experiment that actually ran failed.
    exp_failed = _experiment({"rmse": 0.15}, status=ExperimentStatus.FAILED)
    verified = reg.verify(claim, [exp_failed])
    assert verified.verification_status is ClaimStatus.REJECTED


def test_writer_filter_excludes_rejected_and_pending() -> None:
    reg = EvidenceRegistry()
    exp = _experiment({"rmse": 0.15})
    pending = reg.register_quantitative("run_x", "p", experiment=exp, metric_name="rmse")
    verified = reg.verify(
        reg.register_quantitative("run_x", "v", experiment=exp, metric_name="rmse"), [exp]
    )
    rejected = reg.register_qualitative(
        "run_x", "r", ClaimType.LIMITATION, status=ClaimStatus.REJECTED
    )
    usable = reg.writer_usable([pending, verified, rejected])
    assert verified in usable
    assert pending not in usable
    assert rejected not in usable


# --------------------------------------------------------------------------- #
# Citation registry
# --------------------------------------------------------------------------- #
def test_citation_dedup_by_title_year() -> None:
    reg = CitationRegistry()
    cites = [
        CitationRecord(citation_id="c1", title="A Method", year=2020),
        CitationRecord(citation_id="c2", title="A Method", year=2020),
        CitationRecord(citation_id="c3", title="Other", year=2021),
    ]
    out = reg.deduplicate(cites)
    assert len(out) == 2


def test_citation_local_verification_levels() -> None:
    reg = CitationRegistry()
    full = CitationRecord(
        citation_id="c1", title="Complete Work", authors=["Smith"], year=2019
    )
    assert reg.verify(full).verification_status in (
        CitationStatus.VERIFIED,
        CitationStatus.PARTIALLY_VERIFIED,
    )
    title_only = CitationRecord(citation_id="c2", title="Lonely Title")
    assert reg.verify(title_only).verification_status is CitationStatus.NEEDS_HUMAN_REVIEW
    empty = CitationRecord(citation_id="c3", title="")
    assert reg.verify(empty).verification_status is CitationStatus.UNRESOLVED


def test_citation_remote_unavailable_falls_back() -> None:
    class DownResolver(RemoteResolver):
        provider_name = "down"

        def resolve_doi(self, doi: str):
            raise RemoteUnavailable("network down")

    reg = CitationRegistry(remote_resolver=DownResolver())
    cite = CitationRecord(
        citation_id="c1",
        title="Networked Work",
        authors=["Jones"],
        year=2018,
        doi="10.1000/xyz123",
    )
    result = reg.verify(cite)
    # Falls back to local structural verification, does not crash.
    assert result.verification_status in (
        CitationStatus.VERIFIED,
        CitationStatus.PARTIALLY_VERIFIED,
    )
    assert "unavailable" in result.verification_notes


def test_crossref_resolver_is_constructible() -> None:
    # Construction must not require network; resolution would.
    resolver = CrossrefResolver()
    assert resolver.provider_name == "crossref"


# --------------------------------------------------------------------------- #
# Compliance engine
# --------------------------------------------------------------------------- #
def test_all_five_profiles_load() -> None:
    for name in ("practice", "generic_contest", "cumcm", "mcm_icm", "apmcm"):
        profile = load_profile(name)
        assert profile.profile_id


def test_practice_profile_allows_auto_export() -> None:
    engine = ComplianceEngine(load_profile("practice"))
    assert engine.capability_enabled("code_generation") is True
    assert engine.required_checkpoints() == []
    assert engine.disclosure_required() is False


def test_contest_profile_requires_checkpoints_and_disclosure() -> None:
    engine = ComplianceEngine(load_profile("generic_contest"))
    assert engine.checkpoint_required("final_report") is True
    assert engine.disclosure_required() is True
    with pytest.raises(PolicyViolationError):
        engine.check_action("export_without_final_approval")


def test_disclosure_markdown_renders_interactions() -> None:
    engine = ComplianceEngine(load_profile("generic_contest"))
    record = engine.build_disclosure(
        "run_x",
        [
            DisclosureInteraction(
                provider="mock",
                model_identifier="mock-1",
                purpose="strategy generation",
                stage="generate_strategies",
                human_confirmation=True,
            )
        ],
    )
    md = engine.render_disclosure_markdown(record)
    assert "AI-Use Disclosure" in md
    assert "strategy generation" in md
