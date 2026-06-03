"""Guard: prompt contracts must stay domain-neutral.

Root cause #3 of weak output was few-shot contamination — hard-coded
qboost/QUBO/AdaBoost examples in the agent output-contracts steered every
problem (including an irrigation problem) toward a quantum-classifier write-up.
These tests fail if any domain-specific method name leaks back into a contract.
"""

from __future__ import annotations

import pytest

from modelforge.prompts.registry import PROMPTS

# Method-/domain-specific tokens that must NOT appear as few-shot examples in the
# generic agent contracts (the codegen template library may still implement them).
_CONTAMINANTS = ("qboost", "qubo", "adaboost")

# Agents whose contracts steer modeling choices and must stay domain-neutral.
_STEERING_AGENTS = ("strategy_proposer", "code_author", "paper_architect", "domain_analyst")


@pytest.mark.parametrize("agent_key", _STEERING_AGENTS)
def test_steering_contracts_are_domain_neutral(agent_key: str):
    prompt = PROMPTS[agent_key]
    blob = (prompt.system + " " + prompt.output_contract).lower()
    for token in _CONTAMINANTS:
        assert token not in blob, (
            f"{agent_key} contract leaks domain-specific example '{token}'; "
            "use a neutral placeholder instead"
        )


def test_no_contract_hardcodes_a_specific_problem_family_as_the_answer():
    # The strategy proposer must instruct choosing the family from the problem,
    # not present a single family as the example answer.
    contract = PROMPTS["strategy_proposer"].output_contract.lower()
    assert "placeholder" in contract
    assert "candidate_methods" in contract


def test_all_known_contaminants_absent_everywhere_in_registry():
    for key, prompt in PROMPTS.items():
        blob = (prompt.system + " " + prompt.output_contract + " "
                + " ".join(prompt.forbidden)).lower()
        for token in _CONTAMINANTS:
            assert token not in blob, f"'{token}' leaked into prompt '{key}'"
