"""Slice 1b: the architect must address each sub-problem with its own section.

Root cause #1 was that `problem_card.subproblems` existed but was dropped: one
generic model section stood in for an inherently multi-part problem. The outline
must now emit one model section per sub-problem plus the competition scaffolding
(assumptions, nomenclature, sensitivity, limitations).
"""

from __future__ import annotations

from modelforge.agents.base import AgentContext
from modelforge.agents.paper_architect import PaperArchitectAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.problem import ProblemCard, SubProblem


def _ctx() -> AgentContext:
    return AgentContext(run_id="run_test", provider=MockProvider())


def _card() -> ProblemCard:
    return ProblemCard(
        title="Agricultural Irrigation System Optimization",
        subproblems=[
            SubProblem(
                sub_id="P1",
                statement="Predict soil moisture from weather",
                objective="forecast 5cm_SM",
            ),
            SubProblem(
                sub_id="P2",
                statement="Design minimum-cost irrigation layout",
                objective="min cost",
            ),
            SubProblem(
                sub_id="P3",
                statement="Dynamic drought scheduling and reserve",
                objective="max survival",
            ),
            SubProblem(
                sub_id="P4",
                statement="Multi-period adaptation plan",
                objective="adapt May-July",
            ),
        ],
        assumptions_to_confirm=["flat terrain", "uniform soil"],
        variables=["It", "Vk(t)"],
    )


def test_outline_has_one_model_section_per_subproblem():
    res = PaperArchitectAgent(_ctx()).architect(
        "Irrigation", [], figure_ids=[], table_ids=[], citations=[], problem_card=_card()
    )
    assert res.ok and res.output is not None
    ids = {s.section_id for s in res.output.sections}
    for sid in ("model_P1", "model_P2", "model_P3", "model_P4"):
        assert sid in ids, f"missing per-sub-problem section {sid}"


def test_outline_has_competition_scaffolding():
    res = PaperArchitectAgent(_ctx()).architect(
        "Irrigation", [], figure_ids=[], table_ids=[], citations=[], problem_card=_card()
    )
    titles = " ".join(s.title for s in res.output.sections).lower()
    ids = {s.section_id for s in res.output.sections}
    assert "assumptions" in ids
    assert "nomenclature" in ids or "symbol" in titles
    assert "sensitivity" in ids
    assert "limitations" in ids
    assert res.output.template == "competition"


def test_outline_falls_back_to_single_model_without_subproblems():
    # Backward compatible: no problem card -> a single model section, not a crash.
    res = PaperArchitectAgent(_ctx()).architect(
        "Report", [], figure_ids=[], table_ids=[], citations=[]
    )
    assert res.ok
    ids = {s.section_id for s in res.output.sections}
    assert "model" in ids
    assert not any(sid.startswith("model_P") for sid in ids)
