"""Slice 2a: domain/mechanistic model knowledge base."""

from __future__ import annotations

from modelforge.schemas.enums import ProblemFamily
from modelforge.services.method_library.domain_models import (
    DOMAIN_MODELS,
    DomainModelLibrary,
    get_domain_model_library,
)


def test_every_model_has_rich_metadata():
    for m in DOMAIN_MODELS:
        assert m.model_id and m.name and m.summary
        assert m.governing_equations, f"{m.model_id} has no equations"
        assert m.assumptions and m.failure_modes
        assert m.validation_methods and m.sensitivity_methods
        assert m.implementation_hints and m.references
        assert m.families and m.keywords


def test_model_ids_are_unique():
    ids = [m.model_id for m in DOMAIN_MODELS]
    assert len(ids) == len(set(ids))


def test_kb_covers_all_four_benchmark_categories():
    lib = get_domain_model_library()
    irrigation = lib.retrieve("irrigation soil moisture drought tank layout",
                              [ProblemFamily.OPTIMIZATION, ProblemFamily.PREDICTION])
    topsis = lib.retrieve("rank counties multi-criteria evaluation weights",
                          [ProblemFamily.EVALUATION])
    network = lib.retrieve("supply network flow bottleneck resilience",
                           [ProblemFamily.GRAPH])
    forecast = lib.retrieve("hourly electricity demand forecast seasonality",
                            [ProblemFamily.PREDICTION])
    assert any("penman" in m.model_id or "soil" in m.model_id for m in irrigation)
    assert any("topsis" in m.model_id for m in topsis)
    assert any("flow" in m.model_id or "resilience" in m.model_id for m in network)
    assert any("gbdt" in m.model_id or "seasonal" in m.model_id for m in forecast)


def test_retrieval_ranks_and_populates_suitability():
    lib = get_domain_model_library()
    res = lib.retrieve("evapotranspiration irrigation crop water demand",
                       [ProblemFamily.OPTIMIZATION], top_k=3)
    assert res
    assert res[0].suitability_score > 0
    assert len(res) <= 3


def test_library_is_extensible_with_custom_models():
    from modelforge.schemas.method_kb import DomainModel
    extra = DomainModel(
        model_id="custom_x", name="Custom", category="mechanistic",
        families=[ProblemFamily.SIMULATION], summary="s",
        governing_equations=["x=1"], keywords=["widget"],
    )
    lib = DomainModelLibrary(models=[extra])
    assert lib.get("custom_x") is not None
    assert lib.retrieve("a widget problem", [ProblemFamily.SIMULATION])
