# Workflow Rebuild — Decomposition-First Engine (Design Spec)

**Date:** 2026-06-03
**Status:** Approved (incremental, benchmark-gated), in implementation
**Branch:** `feat/competition-judge-benchmark`
**Gated by:** `2026-06-03-competition-judge-benchmark-design.md` (the instrument)
**Extends:** `2026-06-02-modelforge-swarm-design.md` (original architecture)

## 1. Why

ModelForge-Swarm collapses every problem to one strategy → one toy template →
one report. Root causes (Phase 1): no decomposition, no domain models, prompt
few-shot contamination (qboost/QUBO baked into contracts), 3-template ceiling,
claim-concatenating writer, renderer that cannot emit equations/tables.

**Key lever already present:** `problem_card.subproblems` is produced by the
parser but **ignored** by every node after `select_strategy`. The rebuild threads
it through, reusing the existing per-strategy machinery as the per-subproblem
unit.

## 2. Gate rule (non-negotiable)

No slice merges unless it **raises the CompetitionJudge score** of the generated
irrigation paper vs. the recorded baseline (weak corpus paper = 1.12), and does
not regress the other three categories once they have generated outputs. Each
slice ends with: run workflow → score with `modelforge benchmark evaluate` →
record delta.

## 3. Target architecture (full rebuild, delivered in slices)

**State (`schemas/state.py`):** add
`subproblem_solutions: list[SubproblemSolution]`. Each `SubproblemSolution`
carries: `sub_id`, route-tournament result, selected route, experiment record(s),
verified claims, and a model write-up. Existing single-strategy fields become the
per-subproblem unit.

**Graph (`graph/nodes.py`, `workflow.py`):**
- `decompose` — promote `problem_card.subproblems` into a solved plan with a
  data-flow DAG (Q1→Q2→Q3→Q4) and a per-subproblem family hint.
- per-subproblem loop: `route_tournament` (≥5 distinct routes, scored, pilot-
  gated) → `select_route` → reuse `generate_code`/`run_sandbox`/`run_baselines`/
  `register_evidence`, parameterized by sub_id.
- `integrate` — pass earlier outputs as inputs/constraints to later subproblems.
- `run_judge_panel` — replace the stub with the real `CompetitionJudge` panel +
  a `RedTeamAgent` gate (severity ≥ MAJOR blocks export until resolved/waived).

**Agents (`agents/`):** `DecomposeAgent`, `RouteGeneratorAgent` (≥5 routes with
strengths/weaknesses/risk/expected-score), `AssumptionEngineerAgent` (numbered
assumptions + symbol table), `SensitivityPlannerAgent` (designs the
param→outcome experiment), `RedTeamAgent`, and a competition-grade writer that
produces mathematical exposition (numbers still gated by verified claims).

**Method library (`services/method_library/`):** add domain/mechanistic models:
FAO Penman-Monteith, soil-water balance, MPC / rolling-horizon, spatial coverage
/ geometric packing, Markov-chain scenario generation, multi-stage stochastic DP,
compartmental ODEs. Agents retrieve from this KB instead of free-recalling.

**Renderer (`services/report/`):** equation + table-capable markdown→LaTeX;
per-subproblem 模型建立与求解 structure; symbol table; assumptions; sensitivity
section; honest limitations; render footnote citations (never leak `claim_xxx`).

**Prompts (`prompts/registry.py`):** remove qboost/QUBO/AdaBoost few-shot from
all contracts; make examples domain-neutral and schema-only.

## 4. Slices (each independently measurable)

**Slice 1 — stop the catastrophe + structured multi-part output.**
- De-contaminate prompt contracts (remove qboost/QUBO/AdaBoost few-shot).
- Thread `subproblems` through to the writer; produce a per-subproblem structured
  report with assumptions, symbol table, and a sensitivity section.
- Equation/table-capable renderer; no leaked claim tokens.
- **Target:** generated irrigation paper score >> 1.12 (weak baseline); structural
  layer detects subproblems/equations/tables/assumptions/sensitivity.

**Slice 2 — route tournament + domain-model KB.**
- `RouteGeneratorAgent` (≥5 routes) + tournament selection (pilot-gated).
- Seed domain/mechanistic models into the library; retrieval grounds on them.
- **Target:** modeling-depth + innovation dimensions rise; routes are distinct.

**Slice 3 — competition agents + red team + per-subproblem experiments.**
- AssumptionEngineer, SensitivityPlanner, RedTeam; per-subproblem sandbox runs.
- Wire CompetitionJudge into `run_judge_panel`.
- **Target:** validation + sensitivity dimensions rise; red team blocks weak
  outputs; approach award range on multiple categories.

## 5. Consistency with original architecture

Preserves: single `ModelingState` blackboard, Artifact/Evidence registries, typed
agents, versioned prompts, bounded retries, Mock-default keyless CI, "no
fabricated metrics" (numbers still flow only from verified claims). The
per-subproblem loop is sequential on the single blackboard (no parallel state).
CompetitionJudge fills the `run_judge_panel` "future extension" hook.

## 6. Out of scope

Frontend changes; multi-objective Pareto routing; non-irrigation data pipelines
beyond what the four benchmark problems need.
