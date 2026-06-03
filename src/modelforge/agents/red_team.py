"""RedTeamAgent (Phase H, Slice 3d) — adversarial pre-export gate.

Tries to destroy the solution before it ships: overfitting, unreasonable
assumptions, a stronger model, missing validation, data leakage, weak sensitivity,
domain mismatch, would-a-judge-challenge-this. Emits findings with severity; a
BLOCKER/MAJOR finding blocks export until resolved or explicitly waived.

The mock runs DETERMINISTIC structural checks on the report text (a real
adversarial gate even without an LLM); a real provider adds reasoning-level
critique.
"""

from __future__ import annotations

import re

from modelforge.agents.base import AgentResult, BaseAgent
from modelforge.schemas.competition import RedTeamFinding, RedTeamReport


class RedTeamAgent(BaseAgent[RedTeamReport]):
    agent_key = "red_team"
    output_schema = RedTeamReport

    def review(self, report_markdown: str) -> AgentResult[RedTeamReport]:
        context = {
            "report_excerpt": report_markdown[:6000],
            # Deterministic structural signals the mock can check without an LLM.
            "signals": _signals(report_markdown),
        }
        return self.run_structured(context, temperature=0.0, max_tokens=1200)


def _signals(md: str) -> dict:
    t = md.lower()
    def has(*ks: str) -> bool:
        return any(k in t for k in ks)
    return {
        "has_baseline": has("baseline", "基线", "对比模型"),
        "has_validation": has("cross-validation", "交叉验证", "rmse", "r2", "r²", "held-out", "test set"),
        "has_sensitivity": has("sensitivity", "灵敏度", "robustness", "鲁棒性"),
        "has_assumptions": bool(re.search(r"assumption\s*\d|假设[一二三四五\d]", t)),
        "mentions_overfit_control": has("regulariz", "cross-validation", "overfit", "held-out"),
        "leaked_ids": bool(re.search(r"\bclaim_[0-9a-f]{4,}", t)),
    }
