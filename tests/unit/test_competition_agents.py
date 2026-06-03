"""Slice 3b/3c/3d: AssumptionIntelligence, SensitivityPlanner, RedTeam agents."""

from __future__ import annotations

from modelforge.agents.assumption_agent import AssumptionIntelligenceAgent
from modelforge.agents.base import AgentContext
from modelforge.agents.red_team import RedTeamAgent
from modelforge.agents.sensitivity_planner import SensitivityPlannerAgent
from modelforge.providers.llm import MockProvider
from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.problem import DomainAnalysis, ProblemCard, SubProblem


def _ctx() -> AgentContext:
    return AgentContext(run_id="r", provider=MockProvider())


def _card() -> ProblemCard:
    return ProblemCard(
        title="Irrigation",
        problem_summary="minimize irrigation cost with soil moisture and drought",
        subproblems=[SubProblem(sub_id="P2", statement="design minimum-cost irrigation layout")],
        assumptions_to_confirm=["the farm terrain is flat"],
    )


def _da() -> DomainAnalysis:
    return DomainAnalysis(
        likely_problem_families=[ProblemFamily.OPTIMIZATION],
        key_terms=["irrigation", "soil", "drought", "cost", "layout"],
    )


# --------------------------- 3b assumptions -------------------------------- #
def test_assumption_agent_produces_numbered_justified_assumptions():
    res = AssumptionIntelligenceAgent(_ctx()).generate(_card(), _da(), max_assumptions=4)
    assert res.ok and res.output is not None
    a = res.output.assumptions
    assert 1 <= len(a) <= 4
    assert all(x.assumption_id and x.statement and x.justification for x in a)
    assert a[0].assumption_id == "A1"


# --------------------------- 3c sensitivity -------------------------------- #
def test_sensitivity_planner_designs_param_to_outcome_study():
    res = SensitivityPlannerAgent(_ctx()).plan(_card(), _da(), subproblem=_card().subproblems[0])
    assert res.ok and res.output is not None
    p = res.output
    assert p.parameters and p.outcomes and p.method
    assert p.expected_relationship
    assert p.subproblem_id == "P2"


# ------------------------------ 3d red team -------------------------------- #
_WEAK = "# Report\n\n## Methods\nWe formulated a QUBO model.\n\n## Results\nobjective 98.\n"
_STRONG = (
    "# Report\n\n## Model Assumptions\nAssumption 1: flat terrain.\n\n"
    "## Methods\nWe fit a model with regularization and report R2 on the held-out "
    "test set, beating the baseline. Cross-validation confirms it.\n\n"
    "## Sensitivity and Robustness Analysis\nWe vary the key parameter.\n"
)


def test_red_team_flags_weak_report():
    res = RedTeamAgent(_ctx()).review(_WEAK)
    assert res.ok and res.output is not None
    assert res.output.verdict in ("REVISE", "BLOCK")
    cats = {f.category for f in res.output.findings}
    assert "validation" in cats
    assert "weak_sensitivity" in cats


def test_red_team_passes_strong_report():
    res = RedTeamAgent(_ctx()).review(_STRONG)
    assert res.output.verdict == "PASS"
    assert not res.output.blocking()


def test_red_team_blocks_on_leaked_ids():
    leaked = _STRONG + "\nsee run claim_deadbeef99 for details.\n"
    res = RedTeamAgent(_ctx()).review(leaked)
    assert res.output.verdict == "BLOCK"
    assert any(f.severity == "BLOCKER" for f in res.output.findings)
