"""Integration: every code template REALLY executes in the sandbox and produces
metrics. This is the core proof that experiment outputs come from real runs.
"""

from __future__ import annotations

import pytest

from modelforge.common.ids import new_run_id
from modelforge.schemas.enums import ProblemFamily, SandboxStatus
from modelforge.services.codegen import CodeGenerator
from modelforge.services.sandbox import SubprocessSandboxRunner
from modelforge.services.sandbox.base import SandboxRequest
from modelforge.services.sandbox.workspace import prepare_workspace

pytestmark = pytest.mark.integration

# (template, model_kind, family, expected metric key)
CASES = [
    ("prediction", "linear_regression", ProblemFamily.PREDICTION, "rmse"),
    ("prediction", "random_forest", ProblemFamily.PREDICTION, "rmse"),
    ("prediction", "gradient_boosting", ProblemFamily.PREDICTION, "rmse"),
    ("classification", "logistic_regression", ProblemFamily.CLASSIFICATION, "accuracy"),
    ("classification", "decision_tree", ProblemFamily.CLASSIFICATION, "accuracy"),
    ("clustering", "kmeans", ProblemFamily.CLUSTERING, "silhouette"),
    ("clustering", "dbscan", ProblemFamily.CLUSTERING, "n_clusters"),
    ("optimization", "integer_programming", ProblemFamily.OPTIMIZATION, "objective_value"),
    ("graph", "shortest_path", ProblemFamily.GRAPH, "n_nodes"),
    ("graph", "centrality", ProblemFamily.GRAPH, "n_nodes"),
    ("graph", "max_flow", ProblemFamily.GRAPH, "max_flow_value"),
    ("evaluation", "topsis", ProblemFamily.EVALUATION, "n_alternatives"),
    ("evaluation", "pca", ProblemFamily.EVALUATION, "explained_variance_pc1"),
    ("timeseries", "", ProblemFamily.PREDICTION, "rmse"),
    ("simulation", "", ProblemFamily.SIMULATION, "estimate_mean"),
]


@pytest.mark.parametrize("template,model_kind,family,metric", CASES)
def test_template_executes_and_produces_metric(
    tmp_path, template, model_kind, family, metric
) -> None:
    artifact = CodeGenerator().generate(
        "strategy_x", template, family, model_kind=model_kind, seed=7
    )
    prepare_workspace(tmp_path, artifact, {})
    result = SubprocessSandboxRunner().run(
        SandboxRequest(run_id=new_run_id(), workspace=tmp_path, timeout_seconds=90)
    )
    assert result.status is SandboxStatus.SUCCEEDED, (
        f"{template}/{model_kind} failed:\n{result.stderr}"
    )
    assert metric in result.metrics, (
        f"{template} missing metric '{metric}'; got {sorted(result.metrics)}"
    )
    assert result.output_files, f"{template} produced no output files"


def test_generated_project_has_spec_file_structure(tmp_path) -> None:
    artifact = CodeGenerator().generate(
        "s1", "prediction", ProblemFamily.PREDICTION, model_kind="linear_regression"
    )
    names = {f.filename for f in artifact.files}
    # spec 20.2 canonical structure
    assert {
        "main.py",
        "load_data.py",
        "preprocess.py",
        "model.py",
        "evaluate.py",
        "robustness.py",
        "visualize.py",
    } <= names
    assert artifact.content_hash
    assert "scikit-learn" in artifact.dependencies


def test_determinism_same_seed_same_metrics(tmp_path) -> None:
    """Two runs with the same seed give identical metrics (reproducibility)."""
    runner = SubprocessSandboxRunner()
    metrics = []
    for i in range(2):
        ws = tmp_path / f"run{i}"
        ws.mkdir()
        artifact = CodeGenerator().generate(
            "s1", "prediction", ProblemFamily.PREDICTION, model_kind="random_forest", seed=123
        )
        prepare_workspace(ws, artifact, {})
        res = runner.run(SandboxRequest(run_id=new_run_id(), workspace=ws, seed=123))
        assert res.status is SandboxStatus.SUCCEEDED
        metrics.append(res.metrics["rmse"])
    assert metrics[0] == pytest.approx(metrics[1])
