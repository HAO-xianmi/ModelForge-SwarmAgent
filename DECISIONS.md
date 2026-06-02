# Technical Decisions

Records important decisions and deviations from the architecture spec
(working rule 3). Newest first within each phase.

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
