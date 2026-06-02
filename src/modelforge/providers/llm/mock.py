"""Deterministic mock LLM provider.

Drives keyless CI and tests. It does NOT call any network. For each agent it
returns schema-valid JSON derived from the prompt content, so the workflow
produces sensible, reproducible reasoning artifacts without an API key.

Design: agents embed a ``[[MOCK:<agent_key>]]`` directive plus a JSON
``[[CONTEXT]]...[[/CONTEXT]]`` block in the user message. The mock dispatches on
the agent key and shapes its response from the context. Crucially, the mock
NEVER emits experiment metrics — those come only from real sandbox execution
(working rule 5). It produces plans, critiques, and text, not measurements.
"""

from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel

from modelforge.providers.llm.base import LLMResponse, Message, TokenUsage

_MOCK_RE = re.compile(r"\[\[MOCK:([a-z_]+)\]\]")
_CONTEXT_RE = re.compile(r"\[\[CONTEXT\]\](.*?)\[\[/CONTEXT\]\]", re.DOTALL)


def _seeded_choice(seed_text: str, options: list[str]) -> str:
    h = int(hashlib.sha256(seed_text.encode()).hexdigest(), 16)
    return options[h % len(options)]


class MockProvider:
    name = "mock"

    def __init__(self, model: str = "mock-1") -> None:
        self.model = model

    def complete(
        self,
        messages: list[Message],
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        response_schema: type[BaseModel] | None = None,
    ) -> LLMResponse:
        prompt = "\n".join(m.content for m in messages)
        agent = self._agent_key(prompt)
        context = self._context(prompt)
        payload = _DISPATCH.get(agent, _mock_generic)(context, prompt)
        text = json.dumps(payload)
        usage = TokenUsage(
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
        )
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            usage=usage,
            latency_ms=1,
            estimated_cost=0.0,
        )

    @staticmethod
    def _agent_key(prompt: str) -> str:
        m = _MOCK_RE.search(prompt)
        return m.group(1) if m else "generic"

    @staticmethod
    def _context(prompt: str) -> dict:
        m = _CONTEXT_RE.search(prompt)
        if not m:
            return {}
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            return {}


# --------------------------------------------------------------------------- #
# Per-agent mock generators (schema-valid, input-derived, deterministic)
# --------------------------------------------------------------------------- #
def _mock_generic(context: dict, prompt: str) -> dict:
    return {"result": "ok", "note": "mock generic response"}


def _mock_problem_parser(context: dict, prompt: str) -> dict:
    text = context.get("problem_text", "") or "Untitled modeling problem"
    title = text.strip().splitlines()[0][:80] if text.strip() else "Modeling Problem"
    # Family hint from keywords -> influences downstream domain analysis.
    return {
        "title": title.replace("[problem:", "").replace("]", "").strip() or "Modeling Problem",
        "problem_summary": text.strip()[:400],
        "objective_summary": "Build a defensible model and report its performance.",
        "subproblems": [
            {"sub_id": "sub_1", "statement": "Understand and formalize the task.", "objective": ""}
        ],
        "objectives": ["produce a validated model", "report evidence-backed results"],
        "decision_variables": [],
        "constraints": [],
        "datasets": [
            {"name": d, "description": "", "file_id": None}
            for d in context.get("datasets", [])
        ],
        "required_outputs": ["model", "metrics", "report"],
        "formatting_requirements": [],
        "variables": [],
        "ambiguities": [] if text.strip() else ["problem statement is empty"],
        "missing_information": [],
        "assumptions_to_confirm": ["data is representative of the target population"],
        "confidence": 0.85 if text.strip() else 0.3,
        "source_map": [],
    }


def _detect_family(text: str) -> str:
    t = text.lower()
    table = [
        (("forecast", "predict", "regression", "time series", "sales", "demand"), "prediction"),
        (("classify", "classification", "category", "label", "spam"), "classification"),
        (
            ("optimi", "allocat", "schedul", "maximize", "minimize", "knapsack", "resource"),
            "optimization",
        ),
        (("cluster", "segment", "group"), "clustering"),
        (("graph", "network", "shortest path", "centrality", "flow", "route"), "graph"),
        (("evaluate", "rank", "score", "criteria", "topsis", "ahp"), "evaluation"),
        (("simulat", "monte carlo", "stochastic"), "simulation"),
    ]
    for keys, fam in table:
        if any(k in t for k in keys):
            return fam
    return "prediction"


def _mock_domain_analyst(context: dict, prompt: str) -> dict:
    text = (context.get("problem_summary", "") + " " + context.get("title", "")).lower()
    family = _detect_family(text)
    return {
        "domain_tags": [family, "mathematical_modeling"],
        "likely_problem_families": [family],
        "domain_assumptions": ["the provided data is relevant to the objective"],
        "key_terms": list(re.findall(r"[a-z]{4,}", text))[:8],
        "data_requirements": ["a tabular dataset with features and a target where applicable"],
        "potential_external_facts": [],
        "research_questions": ["which model family best fits the data?"],
        "risks": ["overfitting", "data leakage", "insufficient validation"],
        "recommended_specialists": [family],
        "data_modality": "tabular",
        "time_dependence": family == "prediction" and "time" in text,
        "spatial_dependence": False,
        "optimization_required": family == "optimization",
        "uncertainty_required": family == "simulation",
        "interpretability_required": True,
    }


def _mock_strategy_proposer(context: dict, prompt: str) -> dict:
    goal = context.get("design_goal", "performance_first")
    family = context.get("problem_family", "prediction")
    methods = context.get("candidate_methods", [])
    # Pick a method consistent with the goal.
    method_id = _pick_method(goal, family, methods)
    template = context.get("template_for_method", {}).get(method_id, family)
    return {
        "strategy_id": context.get("strategy_id", f"strategy_{goal}_001"),
        "strategy_name": f"{goal.replace('_', ' ').title()} {family} pipeline",
        "design_goal": goal,
        "problem_family": family,
        "subproblem_mapping": ["sub_1"],
        "method_stack": [{"method_id": method_id, "role": "core_model", "rationale": goal}],
        "assumptions": ["data is clean enough after basic preprocessing"],
        "variable_definitions": [],
        "mathematical_formulation": f"Fit a {method_id} model and evaluate on a held-out split.",
        "data_requirements": ["features", "target"],
        "preprocessing_plan": ["impute missing", "scale features", "train/test split"],
        "experiment_plan": ["pilot run", "formal run", "baseline", "robustness"],
        "baseline_plan": ["simple baseline model"],
        "robustness_plan": ["repeated seeds"],
        "visualization_plan": ["prediction vs actual"],
        "expected_artifacts": ["metrics.json", "figure"],
        "estimated_runtime_seconds": 10.0,
        "implementation_risk": "low",
        "known_limitations": ["mock-generated plan; refine with real analysis"],
        "fallback_plan": ["fall back to a linear/logistic baseline"],
        "pilot_template": template,
    }


# Methods that belong to each problem family (used to keep the mock's choice
# family-consistent even when retrieval returns cross-family candidates).
_FAMILY_METHODS = {
    "prediction": ["linear_regression", "random_forest", "gradient_boosting", "arima"],
    "classification": ["logistic_regression", "random_forest", "decision_tree"],
    "optimization": ["integer_programming", "linear_programming", "genetic_algorithm"],
    "graph": ["shortest_path", "centrality", "max_flow"],
    "clustering": ["kmeans", "dbscan", "hierarchical_clustering"],
    "evaluation": ["topsis", "entropy_weight", "pca"],
    "simulation": ["monte_carlo"],
}

_FAMILY_DEFAULT = {
    "prediction": "linear_regression",
    "classification": "logistic_regression",
    "optimization": "integer_programming",
    "graph": "shortest_path",
    "clustering": "kmeans",
    "evaluation": "topsis",
    "simulation": "monte_carlo",
}


def _pick_method(goal: str, family: str, methods: list[str]) -> str:
    prefer = {
        ("interpretability_first", "prediction"): "linear_regression",
        ("performance_first", "prediction"): "random_forest",
        ("innovation_first", "prediction"): "gradient_boosting",
        ("interpretability_first", "classification"): "logistic_regression",
        ("performance_first", "classification"): "random_forest",
        ("innovation_first", "classification"): "decision_tree",
        ("interpretability_first", "optimization"): "linear_programming",
        ("performance_first", "optimization"): "integer_programming",
        ("innovation_first", "optimization"): "genetic_algorithm",
    }
    chosen = prefer.get((goal, family))
    if chosen:
        return chosen
    # Constrain to methods that BELONG to the detected family, so the chosen
    # method's code template always matches the family (avoids running, e.g.,
    # an evaluation template for a graph problem).
    family_methods = _FAMILY_METHODS.get(family, [])
    in_family = [m for m in methods if m in family_methods]
    if in_family:
        return _seeded_choice(goal + family, in_family)
    if family_methods:
        return _seeded_choice(goal + family, family_methods)
    return _FAMILY_DEFAULT.get(family, "linear_regression")


def _mock_skeptic(context: dict, prompt: str) -> dict:
    candidates = context.get("strategy_ids", [])
    reviews = []
    for i, sid in enumerate(candidates):
        # Deterministically vary severity so the skeptic does not blandly approve all.
        is_strict = (i == 0)
        reviews.append({
            "strategy_id": sid,
            "strengths": ["addresses the core task", "has a runnable pilot"],
            "weaknesses": ["assumptions need validation"],
            "issues": (
                [{
                    "severity": "MAJOR",
                    "category": "validation",
                    "description": "validation plan should be made explicit",
                    "required_fix": "specify the train/test protocol",
                }]
                if is_strict else
                [{
                    "severity": "MINOR",
                    "category": "runtime",
                    "description": "runtime not estimated precisely",
                    "required_fix": "add a runtime budget",
                }]
            ),
            "required_pilot_experiments": ["baseline comparison"],
            "recommendation": "revise" if is_strict else "pass",
        })
    return {"reviews": reviews, "summary": "Mock critique: candidates are viable with fixes."}


def _mock_strategy_judge(context: dict, prompt: str) -> dict:
    pilots = context.get("pilots", [])  # [{strategy_id, succeeded, metrics}]
    succeeded = [p for p in pilots if p.get("succeeded")]
    chosen = None
    referenced = []
    if succeeded:
        # Choose the pilot with the best primary metric if available, else first.
        chosen = succeeded[0]["strategy_id"]
        referenced = [p.get("pilot_id", "") for p in succeeded if p.get("pilot_id")]
    elif context.get("strategy_ids"):
        chosen = context["strategy_ids"][0]
    scores = [
        {
            "strategy_id": p.get("strategy_id", ""),
            "problem_fit": 0.8, "data_fit": 0.7, "feasibility": 0.9 if p.get("succeeded") else 0.3,
            "interpretability": 0.7, "experimental_evidence": 0.9 if p.get("succeeded") else 0.1,
            "robustness_potential": 0.6, "novelty": 0.5, "runtime_cost": 0.8,
            "total": 0.78 if p.get("succeeded") else 0.3,
        }
        for p in pilots
    ]
    return {
        "decision": "SELECT" if chosen else "ESCALATE_TO_HUMAN",
        "selected_strategy_id": chosen,
        "merged_from": [],
        "rationale": "Selected the strategy with successful pilot evidence."
        if succeeded else "No successful pilot; escalating.",
        "rejected_alternatives": [
            p.get("strategy_id") for p in pilots if p.get("strategy_id") != chosen
        ],
        "scores": scores,
        "referenced_pilot_ids": referenced,
        "risks": ["mock judgment; confirm with a human checkpoint"],
    }


def _mock_code_author(context: dict, prompt: str) -> dict:
    # The CodeAuthorAgent uses the deterministic CodeGenerator for the actual
    # code; the LLM only chooses template + model_kind. Mock returns that choice.
    return {
        "template": context.get("template", context.get("problem_family", "prediction")),
        "model_kind": context.get("model_kind", ""),
        "notes": "mock code-author selection",
    }


def _mock_debugger(context: dict, prompt: str) -> dict:
    return {
        "can_fix": False,
        "reason": "mock debugger does not modify code; relies on template correctness",
        "explanation": "No patch proposed by the mock provider.",
    }


def _mock_paper_architect(context: dict, prompt: str) -> dict:
    claim_ids = context.get("claim_ids", [])
    figure_ids = context.get("figure_ids", [])
    table_ids = context.get("table_ids", [])
    citation_ids = context.get("citation_ids", [])
    sections = [
        {"section_id": "abstract", "title": "Abstract", "purpose": "summary",
         "required_claim_ids": claim_ids[:2], "word_budget": 150, "human_review_required": False},
        {"section_id": "problem", "title": "Problem Restatement", "purpose": "restate",
         "word_budget": 200},
        {"section_id": "methods", "title": "Model Construction", "purpose": "describe model",
         "required_citation_ids": citation_ids[:3], "word_budget": 300},
        {"section_id": "results", "title": "Experimental Results", "purpose": "report results",
         "required_claim_ids": claim_ids, "required_figure_ids": figure_ids,
         "required_table_ids": table_ids, "word_budget": 350},
        {"section_id": "robustness", "title": "Sensitivity and Robustness Analysis",
         "purpose": "stability", "required_claim_ids": claim_ids, "word_budget": 250},
        {"section_id": "conclusion", "title": "Conclusions", "purpose": "wrap up",
         "word_budget": 200},
        {"section_id": "limitations", "title": "Limitations", "purpose": "limits",
         "word_budget": 150, "human_review_required": True},
    ]
    return {"sections": sections, "title": context.get("title", "Modeling Report"),
            "template": context.get("template", "generic")}


def _mock_paper_writer(context: dict, prompt: str) -> dict:
    # The writer composes prose deterministically from verified claims; the mock
    # returns short paragraph text keyed by section. Real verified numbers are
    # injected by the writer agent, not invented here.
    section_id = context.get("section_id", "section")
    claims = context.get("claims", [])  # [{statement, claim_id}]
    body = " ".join(
        f"{c['statement']} [claim:{c['claim_id']}]" for c in claims
    ) or "This section summarizes the relevant analysis."
    return {"section_id": section_id, "text": body}


_DISPATCH = {
    "problem_parser": _mock_problem_parser,
    "domain_analyst": _mock_domain_analyst,
    "strategy_proposer": _mock_strategy_proposer,
    "skeptic": _mock_skeptic,
    "strategy_judge": _mock_strategy_judge,
    "code_author": _mock_code_author,
    "debugger": _mock_debugger,
    "paper_architect": _mock_paper_architect,
    "paper_writer": _mock_paper_writer,
    "generic": _mock_generic,
}
