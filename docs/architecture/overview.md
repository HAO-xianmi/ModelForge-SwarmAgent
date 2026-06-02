# Architecture Overview

ModelForge-Swarm is a **stateful engineering system**, not a chat of agents. A
state machine (the workflow driver) over a typed **Shared Blackboard**
(`ModelingState`) is the backbone; language models do only reasoning, and
deterministic services do everything that must be reproducible.

## Five layers (spec §6)

```
┌──────────────────────────────────────────────────────────────┐
│ USER INTERFACES   CLI · REST API (FastAPI) · Web console (Next)│
├──────────────────────────────────────────────────────────────┤
│ CONTROL PLANE     RunCoordinator · Workflow driver             │
│                   CheckpointManager · BudgetManager · LoopGuard│
│                   ComplianceEngine (policy)                     │
├──────────────────────────────────────────────────────────────┤
│ SHARED BLACKBOARD ModelingState (typed, versioned, audited)    │
│   ├─ REASONING AGENTS    parser, analyst, retriever,           │
│   │                      3× proposer, skeptic, judge,          │
│   │                      code author, debugger, architect,     │
│   │                      writer                                 │
│   └─ DETERMINISTIC SVCS  ingestion, profiling, method library, │
│                          sandbox, experiments, baselines,      │
│                          robustness, auditor, evidence,        │
│                          citations, compliance, report, export │
├──────────────────────────────────────────────────────────────┤
│ STORAGE / INFRA   SQLite/Postgres · object store · run dir ·   │
│                   Docker / subprocess sandbox                  │
└──────────────────────────────────────────────────────────────┘
```

## Module map (`src/modelforge/`)

| Package | Responsibility |
|---|---|
| `common/` | ids, hashing, UTC time, logging, errors, config |
| `schemas/` | all Pydantic v2 domain models + enums (the contracts) |
| `storage/` | SQLAlchemy models, repositories, **Artifact Registry**, run-state versioning, object store, run directory; Alembic migrations |
| `services/` | deterministic services (see below) |
| `providers/llm/` | `LLMProvider` Protocol + Mock/OpenAI/Anthropic + factory |
| `prompts/` | versioned prompt registry |
| `agents/` | 10 reasoning agents on a `BaseAgent` (typed I/O, bounded retry, repair-once, cost tracking) |
| `graph/` | control plane + workflow driver + `RunCoordinator` |
| `api/` | FastAPI app |
| `cli/` | Typer CLI (incl. `doctor`, `demo`) |

### Deterministic services (`services/`)

`ingestion`, `profiling`, `method_library`, `codegen` (runnable templates),
`sandbox` (Protocol + subprocess + Docker runners), `experiments` (runner,
pilots, baselines, robustness, auditor), `evidence`, `citations`, `compliance`,
`report` (builder + LaTeX), `exporters` (reproducibility bundle).

## Boundaries (spec §6.3)

- **Agent ↔ Agent** — only through the blackboard; no free-form chat.
- **Agent ↔ Tool** — minimal permissions; agents call typed service methods.
- **Writer ↔ Evidence** — the writer may only use VERIFIED claims.
- **Sandbox ↔ Host** — isolated from host secrets, host files, and the network.
- **Contest mode** — tools/checkpoints/exports governed by the active profile.

## Key invariants

- The blackboard is the single source of truth; every update is **versioned**
  and emits an **audit event** (actor, prev/new version, changed fields, reason).
- Artifacts are **immutable** and content-addressed; revisions create new ids.
- Quantitative evidence comes **only** from executed code (no fabricated metrics).
- Every loop is **bounded** (debug, model-revision, report-revision, total).
