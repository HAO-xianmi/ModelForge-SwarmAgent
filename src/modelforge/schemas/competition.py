"""Schemas for the competition-thinking agents (Phase H, Slice 3b-3d):
AssumptionIntelligence, SensitivityPlanner, RedTeam.
"""

from __future__ import annotations

from pydantic import Field

from modelforge.schemas.base import MFBaseModel


# --------------------------------------------------------------------------- #
# Assumptions (3b)
# --------------------------------------------------------------------------- #
class Assumption(MFBaseModel):
    assumption_id: str
    statement: str
    justification: str = ""
    impact: str = ""  # what it simplifies / why it is load-bearing


class AssumptionSet(MFBaseModel):
    assumptions: list[Assumption] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Sensitivity plan (3c)
# --------------------------------------------------------------------------- #
class SensitivityParameter(MFBaseModel):
    name: str
    baseline: str = ""
    low: str = ""
    high: str = ""
    rationale: str = ""


class SensitivityPlan(MFBaseModel):
    subproblem_id: str | None = None
    parameters: list[SensitivityParameter] = Field(default_factory=list)
    outcomes: list[str] = Field(default_factory=list)  # what to measure
    method: str = ""  # one-at-a-time | Monte-Carlo | grid | leave-one-out
    expected_relationship: str = ""


# --------------------------------------------------------------------------- #
# Red team (3d)
# --------------------------------------------------------------------------- #
class RedTeamFinding(MFBaseModel):
    severity: str  # BLOCKER | MAJOR | MINOR | INFO
    category: str  # overfitting | assumption | stronger_model | validation |
    #                data_leakage | weak_sensitivity | domain_mismatch | other
    description: str
    recommendation: str = ""


class RedTeamReport(MFBaseModel):
    findings: list[RedTeamFinding] = Field(default_factory=list)
    verdict: str = "PASS"  # PASS | REVISE | BLOCK
    summary: str = ""

    def blocking(self) -> list[RedTeamFinding]:
        return [f for f in self.findings if f.severity in ("BLOCKER", "MAJOR")]
