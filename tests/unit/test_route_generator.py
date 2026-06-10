"""Slice 2b: RouteGeneratorAgent produces >=5 substantially-different routes."""

from __future__ import annotations

from modelforge.agents.base import AgentContext
from modelforge.agents.route_generator import RouteGeneratorAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, SubProblem


def _ctx() -> AgentContext:
    return AgentContext(run_id="r", provider=MockProvider())


def _irrigation():
    card = ProblemCard(
        title="Agricultural Irrigation System Optimization",
        problem_summary="minimize irrigation cost, predict soil moisture, drought "
        "scheduling and reserve, multi-period adaptation, tank layout coverage",
        subproblems=[SubProblem(sub_id="P2", statement="Design minimum-cost irrigation layout")],
    )
    da = DomainAnalysis(
        domain_tags=["irrigation", "optimization"],
        likely_problem_families=[ProblemFamily.OPTIMIZATION, ProblemFamily.PREDICTION],
        key_terms=["soil", "moisture", "drought", "tank", "layout", "weather", "cost"],
        optimization_required=True,
    )
    return card, da


def test_generates_at_least_five_routes():
    card, da = _irrigation()
    res = RouteGeneratorAgent(_ctx()).generate(card, da, subproblem=card.subproblems[0])
    assert res.ok and res.output is not None
    assert len(res.output.routes) >= 5


def test_routes_are_substantially_different_approaches():
    card, da = _irrigation()
    res = RouteGeneratorAgent(_ctx()).generate(card, da)
    approaches = {r.approach for r in res.output.routes}
    assert len(approaches) >= 4, f"routes not diverse enough: {approaches}"


def test_each_route_records_tradeoffs_and_expected_metrics():
    card, da = _irrigation()
    res = RouteGeneratorAgent(_ctx()).generate(card, da)
    for r in res.output.routes:
        assert r.assumptions and r.advantages and r.limitations
        assert r.model_family
        assert r.methods
        assert r.data_needed
        assert r.outputs
        assert r.why_fit
        assert r.expected_metrics
        for k in ("problem_fit", "modeling_depth", "innovation"):
            assert k in r.expected_metrics
            assert 0.0 <= r.expected_metrics[k] <= 1.0


def test_routes_are_grounded_in_the_domain_kb():
    card, da = _irrigation()
    res = RouteGeneratorAgent(_ctx()).generate(card, da)
    grounded = [r for r in res.output.routes if r.domain_model_ids]
    assert grounded, "no route is grounded in a domain model"


def test_subproblem_id_is_tagged():
    card, da = _irrigation()
    res = RouteGeneratorAgent(_ctx()).generate(card, da, subproblem=card.subproblems[0])
    assert res.output.subproblem_id == "P2"
    assert all(r.subproblem_id == "P2" for r in res.output.routes)
