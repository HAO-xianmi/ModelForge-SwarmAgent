"""Phase E: agent tests with the deterministic MockProvider (no API key).

These verify typed I/O, schema validity, repair-once on bad output, and that the
mock never invents experiment metrics (it produces plans/critiques/text only).
"""

from __future__ import annotations

import pytest

from modelforge.agents import (
    CodeAuthorAgent,
    DomainAnalystAgent,
    MethodRetrieverAgent,
    PaperArchitectAgent,
    PaperWriterAgent,
    ProblemParserAgent,
    SkepticAgent,
    StrategyJudgeAgent,
    StrategyProposerAgent,
)
from modelforge.agents.base import AgentContext
from modelforge.providers.llm import MockProvider
from modelforge.providers.llm.base import LLMResponse
from modelforge.schemas.enums import (
    ClaimStatus,
    ClaimType,
    ExperimentStatus,
    JudgeDecision,
    ProblemFamily,
    StrategyGoal,
)
from modelforge.schemas.evidence import EvidenceClaim
from modelforge.schemas.problem import (
    DomainAnalysis,
    FileManifest,
    InputManifest,
    ProblemCard,
)
from modelforge.schemas.report import ReportSection
from modelforge.schemas.strategy import (
    MethodStackEntry,
    PilotExperiment,
    StrategyCandidate,
)


@pytest.fixture()
def ctx() -> AgentContext:
    return AgentContext(run_id="run_test", provider=MockProvider())


def _manifest(text: str) -> InputManifest:
    return InputManifest(
        run_id="run_test",
        problem_text=text,
        files=[
            FileManifest(
                file_id="f1",
                original_name="problem.txt",
                normalized_name="problem.txt",
                content_hash="h",
                mime_type="text/plain",
                size_bytes=len(text),
                role="problem",
            )
        ],
    )


# --------------------------------------------------------------------------- #
def test_problem_parser_produces_card(ctx) -> None:
    result = ProblemParserAgent(ctx).parse(_manifest("Forecast next month's sales."))
    assert result.ok
    assert isinstance(result.output, ProblemCard)
    assert result.output.title
    assert result.output.confidence > 0
    # A model call was recorded with token accounting.
    assert ctx.model_calls and ctx.model_calls[0].input_tokens > 0


def test_domain_analyst_detects_family(ctx) -> None:
    card = ProblemCard(title="Sales forecasting", problem_summary="predict future sales demand")
    result = DomainAnalystAgent(ctx).analyze(card)
    assert result.ok
    assert ProblemFamily.PREDICTION in result.output.likely_problem_families


def test_domain_analyst_detects_optimization(ctx) -> None:
    card = ProblemCard(
        title="Resource allocation",
        problem_summary="maximize profit by allocating limited resources (knapsack)",
    )
    result = DomainAnalystAgent(ctx).analyze(card)
    assert ProblemFamily.OPTIMIZATION in result.output.likely_problem_families


def test_method_retriever_returns_registered_methods() -> None:
    agent = MethodRetrieverAgent()
    card = ProblemCard(title="Forecasting", objectives=["forecast"])
    domain = DomainAnalysis(likely_problem_families=[ProblemFamily.PREDICTION])
    methods = agent.retrieve(card, domain)
    assert methods
    assert all(m.suitability_score >= 0 for m in methods)


def test_three_proposers_are_independent_and_pilotable(ctx) -> None:
    card = ProblemCard(title="Forecasting", objectives=["forecast"])
    domain = DomainAnalysis(likely_problem_families=[ProblemFamily.PREDICTION])
    methods = MethodRetrieverAgent().retrieve(card, domain)
    candidates = []
    for goal in (
        StrategyGoal.INTERPRETABILITY_FIRST,
        StrategyGoal.PERFORMANCE_FIRST,
        StrategyGoal.INNOVATION_FIRST,
    ):
        res = StrategyProposerAgent(ctx, goal).propose(card, domain, methods)
        assert res.ok, res.failure
        candidates.append(res.output)
    # Each has a runnable pilot.
    assert all(c.is_pilotable for c in candidates)
    # Different goals -> different recommended methods (independence).
    methods_chosen = {c.method_stack[0].method_id for c in candidates if c.method_stack}
    assert len(methods_chosen) >= 2


def test_skeptic_does_not_blandly_approve_all(ctx) -> None:
    candidates = [
        StrategyCandidate(
            strategy_id=f"strategy_{i}",
            strategy_name=f"S{i}",
            design_goal=StrategyGoal.PERFORMANCE_FIRST,
            problem_family=ProblemFamily.PREDICTION,
            pilot_template="prediction",
            method_stack=[MethodStackEntry(method_id="random_forest")],
        )
        for i in range(2)
    ]
    result = SkepticAgent(ctx).review(candidates)
    assert result.ok
    recommendations = {r.recommendation for r in result.output.reviews}
    # Not all "pass" — at least one needs revision.
    assert "revise" in recommendations


def test_judge_selects_strategy_with_pilot_evidence(ctx) -> None:
    candidates = [
        StrategyCandidate(
            strategy_id="strategy_a",
            strategy_name="A",
            design_goal=StrategyGoal.PERFORMANCE_FIRST,
            problem_family=ProblemFamily.PREDICTION,
            pilot_template="prediction",
        )
    ]
    pilots = [
        PilotExperiment(
            pilot_id="pilot_a",
            strategy_id="strategy_a",
            status=ExperimentStatus.SUCCEEDED,
            metrics={"rmse": 0.12},
        )
    ]
    result = StrategyJudgeAgent(ctx).judge(candidates, None, pilots)
    assert result.ok
    assert result.output.decision is JudgeDecision.SELECT
    assert result.output.selected_strategy_id == "strategy_a"
    assert "pilot_a" in result.output.referenced_pilot_ids


def test_code_author_returns_real_runnable_artifact(ctx) -> None:
    strategy = StrategyCandidate(
        strategy_id="strategy_a",
        strategy_name="A",
        design_goal=StrategyGoal.PERFORMANCE_FIRST,
        problem_family=ProblemFamily.PREDICTION,
        pilot_template="prediction",
        method_stack=[MethodStackEntry(method_id="random_forest")],
    )
    result = CodeAuthorAgent(ctx).author(strategy)
    assert result.ok
    code = result.output
    assert code.file("main.py") is not None
    assert "random_forest" in code.file("main.py").content
    assert "scikit-learn" in code.dependencies


def test_paper_architect_only_references_existing_claims(ctx) -> None:
    claims = [
        EvidenceClaim(
            claim_id="claim_1",
            run_id="run_test",
            claim_type=ClaimType.QUANTITATIVE_RESULT,
            statement="RMSE is 0.12",
            verification_status=ClaimStatus.VERIFIED,
        )
    ]
    result = PaperArchitectAgent(ctx).architect(
        "Report", claims, figure_ids=["fig_1"], table_ids=[], citations=[]
    )
    assert result.ok
    for section in result.output.sections:
        # No section references a claim id that doesn't exist.
        assert all(cid == "claim_1" for cid in section.required_claim_ids)
        assert all(fid == "fig_1" for fid in section.required_figure_ids)


def test_paper_writer_only_uses_usable_claims(ctx) -> None:
    verified = EvidenceClaim(
        claim_id="claim_1",
        run_id="run_test",
        claim_type=ClaimType.QUANTITATIVE_RESULT,
        statement="RMSE is 0.12",
        verification_status=ClaimStatus.VERIFIED,
    )
    rejected = EvidenceClaim(
        claim_id="claim_2",
        run_id="run_test",
        claim_type=ClaimType.MODEL_COMPARISON,
        statement="beats everything",
        verification_status=ClaimStatus.REJECTED,
    )
    section = ReportSection(
        section_id="results",
        title="Results",
        required_claim_ids=["claim_1", "claim_2"],
    )
    index = {c.claim_id: c for c in (verified, rejected)}
    result = PaperWriterAgent(ctx).write_section(section, index)
    assert result.ok
    text = result.output.text
    assert "claim_1" in text
    assert "claim_2" not in text  # rejected claim excluded


def test_agent_repair_once_on_bad_output() -> None:
    """A provider that first returns garbage, then valid JSON, succeeds via repair."""

    class FlakyProvider:
        name = "flaky"
        model = "flaky-1"

        def __init__(self) -> None:
            self.calls = 0

        def complete(self, messages, *, temperature=0.2, max_tokens=2048, response_schema=None):
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(text="not json at all", model=self.model, provider=self.name)
            valid = (
                '{"domain_tags": ["x"], "likely_problem_families": ["prediction"]}'
            )
            return LLMResponse(text=valid, model=self.model, provider=self.name)

    provider = FlakyProvider()
    ctx = AgentContext(run_id="run_test", provider=provider)
    result = DomainAnalystAgent(ctx).analyze(ProblemCard(title="x"))
    assert provider.calls == 2  # one repair attempt
    assert result.ok


def test_agent_safe_failure_after_retry_exhaustion() -> None:
    class BadProvider:
        name = "bad"
        model = "bad-1"

        def complete(self, messages, *, temperature=0.2, max_tokens=2048, response_schema=None):
            return LLMResponse(text="never valid", model=self.model, provider=self.name)

    ctx = AgentContext(run_id="run_test", provider=BadProvider())
    result = DomainAnalystAgent(ctx).analyze(ProblemCard(title="x"))
    assert not result.ok
    assert result.failure is not None and "schema validation failed" in result.failure
