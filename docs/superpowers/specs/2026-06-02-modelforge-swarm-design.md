# ModelForge-Swarm — Implementation Design Spec

**Date:** 2026-06-02
**Status:** Approved, in implementation
**Source of truth:** `ModelForge-Swarm_Software_Architecture_and_Development_Specification_v1.0.txt`

## 1. Goal

A local-first, auditable, reproducible multi-agent copilot for mathematical
modeling. Parses problems, explores multiple strategies, runs **real**
reproducible experiments in a sandbox, validates evidence, and produces
evidence-grounded report drafts with human checkpoints.

## 2. Core foundation (everything else builds on these)

1. **Shared Blackboard** — `ModelingState` (typed) is the single authoritative
   run state. No parallel state systems.
2. **LangGraph workflow** — the state machine backbone. Deterministic
   Supervisor selects nodes; LLMs only reason.
3. **Artifact Registry** — immutable, hashed, content-addressed file references.
4. **Evidence Registry** — claims gated by verification status; report writer
   may only use VERIFIED (and explicitly-marked NEEDS_HUMAN_REVIEW) claims.
   Evidence-constrained from the start, not bolted on.
5. **SandboxRunner abstraction** — implemented *before* agent-driven
   experimentation so all experiment outputs come from real execution.

## 3. Environment-driven decisions

| Concern | Decision | Reason |
|---|---|---|
| Sandbox | `SandboxRunner` Protocol → `DockerSandboxRunner` (full spec impl) + `SubprocessSandboxRunner` (timeout, restricted cwd, path guard, net-disabled env, captured streams). Auto-select via doctor. | Docker absent on dev host; code must still really execute. Spec §7 fallback rule. |
| LLM | `LLMProvider` Protocol → `MockProvider` (deterministic default, no key) + `OpenAICompatibleProvider` + `AnthropicProvider`. | Spec requires no single-vendor dependency; CI/tests must run keyless. |
| DB | SQLAlchemy 2.x, SQLite default, Postgres via `DATABASE_URL`, Alembic. | Local-first; production-ready. |
| Depth | Backend engine deep + tested e2e; Next.js console lean but functional. | One session cannot take all 25 milestones to production depth. |

## 4. Hard invariants (enforced in code + tests)

- Typed input/output schemas on every agent.
- Versioned prompt per agent; prompt registry records version.
- Bounded retries on every loop (model revisions, debug, report, citation, total).
- One audit event per state change (actor, ts, prev/new version, changed fields, reason).
- Writer MUST NOT use REJECTED claims or treat PENDING quantitative claims as facts.
- No fabricated metrics: numbers in evidence come only from executed code.
- Large artifacts stored externally, referenced by `artifact_id`.
- Human edits distinguishable from machine edits.

## 5. Build phases (each verified before the next)

- **A — Foundation:** repo structure, `pyproject.toml`, configs, `common/`
  (ids, hashing, time, logging, errors, config). Lint + type + smoke.
- **B — Domain:** all Pydantic v2 schemas + enums. Validation tests.
- **C — Storage:** SQLAlchemy models, repositories, artifact registry
  (immutable revisions), run-state versioning, audit persistence, local object
  store, run-directory builder, Alembic. Tests.
- **D — Services:** ingestion, data profiler, method library (20 entries),
  sandbox (both runners), pilots, formal pipeline + bounded debug, baselines,
  robustness, experiment auditor, evidence registry, citation registry,
  compliance engine (5 profiles). Tests incl. real subprocess execution +
  security tests (path traversal, oversized upload, timeout, net deny).
- **E — Agents + LLM:** provider abstraction, prompt registry, 10 agents
  (3+ proposer instances), structured-output validation + repair-once, bounded
  retry, audit + cost tracking. Deterministic mock tests.
- **F — Workflow:** LangGraph graph with all nodes + conditional routing +
  loop protection, 3 checkpoints, report architect/writer (evidence-gated),
  markdown/LaTeX/PDF export, reproducibility ZIP bundle + manifest.
  Integration + one full e2e prediction run.
- **G — Surfaces:** FastAPI (all core endpoints), CLI (incl. `doctor`,
  `demo`), lean Next.js frontend, 3 deterministic examples, docs,
  `FINAL_VALIDATION_REPORT.md`.

## 6. Reconciliation with process

The user authorized immediate implementation without per-section approval gates.
This spec doc is written as the first artifact; implementation proceeds straight
into Phase A. Decisions surfaced only when genuinely blocked.

## 7. Anything not fully implementable here

Recorded in `IMPLEMENTATION_STATUS.md` as: Partial / Reason / Remaining work /
Next step. Known up front: Docker execution path (no Docker on host — subprocess
path used instead, Docker path implemented but unexecuted here); remote citation
APIs (network/credentials); full frontend polish.
