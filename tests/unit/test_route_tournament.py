"""Slice 2c: route tournament — scoring, pairwise comparison, audit trail."""

from __future__ import annotations

from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.route import ModelingRoute, RouteSet
from modelforge.services.routes import CRITERION_WEIGHTS, RouteTournament, score_route


def _route(rid: str, fit: float, depth: float, innov: float) -> ModelingRoute:
    return ModelingRoute(
        route_id=rid, name=rid, approach="mechanistic",
        family=ProblemFamily.OPTIMIZATION, summary="s",
        expected_metrics={
            "problem_fit": fit, "modeling_depth": depth, "innovation": innov,
            "feasibility": 0.7, "robustness": 0.7, "interpretability": 0.7,
        },
    )


def _set() -> RouteSet:
    return RouteSet(subproblem_id="P2", routes=[
        _route("route_a", 0.9, 0.9, 0.8),   # strongest
        _route("route_b", 0.6, 0.6, 0.5),
        _route("route_c", 0.8, 0.7, 0.6),
    ])


def test_criterion_weights_sum_to_one():
    assert abs(sum(CRITERION_WEIGHTS.values()) - 1.0) < 1e-9


def test_score_is_weighted_sum():
    s = score_route(_route("r", 1.0, 1.0, 1.0))
    # all-0.7 except fit/depth/innov=1.0 -> weighted sum
    expected = (CRITERION_WEIGHTS["problem_fit"] + CRITERION_WEIGHTS["modeling_depth"]
                + CRITERION_WEIGHTS["innovation"]
                + 0.7 * (CRITERION_WEIGHTS["feasibility"] + CRITERION_WEIGHTS["robustness"]
                         + CRITERION_WEIGHTS["interpretability"]))
    assert abs(s.expected_total - round(expected, 4)) < 1e-3


def test_full_round_robin_comparisons():
    res = RouteTournament().run(_set())
    assert len(res.comparisons) == 3  # C(3,2)
    assert len(res.scores) == 3


def test_selects_strongest_route_with_audit_trail():
    res = RouteTournament().run(_set())
    assert res.selected_route_id == "route_a"
    assert res.runner_up_id == "route_c"
    assert res.audit_trail
    assert any("selected route_a" in line for line in res.audit_trail)
    assert res.rationale and "route_a" in res.rationale


def test_tournament_is_deterministic():
    a = RouteTournament().run(_set())
    b = RouteTournament().run(_set())
    assert a.model_dump() == b.model_dump()
