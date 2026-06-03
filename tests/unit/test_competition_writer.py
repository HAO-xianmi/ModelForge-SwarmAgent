"""Slice 3a: CompetitionWriterAgent (mock path stays clean + evidence-gated).

The real provider weaves KB equations into prose (validated separately with the
real judge). Here we assert the mock path is clean, leak-free, and evidence-gated,
and that the agent accepts the KB domain_model context without breaking.
"""

from __future__ import annotations

from modelforge.agents.base import AgentContext
from modelforge.agents.competition_writer import CompetitionWriterAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.enums import ClaimStatus, ClaimType
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.report import ReportSection
from modelforge.services.method_library.domain_models import get_domain_model_library


def _writer() -> CompetitionWriterAgent:
    return CompetitionWriterAgent(AgentContext(run_id="r", provider=MockProvider()))


def _claim(cid: str, verified: bool) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=cid, run_id="r", claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement=f"metric {cid} is good",
        verification_status=ClaimStatus.VERIFIED if verified else ClaimStatus.REJECTED,
    )


def test_model_section_accepts_domain_model_and_stays_clean():
    dm = get_domain_model_library().get("penman_monteith_et0").model_dump()
    sec = ReportSection(section_id="model_P2", title="Sub-problem P2 Model",
                        required_claim_ids=["claim_ok"])
    ci = {"claim_ok": _claim("claim_ok", True)}
    res = _writer().write_section(sec, ci, domain_model=dm, route_name="mechanistic")
    assert res.ok and res.output is not None
    assert res.output.text.strip()
    # The writer cites verified claims via the [claim:id] marker (the builder
    # later renders these to clean [E1] markers; raw-id stripping is tested there).
    assert "[claim:claim_ok]" in res.output.text


def test_writer_is_evidence_gated():
    sec = ReportSection(section_id="model_P1", title="M",
                        required_claim_ids=["claim_ok", "claim_bad"])
    ci = {"claim_ok": _claim("claim_ok", True), "claim_bad": _claim("claim_bad", False)}
    res = _writer().write_section(sec, ci)
    # the rejected claim's id must not be cited
    assert "claim_bad" not in res.output.text


def test_writer_handles_missing_domain_model():
    sec = ReportSection(section_id="model_P9", title="M")
    res = _writer().write_section(sec, {}, domain_model=None)
    assert res.ok and res.output.text.strip()
