"""Assemble a runnable CodeArtifact from a template + parameters.

The generated project follows spec 20.2 structure (load_data, preprocess, model,
evaluate, robustness, visualize, main). The executable logic lives in ``main.py``
(prepended with the deterministic common header); the other modules are real,
import-clean companion files documenting each stage and exposing the seed —
this keeps the canonical layout without duplicating logic across files.
"""

from __future__ import annotations

from modelforge.common.hashing import hash_text
from modelforge.common.ids import new_id
from modelforge.schemas.enums import ProblemFamily
from modelforge.schemas.experiment import CodeArtifact, CodeFile
from modelforge.services.codegen.common import COMMON_HEADER
from modelforge.services.codegen.templates_other import (
    CLASSIFICATION_MAIN,
    CLUSTERING_MAIN,
    EVALUATION_MAIN,
    GRAPH_MAIN,
    OPTIMIZATION_MAIN,
)
from modelforge.services.codegen.templates_prediction import PREDICTION_MAIN
from modelforge.services.codegen.templates_ts_sim import SIMULATION_MAIN, TIMESERIES_MAIN

# Required dependencies per template (recorded in the dependency lock).
_DEPS = {
    "prediction": ["numpy", "pandas", "scikit-learn", "matplotlib"],
    "classification": ["numpy", "pandas", "scikit-learn", "matplotlib"],
    "clustering": ["numpy", "pandas", "scikit-learn", "matplotlib"],
    "optimization": ["numpy", "pandas", "pulp", "matplotlib"],
    "graph": ["numpy", "pandas", "networkx", "matplotlib"],
    "evaluation": ["numpy", "pandas", "scikit-learn", "matplotlib"],
    "timeseries": ["numpy", "pandas", "scikit-learn", "statsmodels", "matplotlib"],
    "simulation": ["numpy", "matplotlib"],
}

_COMPANION_MODULES = {
    "load_data.py": "Data loading stage. The runnable logic lives in main.py "
    "(load_dataset/load_problem/load_graph helpers).",
    "preprocess.py": "Preprocessing stage: imputation, scaling, train/test split "
    "(performed inside main.py to keep a single deterministic flow).",
    "model.py": "Model construction stage (build_model in main.py).",
    "evaluate.py": "Evaluation stage: metrics written to ../output/metrics.json.",
    "robustness.py": "Robustness hooks; the RobustnessRunner re-invokes main.py "
    "with perturbed seeds/parameters.",
    "visualize.py": "Visualization stage: figures saved under ../output.",
}


class CodeGenerator:
    def generate(
        self,
        strategy_id: str,
        template: str,
        problem_family: ProblemFamily,
        *,
        model_kind: str = "",
        seed: int = 42,
    ) -> CodeArtifact:
        main_body = self._render_main(template, problem_family, model_kind)
        main_content = COMMON_HEADER + "\n" + main_body
        files = [CodeFile(filename="main.py", content=main_content, role="entrypoint")]
        for name, doc in _COMPANION_MODULES.items():
            companion = (
                f'"""{doc}"""\n\n'
                "SEED = 42  # see main.py for the authoritative seed handling\n"
            )
            files.append(CodeFile(filename=name, content=companion, role="companion"))
        deps = _DEPS.get(template, _DEPS["prediction"])
        artifact = CodeArtifact(
            code_artifact_id=new_id("code"),
            strategy_id=strategy_id,
            files=files,
            dependencies=deps,
            entrypoint="main.py",
            seed=seed,
            notes=f"template={template} family={problem_family.value} model={model_kind}",
        )
        artifact.content_hash = hash_text(main_content)
        return artifact

    def _render_main(
        self, template: str, family: ProblemFamily, model_kind: str
    ) -> str:
        # Templates use literal sentinel tokens (no str.format) so the embedded
        # Python f-strings and dict literals are left untouched.
        if template == "prediction":
            kind = model_kind or "linear_regression"
            return PREDICTION_MAIN.replace("__MODEL_KIND__", kind)
        if template == "classification":
            kind = model_kind or "logistic_regression"
            return CLASSIFICATION_MAIN.replace("__MODEL_KIND__", kind)
        if template == "clustering":
            kind = model_kind or "kmeans"
            return CLUSTERING_MAIN.replace("__MODEL_KIND__", kind)
        if template == "optimization":
            return OPTIMIZATION_MAIN
        if template == "graph":
            return GRAPH_MAIN.replace("__ANALYSIS__", _graph_analysis(model_kind))
        if template == "evaluation":
            method = model_kind or "topsis"
            return EVALUATION_MAIN.replace("__METHOD__", method)
        if template == "timeseries":
            return TIMESERIES_MAIN
        if template == "simulation":
            return SIMULATION_MAIN
        # Default to prediction so generation never fails outright.
        return PREDICTION_MAIN.replace("__MODEL_KIND__", "linear_regression")


def _graph_analysis(model_kind: str) -> str:
    mk = model_kind.lower()
    if "flow" in mk:
        return "max_flow"
    if "central" in mk:
        return "centrality"
    return "shortest_path"
