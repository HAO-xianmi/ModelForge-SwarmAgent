from __future__ import annotations

from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.problem import ProblemCard, SubProblem
from modelforge.schemas.route import ModelingRoute
from modelforge.services.evaluation import MethodFitGate


def _irrigation_card() -> tuple[ProblemCard, SubProblem]:
    subproblem = SubProblem(
        sub_id="P3",
        statement=(
            "Optimize irrigation scheduling using soil moisture, weather, ET, and "
            "water-balance constraints."
        ),
        objective="choose irrigation timing and volume",
        required_outputs=["ET estimate", "soil water balance", "irrigation schedule"],
        input_data_refs=["soil.csv", "weather.csv"],
        constraints=["soil moisture lower bound", "water availability", "cost budget"],
        expected_equations=["FAO-56 Penman-Monteith", "soil water balance"],
    )
    card = ProblemCard(
        title="Agricultural Irrigation System Optimization",
        problem_summary=(
            "Estimate crop water demand and optimize irrigation using soil and weather data."
        ),
        subproblems=[subproblem],
        variables=["soil_moisture", "rainfall", "ET0", "irrigation_amount"],
        constraints=["water balance", "cost budget"],
    )
    return card, subproblem


def test_irrigation_qubo_route_fails() -> None:
    card, subproblem = _irrigation_card()
    route = ModelingRoute(
        route_id="route_qubo",
        name="QUBO quantum benchmark route",
        approach="optimization",
        family=ProblemFamily.OPTIMIZATION,
        model_family="quantum",
        methods=["QUBO", "variational quantum algorithm"],
        data_needed=[],
        outputs=["objective value"],
        why_fit="state-of-the-art on benchmark datasets",
        summary="Map the problem to a binary quadratic form and solve it as QUBO.",
    )

    report = MethodFitGate().evaluate(
        card, subproblem, route, available_input_files=["soil.csv", "weather.csv"]
    )

    assert not report.passed
    assert report.routing_hint == "reroute_method"
    assert any("mismatched" in issue for issue in report.issues)


def test_irrigation_water_balance_route_passes() -> None:
    card, subproblem = _irrigation_card()
    route = ModelingRoute(
        route_id="route_water_balance",
        name="FAO-56 soil-water-balance scheduling route",
        approach="mechanistic",
        family=ProblemFamily.OPTIMIZATION,
        model_family="soil_water_balance",
        methods=[
            "FAO-56 Penman-Monteith",
            "soil water balance",
            "irrigation scheduling optimization",
        ],
        data_needed=["soil.csv", "weather.csv", "rainfall", "temperature"],
        outputs=["ET estimate", "soil water balance", "irrigation schedule"],
        why_fit=(
            "ET0 and rainfall drive net water demand; the schedule controls "
            "irrigation_amount subject to soil moisture bounds."
        ),
        summary="Mechanistic ET and soil-water-balance model with scheduling decisions.",
    )

    report = MethodFitGate().evaluate(
        card, subproblem, route, available_input_files=["soil.csv", "weather.csv"]
    )

    assert report.passed
    assert report.score >= 8.0
    assert report.routing_hint == "proceed"


def test_entropy_topsis_route_passes_for_evaluation_problem() -> None:
    subproblem = SubProblem(
        sub_id="P1",
        statement="Rank alternatives from multiple criteria and report final scores.",
        required_outputs=["criteria weights", "ranking"],
        input_data_refs=["criteria.csv"],
    )
    card = ProblemCard(
        title="Supplier evaluation",
        problem_summary="Evaluate and rank candidates using criteria indicators.",
        subproblems=[subproblem],
    )
    route = ModelingRoute(
        route_id="route_topsis",
        name="Entropy TOPSIS route",
        approach="data_driven",
        family=ProblemFamily.EVALUATION,
        model_family="multi_criteria_evaluation",
        methods=["entropy weight method", "TOPSIS"],
        data_needed=["criteria.csv"],
        outputs=["criteria weights", "ranking"],
        why_fit="Entropy weights criteria and TOPSIS ranks alternatives by closeness.",
        summary="Multi-criteria evaluation with entropy weighting and TOPSIS.",
    )

    report = MethodFitGate().evaluate(
        card, subproblem, route, available_input_files=["criteria.csv"]
    )

    assert report.passed


def test_network_flow_centrality_route_passes_for_network_problem() -> None:
    subproblem = SubProblem(
        sub_id="P2",
        statement="Analyze a transportation network with capacities and critical nodes.",
        required_outputs=["min-cost flow plan", "centrality scores"],
        input_data_refs=["edges.csv"],
    )
    card = ProblemCard(
        title="Network resilience",
        problem_summary="Use graph data to evaluate flows and important nodes.",
        subproblems=[subproblem],
    )
    route = ModelingRoute(
        route_id="route_network",
        name="Min-cost-flow and centrality route",
        approach="network",
        family=ProblemFamily.GRAPH,
        model_family="graph_flow",
        methods=["min-cost-flow", "centrality"],
        data_needed=["edges.csv", "capacity"],
        outputs=["min-cost flow plan", "centrality scores"],
        why_fit="Edge capacities define flow constraints and node measures identify bottlenecks.",
        summary="Network optimization and centrality analysis.",
    )

    report = MethodFitGate().evaluate(card, subproblem, route, available_input_files=["edges.csv"])

    assert report.passed
