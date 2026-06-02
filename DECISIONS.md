# Technical Decisions

Records important decisions and deviations from the architecture spec
(working rule 3). Newest first within each phase.

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
