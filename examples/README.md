# Examples

Three deterministic, self-contained examples that run end to end with **no API
key** (mock LLM) and **no Docker** (local subprocess sandbox). Each produces real
experiment metrics and a reproducibility bundle.

| Example | Family | What it does |
|---|---|---|
| `simple_prediction/` | prediction | Regression on 3 numeric predictors; reports RMSE/MAE/R². |
| `allocation_optimization/` | optimization | 0/1 knapsack via integer programming; reports objective value. |
| `network_analysis/` | graph | Centrality / shortest path on a weighted edge list. |

Each folder contains a `problem.txt` (the statement) and a `data.csv` (the
deterministic dataset).

## Run an example

```bash
pip install -e ".[dev,science]"
python examples/run_example.py simple_prediction
python examples/run_example.py allocation_optimization
python examples/run_example.py network_analysis
```

Expected output (abridged):

```
Example: simple_prediction  ->  run run_...
Completed.
  metrics (real execution): {'rmse': 0.37..., 'mae': ..., 'r2': ..., 'synthetic_data': 0.0}
  verified claims: 4
  bundle: .../runs/run_.../exports/modelforge_run_run_....zip
```

## What gets produced

Each run creates `runs/{run_id}/` with the full audit trail and a reproducibility
ZIP under `exports/` containing:

```
report.md, report.tex, references.bib
figures/        code/        metrics/
evidence/       citations/   logs/
reproducibility_manifest.json
artifact_manifest.json
input_manifest.json
```

The metrics in the report come **only** from real sandbox execution — the
`synthetic_data: 0.0` marker confirms the model was trained on the provided
dataset, not a synthetic fallback.

## Walkthrough (simple_prediction)

1. **Ingest** — `problem.txt` + `data.csv` are hashed and stored.
2. **Parse / analyze** — the problem is classified as a `prediction` task.
3. **Strategies** — three proposers (interpretability/performance/innovation)
   each produce a runnable strategy; the skeptic critiques them.
4. **Pilots** — each strategy runs a quick real experiment.
5. **Select** — the judge picks the strategy with the best pilot evidence.
6. **Experiments** — formal run + baseline + repeated-seed robustness, all in
   the sandbox.
7. **Audit** — quality gates check train/test split, baseline, robustness, etc.
8. **Evidence** — quantitative claims are registered and verified against the
   real experiment metrics.
9. **Report** — the architect builds an outline from *verified* claims only; the
   writer drafts prose citing claim ids.
10. **Export** — markdown/LaTeX (+ PDF if a LaTeX compiler is present) and the
    reproducibility bundle.
