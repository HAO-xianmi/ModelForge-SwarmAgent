# Deployment

## Local MVP (zero external dependencies)

```bash
pip install -e ".[dev,science]"
modelforge doctor
modelforge demo
```

Uses SQLite + the subprocess sandbox + the mock LLM. Nothing else required.

## Production-like (Docker Compose)

```bash
docker compose up --build
```

Brings up:

- **db** — PostgreSQL 16
- **redis** — Redis 7 (queue abstraction; optional)
- **api** — FastAPI backend (mounts `./runs`, talks to the host Docker daemon so
  the sandbox runner can launch isolated containers)
- **sandbox-image** — one-shot build of `modelforge-sandbox:latest`

Configure via environment (see `.env.example`):

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg://…` for Postgres |
| `MODELFORGE_SANDBOX` | `docker` to force the container runner |
| `MODELFORGE_LLM` + key | `openai`/`anthropic` for real models |

Apply migrations against Postgres:

```bash
alembic upgrade head
```

## Sandbox isolation (spec §34.4)

Sandbox workers should be isolated from API/DB credentials, host filesystem, and
the internal network. The Docker runner already runs containers non-root, with
`--network none`, read-only input mounts, dropped capabilities, and CPU/memory/
pids limits. In a multi-host deployment, run sandbox workers on a separate,
credential-free pool.

## Notes

- **Docker on the dev host:** if Docker is unavailable, the runner transparently
  falls back to the local subprocess sandbox. The Docker code path is fully
  implemented but is only *exercised* where a daemon is present (tests marked
  `requires_docker`).
- **LaTeX/PDF:** install MiKTeX or TeX Live for PDF export; otherwise markdown +
  `.tex` are still produced and the PDF step is skipped gracefully.
