# ModelForge-Swarm

**An auditable multi-agent copilot for mathematical modeling.**

> From problem statement to reproducible modeling workflow.

ModelForge-Swarm parses a modeling problem, explores multiple strategies, runs
**real** reproducible experiments in a sandbox, validates evidence, and
generates evidence-grounded report drafts — with human approval checkpoints and
a full audit trail.

It is a **stateful engineering system**, not a chat of agents: a state machine
(LangGraph) + a typed shared blackboard form the backbone; language models are
used only for reasoning, and deterministic services do everything that must be
reproducible.

> **Positioning:** a modeling *copilot*, training platform, and research
> prototype. It is **not** an autonomous contest-submission engine and does not
> bypass competition rules. The human remains responsible for final decisions.

---

## Status

This repository is built in phases. See **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)**
for exactly what is complete, partial, or pending, and **[DECISIONS.md](DECISIONS.md)**
for design decisions and deviations.

## Quick start (zero external dependencies)

The MVP runs with **no Docker, no Postgres, no API key**: SQLite + a
subprocess sandbox + a deterministic mock LLM.

```bash
# 1. Create/activate a Python 3.12+ environment, then:
pip install -e ".[dev,science]"

# 2. Check your environment:
python -m modelforge.cli.main doctor

# 3. Run a built-in example end to end:
python -m modelforge.cli.main demo
```

### Enabling real services (optional)

| Capability | How to enable |
|---|---|
| Real LLM | `MODELFORGE_LLM=openai` + `OPENAI_API_KEY`, or `MODELFORGE_LLM=anthropic` + `ANTHROPIC_API_KEY` |
| Docker sandbox | install Docker, `MODELFORGE_SANDBOX=docker` |
| PostgreSQL | `DATABASE_URL=postgresql+psycopg://...` |
| PDF export | install a LaTeX compiler (MiKTeX / TeX Live) |

Copy `.env.example` to `.env` and edit.

## Architecture (five layers)

```
User Interfaces  ── CLI · REST API · Web console
Control Plane    ── Supervisor · LangGraph workflow · Checkpoints · Budgets · Policy
Shared Blackboard── ModelingState (typed authoritative run state)
   ├─ Reasoning Agents      (parse, analyze, retrieve, propose, critique, judge, code, debug, write)
   └─ Deterministic Services(ingest, profile, sandbox, experiments, evidence, citations, compliance, export)
Storage / Infra  ── SQLite/Postgres · object store · run directory · Docker/subprocess sandbox
```

## Workflow

```
ingest → parse → analyze ─┤Checkpoint 1├→ retrieve methods → generate 3 strategies
   → skeptic → pilots → select ─┤Checkpoint 2├→ profile → generate code → run sandbox
        ↘ debug (bounded) ↙
   → baselines → robustness → audit ──(blocking?)──▶ revise code / revise strategy
   → register evidence → architect report → write report → verify citations
   → judge panel ─┤Checkpoint 3├→ build LaTeX → export PDF → export bundle → COMPLETED
```

Full node/transition detail is in [docs/architecture/workflow.md](docs/architecture/workflow.md).

## Core guarantees

- **Evidence-constrained reports** — the writer may only use *verified* claims;
  rejected/pending claims cannot become factual statements.
- **Real experiments only** — every quantitative result comes from executed
  code in the sandbox; no fabricated metrics.
- **Bounded autonomy** — every loop has a retry cap, timeout, and escalation.
- **Full audit trail** — every state change emits an event with actor,
  timestamp, version delta, and reason.
- **Human checkpoints** — problem understanding, strategy selection, final draft.

## Using it

### CLI

```bash
modelforge doctor                              # environment diagnostics
modelforge demo                                # built-in example, end to end
modelforge init                                # create db + runs dir
modelforge create-run --profile practice       # prints a run id
modelforge upload <run_id> problem.txt data.csv
modelforge start <run_id>                       # runs to a checkpoint or completion
modelforge status <run_id>                      # stage, budget, counts
modelforge checkpoints <run_id>                 # pending checkpoint + history
modelforge resolve-checkpoint <run_id> <cp_id> APPROVE
modelforge artifacts <run_id>                   # registered artifacts
modelforge export <run_id> --out bundle.zip     # copy the reproducibility bundle
```

(If not installed as a script, prefix with `python -m modelforge.cli.main`.)

### REST API

```bash
python -m uvicorn modelforge.api.main:app --port 8000
# OpenAPI docs at http://localhost:8000/docs
```

Core endpoints (spec §26): `POST /api/v1/runs`, `POST /runs/{id}/files`,
`POST /runs/{id}/start`, `GET /runs/{id}`, `/state`, `/events`, `/artifacts`,
`/checkpoints`, `POST /checkpoints/{cp}/resolve`, `POST /cancel`, `/exports`,
`GET /exports/download`, plus `/methods` and `/profiles/{id}`.

### Web console

```bash
# backend (port 8000) must be running, then:
cd apps/web && npm install && npm run dev   # http://localhost:3000
```

See [apps/web/README.md](apps/web/README.md).

### Examples

```bash
python examples/run_example.py simple_prediction
python examples/run_example.py allocation_optimization
python examples/run_example.py network_analysis
```

See [examples/README.md](examples/README.md).

### Exports

Each completed run writes `runs/{run_id}/exports/modelforge_run_{run_id}.zip`
containing `report.md`, `report.tex` (+ `report.pdf` if a LaTeX compiler is
present), `references.bib`, `figures/`, `code/`, `metrics/`, `evidence/`,
`citations/`, `logs/`, and the `*_manifest.json` files.

## Adding API keys

Copy `.env.example` to `.env` and set the provider:

```ini
MODELFORGE_LLM=openai            # or anthropic
OPENAI_API_KEY=sk-...            # or ANTHROPIC_API_KEY=sk-ant-...
```

Without a key the deterministic mock provider is used (default).

## Local development

```bash
pip install -e ".[dev,science]"
make lint     # ruff
make type     # mypy (strict)
make test     # pytest (unit + integration + e2e; real sandbox execution)
make api      # run the FastAPI backend
make web      # run the Next.js console
```

## Docker-based deployment (production-like)

```bash
docker compose up --build           # Postgres + Redis + API + sandbox image
```

The sandbox runner auto-selects Docker when a daemon is reachable
(`MODELFORGE_SANDBOX=docker` to force it), otherwise the local subprocess
runner. See [docs/deployment/](docs/deployment/).

## Documentation

- [docs/architecture/](docs/architecture/) — architecture + workflow
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) — what's complete/partial/pending
- [DECISIONS.md](DECISIONS.md) — design decisions & deviations
- [FINAL_VALIDATION_REPORT.md](FINAL_VALIDATION_REPORT.md) — validation results

## License

Apache-2.0 — see [LICENSE](LICENSE).
