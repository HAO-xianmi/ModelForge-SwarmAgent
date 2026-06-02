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

## Core guarantees

- **Evidence-constrained reports** — the writer may only use *verified* claims;
  rejected/pending claims cannot become factual statements.
- **Real experiments only** — every quantitative result comes from executed
  code in the sandbox; no fabricated metrics.
- **Bounded autonomy** — every loop has a retry cap, timeout, and escalation.
- **Full audit trail** — every state change emits an event with actor,
  timestamp, version delta, and reason.
- **Human checkpoints** — problem understanding, strategy selection, final draft.

## Development

```bash
make lint     # ruff
make type     # mypy (strict)
make test     # pytest
```

## License

Apache-2.0 — see [LICENSE](LICENSE).
