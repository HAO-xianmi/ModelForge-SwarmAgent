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
    subproblems = context.get("subproblems", [])
    # Competition structure: abstract, restatement, assumptions, nomenclature,
    # one model section PER sub-problem, sensitivity, conclusion, limitations.
    sections = [
        {"section_id": "abstract", "title": "Abstract",
         "purpose": "summarize the methods and key quantitative results",
         "required_claim_ids": claim_ids[:2], "word_budget": 200},
        {"section_id": "restatement", "title": "Problem Restatement and Analysis",
         "purpose": "restate the problem and decompose it into its sub-problems",
         "word_budget": 250},
        {"section_id": "assumptions", "title": "Model Assumptions",
         "purpose": "state the load-bearing assumptions and justify each",
         "word_budget": 200},
        {"section_id": "nomenclature", "title": "Nomenclature and Symbol Definitions",
         "purpose": "define every variable and its units", "word_budget": 150},
    ]
    if subproblems:
        for i, sp in enumerate(subproblems):
            sid = sp.get("sub_id") or f"P{i + 1}"
            stmt = (sp.get("statement") or "").strip()
            sections.append({
                "section_id": f"model_{sid}",
                "title": f"Sub-problem {sid} Model: {stmt[:48]}",
                "purpose": f"establish and solve the model for sub-problem {sid}; "
                           f"objective: {(sp.get('objective') or '')[:80]}",
                "required_claim_ids": claim_ids,
                "required_figure_ids": figure_ids,
                "required_table_ids": table_ids,
                "required_citation_ids": citation_ids[:2],
                "word_budget": 350,
            })
    else:
        sections.append({
            "section_id": "model", "title": "Model Construction and Solution",
            "purpose": "establish and solve the model",
            "required_claim_ids": claim_ids, "required_figure_ids": figure_ids,
            "required_table_ids": table_ids, "required_citation_ids": citation_ids[:3],
            "word_budget": 350})
    sections += [
        {"section_id": "sensitivity", "title": "Sensitivity and Robustness Analysis",
         "purpose": "vary key parameters and report the parameter-to-outcome relationship",
         "required_claim_ids": claim_ids, "word_budget": 250},
        {"section_id": "conclusion", "title": "Conclusions", "purpose": "wrap up",
         "word_budget": 180},
        {"section_id": "limitations", "title": "Strengths, Weaknesses and Limitations",
         "purpose": "honest evaluation of the model", "word_budget": 180,
         "human_review_required": True},
    ]
    return {"sections": sections, "title": context.get("title", "Modeling Report"),
            "template": context.get("template", "competition")}


def _mock_paper_writer(context: dict, prompt: str) -> dict:
    # Section-aware deterministic prose. Numbers come ONLY from verified claims
    # (cited via [claim:id]); the structural scaffolding (assumptions, symbol
    # table, equations, sensitivity table) is generated so the report reads like
    # a competition paper even under the keyless mock. Real providers replace
    # this with genuine modeling prose.
    section_id = context.get("section_id", "section")
    sid = section_id.lower()
    claims = context.get("claims", [])  # [{statement, claim_id}]
    assumptions = context.get("assumptions", [])
    variables = context.get("variables", [])
    claim_text = " ".join(f"{c['statement']} [claim:{c['claim_id']}]" for c in claims)

    if "assumption" in sid:
        items = assumptions or [
            "the provided data is representative of the operating conditions",
            "the governing relationships are stable over the modeling horizon",
            "measurement noise is unbiased",
        ]
        body = "We adopt the following load-bearing assumptions. " + " ".join(
            f"Assumption {i + 1}: {a}." for i, a in enumerate(items)
        )
    elif "nomenclature" in sid or "symbol" in sid:
        rows = "\n".join(f"| ${v}$ | quantity {v} | - |" for v in (variables or ["x", "y", "t"]))
        body = (
            "Table 1 defines the notation used throughout.\n\n"
            "| Symbol | Description | Units |\n|---|---|---|\n" + rows
        )
    elif "sensitivity" in sid:
        body = (
            "We conduct a sensitivity analysis by perturbing the key parameter "
            "across its plausible range and recording the response. "
            + (claim_text or "The objective varies monotonically with the parameter, "
               "indicating a stable parameter-to-outcome relationship.")
            + "\n\nTable 2 reports the sensitivity sweep.\n\n"
            "| Parameter | -20% | baseline | +20% |\n|---|---|---|---|\n"
            "| key parameter | lower response | reference | upper response |"
        )
    elif sid.startswith("model"):
        # NOTE: the mock writer intentionally does NOT render the KB's domain
        # equations — dumping raw equation blocks into templated prose is
        # incoherent and regresses a reasoning judge (validated 2026-06-03).
        # The `domain_model` context is consumed only by the real
        # CompetitionWriterAgent (Slice 3), which weaves it into prose.
        body = (
            (claim_text or "We establish and solve the model for this sub-problem.")
            + " The governing relation is\n\n$$\ny = a \\cdot x + b\n$$\n\n"
            "and is solved to obtain the reported quantitative results."
        )
    elif sid == "abstract":
        body = (
            "This paper decomposes the problem into its sub-problems and solves "
            "each with a tailored model, validating results against a baseline. "
            + claim_text
        )
    elif "restatement" in sid:
        body = (
            "We restate the problem and decompose it into its constituent "
            "sub-problems, whose outputs feed one another in sequence."
        )
    elif "limitation" in sid:
        body = (
            "Strengths: the framework is modular, evidence-grounded, and validated "
            "against a baseline. Weaknesses: the simplifying assumptions may not "
            "hold under all regimes, and the analysis covers a single season; "
            "multi-year validation is left for future work."
        )
    elif "conclusion" in sid:
        body = (
            "We conclude that the decomposed models jointly address the problem; "
            + (claim_text or "the results are consistent and defensible.")
        )
    else:
        body = claim_text or "This section summarizes the relevant analysis."
    return {"section_id": section_id, "text": body}


_ROUTE_MERIT = {
    "mechanistic": dict(problem_fit=0.85, modeling_depth=0.80, innovation=0.50,
                        feasibility=0.80, robustness=0.70, interpretability=0.90),
    "data_driven": dict(problem_fit=0.80, modeling_depth=0.75, innovation=0.55,
                        feasibility=0.85, robustness=0.60, interpretability=0.50),
    "optimization": dict(problem_fit=0.80, modeling_depth=0.80, innovation=0.50,
                         feasibility=0.70, robustness=0.65, interpretability=0.70),
    "stochastic": dict(problem_fit=0.75, modeling_depth=0.70, innovation=0.60,
                       feasibility=0.70, robustness=0.85, interpretability=0.60),
    "network": dict(problem_fit=0.80, modeling_depth=0.75, innovation=0.55,
                    feasibility=0.75, robustness=0.70, interpretability=0.70),
    "hybrid": dict(problem_fit=0.85, modeling_depth=0.85, innovation=0.75,
                   feasibility=0.65, robustness=0.75, interpretability=0.60),
}


def _route_from_model(rid: str, m: dict, approach: str, family: str, sub) -> dict:
    return {
        "route_id": rid, "name": f"{m['name']} route", "approach": approach,
        "family": family, "summary": m.get("summary", ""),
        "domain_model_ids": [m["model_id"]], "method_ids": [],
        "assumptions": m.get("assumptions") or ["the domain assumptions hold"],
        "advantages": m.get("advantages") or ["grounded in a validated domain model"],
        "limitations": m.get("limitations") or ["model simplifications apply"],
        "risks": ["parameter estimation / data availability"],
        "expected_metrics": _ROUTE_MERIT.get(approach, _ROUTE_MERIT["data_driven"]),
        "subproblem_id": sub,
    }


def _mock_route_generator(context: dict, prompt: str) -> dict:
    """Build >= min_routes substantially-different routes (distinct approaches)
    grounded in the retrieved domain models, padding with generic methods."""
    dms = context.get("domain_models", [])
    methods = context.get("methods", [])
    family = context.get("problem_family", "unknown")
    sub = context.get("subproblem_id")
    min_routes = int(context.get("min_routes", 5))

    by_approach: dict[str, list[dict]] = {}
    for m in dms:
        by_approach.setdefault(m.get("approach", "data_driven"), []).append(m)

    routes: list[dict] = []
    for ap in ("mechanistic", "data_driven", "optimization", "stochastic", "network"):
        cand = by_approach.get(ap)
        if cand:
            routes.append(_route_from_model(f"route_{ap}", cand[0], ap, family, sub))

    mech, data = by_approach.get("mechanistic"), by_approach.get("data_driven")
    if mech and data:
        r = _route_from_model("route_hybrid", mech[0], "hybrid", family, sub)
        r["name"] = f"Hybrid: {data[0]['name']} feeding {mech[0]['name']}"
        r["summary"] = ("Hybrid route: a data-driven model supplies inputs/parameters "
                        "to a mechanistic model, combining accuracy with interpretability.")
        r["domain_model_ids"] = [mech[0]["model_id"], data[0]["model_id"]]
        routes.append(r)

    i = 0
    while len(routes) < min_routes and i < len(methods):
        mid = methods[i]
        i += 1
        if any(mid in r.get("method_ids", []) for r in routes):
            continue
        routes.append({
            "route_id": f"route_method_{i}", "name": f"{mid} baseline route",
            "approach": "data_driven", "family": family,
            "summary": f"A route built on the generic {mid} method as a baseline.",
            "domain_model_ids": [], "method_ids": [mid],
            "assumptions": ["standard method assumptions hold"],
            "advantages": ["simple and fast to implement"],
            "limitations": ["less domain-specific than a mechanistic route"],
            "risks": ["may underfit the domain structure"],
            "expected_metrics": _ROUTE_MERIT["data_driven"], "subproblem_id": sub,
        })
    return {"routes": routes, "subproblem_id": sub}


def _mock_assumption_agent(context: dict, prompt: str) -> dict:
    existing = context.get("existing_assumptions", [])
    domain = context.get("domain_assumptions", [])
    maxn = int(context.get("max_assumptions", 5))
    pool = list(dict.fromkeys([*existing, *domain])) or [
        "the provided data is representative of the operating conditions"
    ]
    items = [
        {
            "assumption_id": f"A{i + 1}",
            "statement": s,
            "justification": "adopted to keep the model tractable while preserving "
            "the dominant effects",
            "impact": "simplifies the formulation; relaxing it would require a more "
            "detailed sub-model",
        }
        for i, s in enumerate(pool[:maxn])
    ]
    return {"assumptions": items}


def _mock_sensitivity_planner(context: dict, prompt: str) -> dict:
    methods = context.get("sensitivity_methods", [])
    params = [
        {"name": m, "baseline": "reference value", "low": "-20%", "high": "+20%",
         "rationale": "spans the plausible operating range"}
        for m in methods[:3]
    ] or [{"name": "key parameter", "baseline": "reference value", "low": "-20%",
           "high": "+20%", "rationale": "plausible operating range"}]
    return {
        "subproblem_id": context.get("subproblem_id"),
        "parameters": params,
        "outcomes": ["objective value", "feasibility margin"],
        "method": "one-at-a-time",
        "expected_relationship": "the outcome varies monotonically with each "
        "parameter over the tested range",
    }


def _mock_red_team(context: dict, prompt: str) -> dict:
    s = context.get("signals", {})
    findings: list[dict] = []
    if not s.get("has_baseline"):
        findings.append({"severity": "MAJOR", "category": "validation",
                         "description": "no baseline comparison found",
                         "recommendation": "add a simple baseline and beat it"})
    if not s.get("has_validation"):
        findings.append({"severity": "MAJOR", "category": "validation",
                         "description": "no out-of-sample validation / metrics found",
                         "recommendation": "report held-out or cross-validation metrics"})
    if not s.get("has_sensitivity"):
        findings.append({"severity": "MAJOR", "category": "weak_sensitivity",
                         "description": "no sensitivity / robustness analysis found",
                         "recommendation": "add a parameter->outcome sensitivity analysis"})
    if not s.get("has_assumptions"):
        findings.append({"severity": "MINOR", "category": "assumption",
                         "description": "assumptions are not enumerated",
                         "recommendation": "state numbered, justified assumptions"})
    if not s.get("mentions_overfit_control"):
        findings.append({"severity": "MINOR", "category": "overfitting",
                         "description": "no overfitting control mentioned",
                         "recommendation": "mention regularization / CV / held-out evaluation"})
    if s.get("leaked_ids"):
        findings.append({"severity": "BLOCKER", "category": "other",
                         "description": "internal claim ids leaked into the report body",
                         "recommendation": "strip internal tokens before export"})
    has = lambda sev: any(f["severity"] == sev for f in findings)  # noqa: E731
    verdict = "BLOCK" if has("BLOCKER") else ("REVISE" if has("MAJOR") else "PASS")
    return {"findings": findings, "verdict": verdict,
            "summary": f"{len(findings)} findings; verdict {verdict}."}


def _mock_competition_judge(context: dict, prompt: str) -> dict:
    """Deterministic stand-in for a real judge panel (keyless CI).

    It grades each dimension from the pre-computed structural signals passed in
    context, so the LLM layer still tracks paper quality without a network call.
    Real providers ignore these and reason over the paper text. This is a
    documented stand-in, NOT a substitute for reasoning-grade judging.
    """
    structural = context.get("structural_scores", {})
    dims = context.get("dimensions", [])
    pool = context.get("evidence_pool", {})
    # Coarse proxy for dimensions with no structural signal (e.g. innovation):
    # reward the presence of a sensitivity analysis + many equations as a weak
    # signal of a non-trivial contribution.
    signals = context.get("detected_signals", {})
    innovation_proxy = 6.0 if (
        signals.get("has_sensitivity") and signals.get("n_equations", 0) >= 10
    ) else (3.0 if signals.get("n_equations", 0) >= 4 else 1.5)
    scores: dict[str, float] = {}
    evidence: dict[str, list[str]] = {}
    justifications: dict[str, str] = {}
    pool_spans = [s for spans in pool.values() for s in spans]
    for d in dims:
        did = d["dimension_id"]
        scores[did] = float(structural.get(did, innovation_proxy))
        # Attach a couple of real detected spans so evidence verification passes.
        key_map = {
            "decomposition": "subproblems", "modeling_depth": "equations",
            "assumptions": "assumptions", "validation": "baseline",
            "sensitivity": "sensitivity", "results": "tables",
            "writing": "subproblems",
        }
        spans = pool.get(key_map.get(did, ""), []) or pool_spans[:1]
        evidence[did] = spans[:2]
        justifications[did] = "mock stand-in: graded from detected structural signals"
    return {"scores": scores, "evidence": evidence, "justifications": justifications}


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
    # The mock competition-writer produces the SAME clean scaffolding (D-H5: the
    # mock must not dump raw equations). The real provider does the prose.
    "competition_writer": _mock_paper_writer,
    "route_generator": _mock_route_generator,
    "assumption_agent": _mock_assumption_agent,
    "sensitivity_planner": _mock_sensitivity_planner,
    "red_team": _mock_red_team,
    "competition_judge": _mock_competition_judge,
    "generic": _mock_generic,
}
