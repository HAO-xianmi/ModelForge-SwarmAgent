# CompetitionJudge & Benchmark Framework — Design Spec

**Date:** 2026-06-03
**Status:** Approved (brainstorm), in implementation
**Branch:** `feat/competition-judge-benchmark`
**Relates to:** `2026-06-02-modelforge-swarm-design.md` (original architecture)

## 1. Goal

Build the *measuring instrument* that must validate **before** any workflow
rebuild: a repeatable benchmark harness and a hybrid `CompetitionJudge` that
scores a modeling paper against a rubric derived from MCM/ICM, CUMCM, and APMCM
judging criteria plus award-winning-paper analysis.

The instrument is the gate. **No future architecture change is accepted unless it
raises benchmark scores across all four problem categories vs. the recorded
baseline.** This spec deliberately builds only the ruler, not the thing measured.

Success (calibration goals, in priority order):
1. Award papers consistently score **higher** than weak papers.
2. Weak papers consistently score **lower**.
3. Rankings are **stable** across repeated runs.
4. The score separates *competition-level reasoning* from *superficial report
   writing* — not merely surface structure.

## 2. Consistency with the original ModelForge-Swarm architecture (REQUIRED)

The benchmark system is an **extension** of ModelForge-Swarm, not a separate
product. Concretely:

| Original invariant (2026-06-02 spec §2/§4) | How this extension complies |
|---|---|
| Single `ModelingState` blackboard; no parallel state | CompetitionJudge writes a `CompetitionJudgeReport` into the existing `state.judge_reports` lineage; the benchmark harness is an *offline* surface that constructs `PaperDocument`s and never forks run state. |
| Artifact Registry (immutable, content-addressed) | Judge reports + benchmark results register as artifacts via the existing registry when run in-workflow; offline corpus files are read-only inputs. |
| Evidence Registry gating | The judge *reads* verified claims when scoring an in-workflow report; it never promotes unverified numbers. |
| Typed schemas on every agent | New `schemas/evaluation.py` follows `MFBaseModel` + the `JudgeReport`/`StrategyScore` pattern in `schemas/strategy.py`. |
| Versioned prompt per agent in registry | The LLM-judge persona prompt is registered in `prompts/registry.py` with a semantic version. |
| `LLMProvider` Protocol (Mock default, keyless CI) | The LLM-judge layer uses the existing provider abstraction; with the mock default it degrades deterministically so CI stays keyless. |
| Bounded retries; one audit event per state change | In-workflow scoring records an audit event; the panel uses bounded judge counts. |
| No fabricated metrics | Structural metrics are computed deterministically from paper text; LLM scores must cite verbatim evidence spans validated against the text. |

**Direct hook:** the existing `run_judge_panel` node is a stub whose comment
states *"A full multi-judge panel is a future extension"* (`graph/nodes.py`).
The CompetitionJudge **is** that promised full panel. A later spec wires it into
that node; this spec builds the reusable engine + offline benchmark harness.

## 3. Architecture & file layout

```
src/modelforge/schemas/evaluation.py        # PaperDocument, StructuralMetrics,
                                            # DimensionScore, CompetitionJudgeReport
src/modelforge/services/evaluation/
  __init__.py
  rubric.py        # 8 dimensions, weights, criteria text — single source of truth
  ingest.py        # md/tex/txt -> normalized PaperDocument (language-agnostic)
  structural.py    # deterministic scorer (pure functions; no I/O, no LLM)
  llm_judge.py     # stabilized LLM panel (temp 0, N judges, median, evidence)
  aggregate.py     # blend structural + LLM; validate evidence quotes
  judge.py         # CompetitionJudge orchestrator: PaperDocument -> report
benchmark/
  __init__.py
  datasets.py      # pluggable calibration dataset registry + loaders
  corpus/
    award/         # REAL award papers (text)   e.g. apmcm2025_a_25201880.txt
    weak/          # REAL weak generated paper  e.g. modelforge_irrigation_v0.txt
    average/       # EMPTY — "pending real samples" marker file only
    labels.json    # {file -> {tier, source, problem_slug}}
  problems/<slug>/problem.md   # 4 benchmark problem statements
  runner.py        # harness: calibrate | evaluate
  reports.py       # render CompetitionJudgeReport -> markdown/json
  results/         # written outputs (gitignored except .gitkeep)
src/modelforge/cli/benchmark_cli.py          # `modelforge benchmark ...`
tests/evaluation/                            # structural unit, separation, repeatability
```

## 4. Rubric — 8 dimensions (0–10 each)

Derived from MCM/ICM (restatement, assumptions, model justification, sensitivity,
strengths/weaknesses, summary), CUMCM (假设合理性 / 建模创造性 / 结果正确性 /
表述清晰), APMCM, and the WinningPaperKnowledgeBase.

| # | Dimension | Structural signal | LLM judges | Struct/LLM split |
|---|---|---|---|---|
| 1 | Decomposition & restatement | # subproblems addressed | restatement quality | 60/40 |
| 2 | Modeling depth & justification | equation density | rigor; method-fits-problem | 30/70 |
| 3 | Assumptions & symbol table | enumerated assumptions; symbol table present | reasonableness | 50/50 |
| 4 | Validation & correctness | baseline present; CV/test metrics present | rigor; honest test-vs-CV gap | 50/50 |
| 5 | Sensitivity & robustness | sensitivity section/table present | depth of param→outcome analysis | 40/60 |
| 6 | Innovation | (none) | named, defensible novelty | 0/100 |
| 7 | Results & evidence | figure/table counts; numbers tied to them | interpretation quality | 40/60 |
| 8 | Writing & presentation | section completeness; references count | abstract/clarity quality | 50/50 |

**Final blend:** `final = w_struct·structural + w_llm·llm` with default
`w_struct = 0.40`, `w_llm = 0.60` (meets the ≥40% deterministic / ≤60% LLM
bound). Per-dimension struct/LLM splits above; a dimension with no structural
signal (innovation) is LLM-only but still bounded by the global 0.60 cap.

## 5. Scoring mechanics

**Structural (fully reproducible).** Pure functions over the normalized
`PaperDocument`. Deterministic detectors, language-agnostic (Chinese + English,
md/tex/plain):
- subproblems: `问题[一二三四五六]`, `Q\d`, `Problem \d`, `sub_\d`, `针对问题`
- equations: `\[`, `$$`, `\begin{equation}`, `\frac`, numbered `(\d+\.\d+)`/`（\d+）`
- tables: `表\s*\d`, `Table \d`, `\begin{table}`, markdown pipe rows
- figures: `图\s*\d`, `Figure \d`, `\includegraphics`, `![`
- baseline: `baseline`, `基线`, `对比模型`, `多元线性回归`, `vs\.?`
- sensitivity: `sensitivity`, `灵敏度`, `敏感性`, `robustness`, `鲁棒性`, `扰动`
- assumptions: `assumption`, `假设[一二三四五]`, enumerated assumption lists
- symbol table: `符号说明`, `notation`, `symbol` table headers
- validation/CV: `cross-validation`, `交叉验证`, `k-fold`, `\bCV\b`, `RMSE`, `R2`/`R²`
Each signal → `[0,1]` via fixed thresholds → scaled to 0–10. **Identical input ⇒
identical score, always.** No randomness, no network, no LLM.

**LLM (stabilized).** Panel of `N` judges (default 3), `temperature=0`,
**median** aggregation. Each judge returns, per LLM dimension,
`{score: 0-10, evidence: [verbatim spans], justification}`. The aggregator
**validates every evidence span is a verbatim substring of the paper**; spans
that don't match are dropped and the dimension flagged `evidence_unverified`.
"Multiple judges" = different providers/models when keys exist, else distinct
personas on one model; with the mock default the panel is deterministic.

## 6. Calibration datasets (pluggable; real papers only)

- **No synthetic/degraded papers.** Calibration uses only real papers.
- `benchmark/datasets.py` exposes a pluggable registry: a dataset is
  `(tier, problem_slug, source, path)`. Loaders discover files under
  `corpus/<tier>/` and read `labels.json`. Adding a paper = drop a file + a
  label entry; no code change.
- Tiers: `award` (seeded: APMCM-2025-A winners), `weak` (seeded: the
  QUBO/irrigation `report.pdf` output), `average` (**EMPTY**, marker file
  `_PENDING_REAL_SAMPLES.md`). The harness skips empty tiers gracefully and the
  separation test asserts only over populated tiers, so development is **not
  blocked** on average-tier samples.

## 7. Benchmark suite & harness

Four problem categories under `benchmark/problems/`:
`irrigation` (optimization + prediction), `topsis_evaluation` (multi-criteria
evaluation), `network` (graph/flow), `forecasting` (time-series prediction).

Harness modes (CLI `modelforge benchmark`):
- `calibrate` — score every corpus paper; emit a ranking report; assert
  separation + stability. Runs now (no workflow needed).
- `evaluate <paper>` — score one paper file; emit a `CompetitionJudgeReport`.
- `baseline` (future) — record current per-category scores as the gate baseline.

Reports (`reports.py`): per-paper markdown (dimension table + evidence + final)
and machine-readable JSON for diffing old-vs-new.

## 8. Testing strategy & success gates (TDD)

Tests authored before/with implementation:
- `structural.py` unit tests: each detector on award-rich vs weak-poor fixtures.
- evidence-quote validation test (hallucinated span dropped).
- **Separation test:** over populated tiers, `min(award.final) − max(weak.final)
  ≥ 2.0` and ordering `award > weak` holds for every (paper) pair.
- **Repeatability test:** scoring the same paper twice ⇒ identical structural
  scores and identical final ranking (LLM within ε; mock exactly equal).
- CLI smoke test: `modelforge benchmark calibrate` exits 0 and prints a ranking.

## 9. Out of scope (explicit)

The workflow rebuild (decomposition loop, route tournament, domain-model KB, new
agents, writer/renderer redesign) is a **separate later spec**, gated by this
instrument. Real average-tier samples are pending; PDF→text extraction is a
documented one-time prep step, not in the scoring hot path (repeatability).
