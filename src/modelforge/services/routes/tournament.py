"""Deterministic route tournament.

Scores each route on explicit weighted criteria, runs a full round-robin of
pairwise comparisons, selects the winner, and records a complete audit trail for
the decision. Deterministic (no LLM): identical input -> identical result, so the
selection is reproducible and auditable.
"""

from __future__ import annotations

from modelforge.schemas.route import (
    ModelingRoute,
    PairwiseComparison,
    RouteScore,
    RouteSet,
    RouteTournamentResult,
)

# Explicit, documented route-selection criteria (the list sums to 1.0). These are
# the modeling-quality axes a competition judge weighs when picking an approach.
CRITERION_WEIGHTS: dict[str, float] = {
    "problem_fit": 0.25,
    "modeling_depth": 0.20,
    "innovation": 0.15,
    "feasibility": 0.15,
    "robustness": 0.15,
    "interpretability": 0.10,
}


def score_route(route: ModelingRoute) -> RouteScore:
    em = route.expected_metrics
    vals = {k: max(0.0, min(1.0, float(em.get(k, 0.0)))) for k in CRITERION_WEIGHTS}
    total = sum(CRITERION_WEIGHTS[k] * vals[k] for k in CRITERION_WEIGHTS)
    return RouteScore(route_id=route.route_id, expected_total=round(total, 4), **vals)


class RouteTournament:
    def run(self, route_set: RouteSet) -> RouteTournamentResult:
        routes = route_set.routes
        scores = [score_route(r) for r in routes]
        by_id = {s.route_id: s for s in scores}
        audit = [
            f"scored {len(routes)} routes on weighted criteria "
            f"{ {k: CRITERION_WEIGHTS[k] for k in CRITERION_WEIGHTS} }"
        ]

        comparisons: list[PairwiseComparison] = []
        wins: dict[str, int] = {s.route_id: 0 for s in scores}
        ids = [r.route_id for r in routes]
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                sa, sb = by_id[a].expected_total, by_id[b].expected_total
                # Deterministic tie-break: higher score, then lexicographic id.
                winner = a if (sa, b) >= (sb, a) else b
                wins[winner] += 1
                comparisons.append(PairwiseComparison(
                    route_a=a, route_b=b, winner=winner, criterion="expected_total",
                    rationale=f"{winner} wins: expected_total "
                    f"{max(sa, sb):.3f} vs {min(sa, sb):.3f}",
                ))
                audit.append(f"compare {a} ({sa:.3f}) vs {b} ({sb:.3f}) -> {winner}")

        ranked = sorted(
            scores, key=lambda s: (wins[s.route_id], s.expected_total, s.route_id),
            reverse=True,
        )
        selected = ranked[0].route_id if ranked else ""
        runner_up = ranked[1].route_id if len(ranked) > 1 else ""
        rationale = (
            f"Selected '{selected}' (wins={wins.get(selected, 0)}, "
            f"expected_total={by_id[selected].expected_total:.3f}); "
            f"runner-up '{runner_up}'."
            if selected else "No routes to select from."
        )
        audit.append(f"selected {selected}; runner-up {runner_up}")

        return RouteTournamentResult(
            subproblem_id=route_set.subproblem_id,
            routes_considered=ids,
            scores=scores,
            comparisons=comparisons,
            selected_route_id=selected,
            runner_up_id=runner_up,
            rationale=rationale,
            audit_trail=audit,
        )
