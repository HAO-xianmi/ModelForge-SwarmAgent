# Contributing

## Setup

```bash
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev,science]"
```

## Quality gates (all must pass)

```bash
make lint     # ruff (style + imports + upgrades)
make type     # mypy (strict, pydantic plugin)
make test     # pytest (unit + integration + e2e)
```

CI mirrors these. Tests run with the **mock LLM** and the **subprocess sandbox**,
so they need no API key or Docker.

## Conventions (spec Appendix G)

- Typed everywhere; agents have typed input + output schemas.
- New status values / events / artifact types go in `schemas/enums.py`.
- Deterministic work → a service (no LLM); reasoning → an agent.
- Every loop is bounded; every state change emits an audit event.
- No fabricated metrics — experiment numbers come only from executed code.
- Prompts are versioned in `prompts/registry.py`.

## Adding a problem family

1. Add a runnable template in `services/codegen/templates_*.py` and wire it in
   `services/codegen/generator.py`.
2. Map the family in the method library (`services/method_library/records.py`),
   baselines, robustness metric, and the auditor's primary-metric map.
3. Teach the mock provider's family detection/method selection (so keyless tests
   route correctly).
4. Add an integration test that executes the template in the sandbox.

## Where things live

See [docs/architecture/overview.md](../architecture/overview.md).
