"""Phase D: method library tests."""

from __future__ import annotations

from modelforge.schemas.enums import MethodCategory, ProblemFamily
from modelforge.schemas.problem import DomainAnalysis, ProblemCard
from modelforge.services.method_library import MethodLibrary, get_method_library


def test_library_has_at_least_20_methods() -> None:
    lib = get_method_library()
    assert len(lib.all()) >= 20


def test_all_method_ids_unique() -> None:
    lib = get_method_library()
    ids = [m.method_id for m in lib.all()]
    assert len(ids) == len(set(ids))


def test_required_fields_populated() -> None:
    lib = get_method_library()
    for m in lib.all():
        assert m.name and m.summary
        assert m.evaluation_metrics, m.method_id
        assert m.pilot_template, m.method_id
        assert m.references, m.method_id


def test_get_and_categories() -> None:
    lib = get_method_library()
    assert lib.get("linear_regression") is not None
    assert lib.get("nonexistent") is None
    opt = lib.by_category(MethodCategory.OPTIMIZATION)
    assert {m.method_id for m in opt} >= {"linear_programming", "integer_programming"}


def test_by_family() -> None:
    lib = get_method_library()
    graph = {m.method_id for m in lib.by_family(ProblemFamily.GRAPH)}
    assert graph >= {"shortest_path", "max_flow", "centrality"}


def test_search() -> None:
    lib = get_method_library()
    found = {m.method_id for m in lib.search("forecast")}
    assert "arima" in found or "exponential_smoothing" in found


def test_retrieve_ranks_prediction_methods() -> None:
    lib = MethodLibrary()
    card = ProblemCard(
        title="Sales forecasting",
        problem_summary="Predict next month sales from historical data.",
        objectives=["forecast sales", "minimize RMSE"],
    )
    domain = DomainAnalysis(
        likely_problem_families=[ProblemFamily.PREDICTION],
        domain_tags=["time series", "forecasting"],
        key_terms=["sales", "forecast"],
    )
    methods = lib.retrieve(card, domain, top_k=5)
    assert methods
    # All returned have a suitability score and prediction-family methods rank.
    assert all(m.suitability_score > 0 for m in methods)
    top_ids = {m.method_id for m in methods}
    assert top_ids & {"linear_regression", "arima", "random_forest", "exponential_smoothing"}


def test_retrieve_never_empty() -> None:
    lib = MethodLibrary()
    card = ProblemCard(title="Totally unknown problem")
    domain = DomainAnalysis(likely_problem_families=[ProblemFamily.UNKNOWN])
    methods = lib.retrieve(card, domain)
    assert len(methods) >= 1
