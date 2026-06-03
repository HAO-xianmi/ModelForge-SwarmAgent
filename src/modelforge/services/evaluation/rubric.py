"""The CompetitionJudge rubric — single source of truth for dimensions.

Derived from MCM/ICM judging (clear restatement, justified assumptions, model
construction & validity, sensitivity analysis, strengths/weaknesses, executive
summary), CUMCM criteria (假设合理性 / 建模创造性 / 结果正确性 / 表述清晰),
APMCM, and the WinningPaperKnowledgeBase extracted from award papers.

Each dimension declares:
  * ``weight``        cross-dimension weight (the list sums to 1.0)
  * ``has_structural``whether a deterministic structural score feeds it
  * ``llm``           whether an LLM judge scores it (all true here)
  * ``llm_criteria``  the criteria text shown to LLM judges

The blend is global, not per-dimension: ``final = 0.40*structural_subtotal +
0.60*llm_subtotal`` (meets the >=40% deterministic / <=60% LLM constraint). A
dimension's displayed ``final_score`` is the global-weight blend of whichever
layers are present (so an LLM-only dimension shows its LLM score).
"""

from __future__ import annotations

from modelforge.schemas.base import MFBaseModel

RUBRIC_VERSION = "1.0.0"

# Default global blend (configurable). Deterministic layer >= 40%, LLM <= 60%.
DEFAULT_W_STRUCT = 0.40
DEFAULT_W_LLM = 0.60


class RubricDimension(MFBaseModel):
    dimension_id: str
    name: str
    weight: float
    has_structural: bool
    llm: bool
    description: str
    llm_criteria: str


RUBRIC: list[RubricDimension] = [
    RubricDimension(
        dimension_id="decomposition",
        name="Problem Decomposition & Restatement",
        weight=0.12,
        has_structural=True,
        llm=True,
        description="Are the sub-problems identified and each addressed with a "
        "model? Is the problem restated in the team's own terms?",
        llm_criteria=(
            "Score 0-10 how well the paper decomposes the problem into the "
            "distinct sub-problems it actually contains and addresses EACH with "
            "its own model, with outputs of earlier parts feeding later parts. "
            "High: every sub-problem has a tailored model and they connect. "
            "Low: one generic model is stretched across an inherently multi-part "
            "problem, or sub-problems are restated but not modeled."
        ),
    ),
    RubricDimension(
        dimension_id="modeling_depth",
        name="Modeling Depth & Justification",
        weight=0.18,
        has_structural=True,
        llm=True,
        description="Mathematical rigor; method choice justified by problem "
        "structure/physics rather than picked from a generic menu.",
        llm_criteria=(
            "Score 0-10 the mathematical depth and justification. High: explicit "
            "equations, mechanistic/first-principles or well-justified models "
            "whose choice is argued from the problem's structure (e.g. physics, "
            "constraints, data). Low: a generic off-the-shelf model with no "
            "derivation or justification, or hand-waving in place of math."
        ),
    ),
    RubricDimension(
        dimension_id="assumptions",
        name="Assumptions & Symbol Definition",
        weight=0.10,
        has_structural=True,
        llm=True,
        description="Explicit, numbered, load-bearing assumptions and a symbol "
        "table defining variables with units.",
        llm_criteria=(
            "Score 0-10 the assumptions and notation. High: a short list of "
            "explicit, reasonable, load-bearing assumptions that genuinely "
            "simplify the model, plus a symbol table. Low: missing, generic "
            "('data is representative'), or unreasonable assumptions; no notation."
        ),
    ),
    RubricDimension(
        dimension_id="validation",
        name="Validation & Correctness",
        weight=0.14,
        has_structural=True,
        llm=True,
        description="Baseline comparison, cross-validation, test metrics, and "
        "physical/sanity checks; honest reporting of gaps.",
        llm_criteria=(
            "Score 0-10 the validation. High: a baseline that the proposed model "
            "visibly beats, cross-validation or held-out metrics, sanity checks, "
            "and HONEST reporting (e.g. test vs CV gap acknowledged). Low: no "
            "baseline, no out-of-sample validation, or results stated without "
            "any check."
        ),
    ),
    RubricDimension(
        dimension_id="sensitivity",
        name="Sensitivity & Robustness Analysis",
        weight=0.12,
        has_structural=True,
        llm=True,
        description="A structured parameter->outcome analysis (table or curve), "
        "not merely repeated random seeds.",
        llm_criteria=(
            "Score 0-10 the sensitivity/robustness analysis. High: a key "
            "parameter is varied and its effect on outcomes is reported as a "
            "table or curve with interpretation (e.g. reserve % vs drought "
            "probability). Low: absent, or 'we ran it a few times' with no "
            "parameter relationship."
        ),
    ),
    RubricDimension(
        dimension_id="innovation",
        name="Innovation",
        weight=0.10,
        has_structural=False,
        llm=True,
        description="A named, defensible novelty in modeling, method, or analysis.",
        llm_criteria=(
            "Score 0-10 the innovation. High: a named, defensible novelty (a new "
            "formulation, a clever hybrid, a non-obvious metric) that is actually "
            "used and justified. Low: entirely standard textbook pipeline with no "
            "original contribution, or 'novelty' that is just jargon."
        ),
    ),
    RubricDimension(
        dimension_id="results",
        name="Results & Evidence",
        weight=0.14,
        has_structural=True,
        llm=True,
        description="Quantitative results tied to figures/tables and interpreted, "
        "not just reported.",
        llm_criteria=(
            "Score 0-10 the results and evidence. High: concrete quantitative "
            "results tied to figures/tables, each interpreted in problem terms "
            "(what the number means, why it is plausible). Low: vague or absent "
            "results, numbers with no figure/table, or uninterpreted dumps. "
            "Penalize results that contradict the stated problem domain."
        ),
    ),
    RubricDimension(
        dimension_id="writing",
        name="Writing & Presentation",
        weight=0.10,
        has_structural=True,
        llm=True,
        description="Abstract quality, sectioning, clarity, and references.",
        llm_criteria=(
            "Score 0-10 the writing. High: a specific, informative abstract that "
            "states the methods and key numbers; clear per-part structure; real "
            "references; clean technical prose. Low: a generic boilerplate "
            "abstract, missing sections, leaked internal tokens, or prose that "
            "does not match the actual problem."
        ),
    ),
]


def rubric_by_id() -> dict[str, RubricDimension]:
    return {d.dimension_id: d for d in RUBRIC}


def total_weight() -> float:
    return sum(d.weight for d in RUBRIC)
