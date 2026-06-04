# Technical Decisions

Records important decisions and deviations from the architecture spec
(working rule 3). Newest first within each phase.

---

## Phase H — Quality rebuild (benchmark-gated)

### D-H8: Domain-specific experiments produce real numbers (Slice 5)
**Decision:** Each benchmark category runs a real, deterministic domain
experiment (`benchmark/experiments.py`) — GBDT forecasting vs a seasonal-naive
baseline; FAO-56 Penman-Monteith + soil-water balance + coverage layout;
min-cost-flow + betweenness resilience; entropy-TOPSIS + weight-sensitivity. The
harness converts the computed metrics into VERIFIED, artifact-linked
EvidenceClaims; the writer cites only those. Inputs are synthesized
deterministically (reproducible under a seed); the numbers are genuinely
computed, never seeded.
**Why:** Structurally strong reports still scored 5.85 because numbers were
placeholders. Award-level requires real, specific, validated results. This closes
the report↔experiment traceability gap (every number → metrics.json + figure)
while preserving reproducibility and auditability. Gate: measured against the
5.85 real-judge baseline.

### D-H7: Wire the rebuilt components into the live workflow, mock-safe
**Decision:** `write_report` now uses CompetitionWriterAgent + per-sub-problem
domain-model matching; `run_judge_panel` runs the RedTeam adversarial gate
(advisory in-workflow). Because the mock CompetitionWriter dispatches to the same
clean scaffolding as the mock PaperWriter, the 44 integration/e2e tests are
unchanged — the upgrade only manifests with a real provider.
**Why:** Slices 1-3 proved the rebuilt report path on the benchmark harness;
Slice 4 makes real `modelforge` runs actually produce those domain-grounded,
red-teamed reports. Keeping the swap mock-identical avoids e2e regression while
delivering the live improvement. A future slice can hard-gate export on a RedTeam
BLOCKER and wire CompetitionJudge into the panel with stored state fields.

### D-H6: Sub-problem-aware content matching is keyword-dominant, decoupled from the tournament
**Decision:** Each report section's CONTENT domain model is chosen by keyword-
dominant retrieval on that SUB-PROBLEM's statement (family overlap down-weighted
to 0.3, keyword surface up to 0.7), independent of the route tournament (which
still selects the modeling APPROACH + audit trail). The CompetitionWriterAgent
(real provider) weaves the matched model's governing equations into a derivation;
the mock writer stays clean scaffolding.
**Why:** The whole-problem family is coarse and often mis-detected, so a family-
matched-but-irrelevant model beat keyword-matched correct ones (penman-monteith
got injected into network/layout/drought sections). Keyword-on-statement fixes
per-section matching. Real-judge validation: irrigation 5.55 → 6.55 (+1.00),
content layer 3.82 → 4.86. Confirms D-H5's plan (KB content lands in the real
writer) works.

### D-H1: A CompetitionJudge benchmark is the acceptance gate
**Decision:** Before rebuilding the workflow, build a hybrid paper-level judge
+ benchmark harness. No workflow change is accepted unless it raises benchmark
scores; nothing is claimed improved without a benchmark number.
**Why:** The MVP shipped structurally weak papers (an irrigation problem came
out as a "QUBO / variational quantum" report). A measuring instrument must exist
and be validated (award >> weak, stable) before optimizing against it.

### D-H2: Hybrid scoring — deterministic ≥40% + stabilized LLM ≤60%
**Decision:** `final = 0.40·structural + 0.60·llm`. Structural layer is pure
deterministic detectors (reproducible, hard to fake); LLM layer uses temp 0, a
3-persona panel, median aggregation, and verbatim evidence verification. Default
provider is mock (deterministic, keyless); a real provider is opt-in.
**Why:** Repeatability was a hard requirement. The deterministic backbone
guarantees bit-identical scores and carries separation even when the LLM layer
is a keyless stand-in; the LLM layer adds reasoning-grade judgment with real
providers.

### D-H3: Calibration on real papers only — no synthetic/degraded papers
**Decision:** The corpus holds only real papers (2 award + 1 weak). The
`average` tier is left empty and marked "pending real samples"; datasets are
pluggable (drop a file + a label entry). Development does not block on it.
**Why:** Synthetic/degraded papers would bias calibration toward our own
assumptions about what "average" looks like.

### D-H4: Incremental, decomposition-first rebuild; instrument fixes allowed when corpus-neutral
**Decision:** Rebuild in benchmark-gated slices (1a de-contaminate prompts, 1b
per-subproblem outline, 1c renderer/content, …). A structural-detector fix is
allowed mid-rebuild ONLY if it leaves the labeled corpus scores unchanged (e.g.
counting distinct sub-problem identifiers fixed English undercounting while
award/weak stayed at 9.03/9.59 vs 1.12).
**Why:** Incremental slices give a measured delta per step and keep regressions
attributable; corpus-neutral instrument fixes keep old-vs-new comparisons valid.

### D-H5: The mock writer is the content ceiling — KB content needs a real writer
**Decision:** The deterministic mock writer produces clean structural scaffolding
ONLY. KB domain equations are NOT injected into the mock writer; they are consumed
by the real CompetitionWriterAgent (Slice 3) and validated with the real judge.
Content-quality slices are benchmarked with real-provider runs at milestone
boundaries.
**Why:** Real-judge measurement (2026-06-03) showed injecting raw KB equations
into the mock writer REGRESSES the score (incoherent equation-dumping; the same
non-sub-problem-aware model injected into every section). Slice 2's value (route
diversity + domain grounding) is content, which a templated mock writer cannot
express and a structural-only mock judge cannot reward. So Slice 2 ships as tested
*infrastructure* (KB, RouteGenerator, tournament + audit); the real writer turns
it into competition prose. Gate stays green: the mock generate-harness baseline is
not regressed.

---

## Phase F — Workflow

### D-F1: Explicit checkpoint-aware driver, LangGraph for topology
**Decision:** The workflow executes via an explicit `Workflow.run/step` driver
(not `graph.invoke`); `build_langgraph` builds a `StateGraph` for topology
documentation/visualization only.
**Why:** The three human checkpoints must pause execution and resume across
process boundaries (a request creates a run, a later request resolves a
checkpoint). LangGraph's single `invoke` cannot cleanly pause/resume mid-graph
with our DB-persisted blackboard, so the driver owns stepping + persistence +
audit per node, and LangGraph documents the spec's Appendix-B topology.

### D-F2: Optional checkpoints auto-pass in practice mode
**Decision:** When the active competition profile does not require a checkpoint,
the driver auto-advances past it (recorded in audit) instead of pausing.
**Why:** Spec 25 makes checkpoints mandatory only under contest-compliant
profiles; practice mode permits full automation (spec 5.1). A real bug here
(driver returned on auto-pass and never set status past PARSING / never reached
EXPORTING) was caught by the e2e test and fixed.

### D-F3: PEP 695 reverted for mypy 1.11 compatibility
**Decision:** Use classic `TypeVar`/`Generic` instead of `class Foo[T]`.
**Why:** mypy 1.11 does not fully support PEP 695 generic classes (reports
"expects no type arguments"). Ruff `UP046/UP047` suppressed in pyproject.

---

## Phase D — Services

### D-D1: Code templates use sentinel tokens, not str.format
**Decision:** Runnable code templates carry literal Python (f-strings, dict
literals) and substitute parameters via `str.replace("__MODEL_KIND__", ...)`.
**Why:** `str.format()` collides with the `{...}` braces pervasive in real
Python code. A first attempt double-escaped braces and was fragile; sentinel
replacement is robust and keeps templates readable as actual Python.

### D-D2: Subprocess sandbox uses `-E -B`, not full `-I`; import allowlist is the boundary
**Decision:** The subprocess runner launches `python -E -B`, not `python -I`.
**Why:** `-I` (and APPDATA scrubbing) dropped the user site-packages where one
allowlisted dependency (pulp) lives on this host, breaking real execution. The
*static import allowlist* is the actual control over which modules sandbox code
may use; `-E` still ignores PYTHON* host vars. `APPDATA`/`LOCALAPPDATA` are kept
so user-site resolves; `MPLCONFIGDIR`/`HOME` are redirected into the workspace
so matplotlib has a writable config dir without touching the host home.
Documented as a known limitation: the subprocess sandbox is weaker than the
Docker runner, which remains preferred when available.

### D-D3: Synthetic-data fallback in templates, clearly labeled
**Decision:** When no dataset is present, templates generate a small synthetic
dataset and set `synthetic_data: 1` in metrics + print `synthetic=True`.
**Why:** A pilot must establish feasibility even before a dataset is attached.
The metrics never *hide* that the data was synthetic, so a synthetic result is
never mistaken for a result on the user's data (working rule 5).

---

## Phase C — Storage

### D-C1: Artifact-id-scoped storage paths (immutability fix)
**Decision:** On-disk artifact paths are `{subdir}/{id_suffix}__{filename}`, not
`{subdir}/{filename}`.
**Why:** A test revealed that revising an artifact reusing the same human
filename overwrote the original file's bytes — the DB row was immutable but the
*bytes* were not, violating spec 11.4. Scoping the path by artifact id makes
every artifact's bytes immutable while keeping a readable `filename` in the
record. Consumers always read through the registry (`storage_uri`), so the
internal name is invisible.

### D-C2: Blackboard state stored as JSON version rows
**Decision:** `ModelingState` is persisted as full JSON snapshots in
`run_state_versions`, one immutable numbered row per update, rather than
normalized columns.
**Why:** The blackboard is the single source of truth and evolves quickly; full
snapshots give trivial point-in-time recovery (spec 32.4 resume) and an exact
audit trail, at the cost of storage we accept for a local-first tool. Changed
fields are diffed for the audit event.

### D-C3: `create_all` for local, Alembic for prod
**Decision:** Tests and the zero-config path use `Base.metadata.create_all`;
`alembic upgrade head` is the production path. Both target the same metadata.
**Why:** Keeps the MVP runnable with no migration step while still shipping real
migrations (acceptance criteria + spec 27).

---

## Phase A — Foundation

### D-A1: `StrEnum` for all string enums
**Decision:** Use `enum.StrEnum` (Python 3.11+) rather than `class X(str, Enum)`.
**Why:** Ruff `UP042` flags the older idiom; `StrEnum` serializes cleanly under
Pydantic v2 and reads better. Project targets 3.12 so it is always available.

### D-A2: pydantic-settings for layered config
**Decision:** `Settings(BaseSettings)` with `MODELFORGE_` env prefix; secrets
(`OPENAI_API_KEY`, `DATABASE_URL`, etc.) use their conventional env names via
field aliases.
**Why:** Spec 36.1 mandates layered config (defaults → file → profile → run →
override). pydantic-settings gives typed defaults + `.env` loading for the two
lowest layers; profile/run/override layers are applied by the control plane.

### D-A3: SQLite default, Postgres opt-in (confirmed with user)
**Decision:** `DATABASE_URL` defaults to `sqlite:///./modelforge.db`.
**Why:** Local-first (working rule 4). Postgres requires a running server;
SQLite needs nothing. SQLAlchemy 2.x keeps both paths identical.

### D-A4: Mock LLM provider is the default (confirmed with user)
**Decision:** `MODELFORGE_LLM=mock` by default; OpenAI/Anthropic adapters
opt-in via env. Mock is deterministic and keyless.
**Why:** Spec forbids single-vendor dependency and requires keyless CI. Mock
produces schema-valid, problem-aware *reasoning* text — it never fabricates
experiment metrics (those come only from executed code, working rule 5).

### D-A5: Two sandbox runners behind one interface (confirmed with user)
**Decision:** `SandboxRunner` Protocol with `DockerSandboxRunner` (full spec
§20 implementation) and `SubprocessSandboxRunner` (timeout, restricted cwd,
path-traversal guard, network-disabled env, captured streams). Auto-select.
**Why:** No Docker on the dev host, but code must *really* execute (rule 5).
Spec §7 explicitly allows a local fallback when a dependency is unavailable.
**Deviation:** Docker path is implemented but unexecuted in this environment —
marked 🚫 in IMPLEMENTATION_STATUS until a Docker host runs `requires_docker`
tests.

### D-A6: `src/` layout, package name `modelforge`
**Decision:** Code lives under `src/modelforge/...`; the public import root is
`modelforge` (the spec's repo tree uses bare `src/` packages).
**Why:** `src/` layout prevents accidental imports of the un-installed tree and
is the modern packaging default. Mapped via `[tool.setuptools.packages.find]`.
