# API Reference

The FastAPI backend serves interactive OpenAPI docs at `/docs` (Swagger UI) and
`/redoc` when running:

```bash
python -m uvicorn modelforge.api.main:app --port 8000
# http://localhost:8000/docs
```

## Endpoints (spec §26)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/api/v1/runs` | create a run |
| POST | `/api/v1/runs/{run_id}/files` | upload input files (multipart) |
| POST | `/api/v1/runs/{run_id}/start` | start/continue the workflow |
| GET | `/api/v1/runs/{run_id}` | run summary (status, budget) |
| GET | `/api/v1/runs/{run_id}/state` | full blackboard snapshot |
| GET | `/api/v1/runs/{run_id}/events` | audit events |
| GET | `/api/v1/runs/{run_id}/artifacts` | registered artifacts |
| GET | `/api/v1/runs/{run_id}/checkpoints` | pending + resolved checkpoints |
| POST | `/api/v1/runs/{run_id}/checkpoints/{cp}/resolve` | resolve a checkpoint |
| POST | `/api/v1/runs/{run_id}/cancel` | cancel a run |
| GET | `/api/v1/runs/{run_id}/exports` | export metadata |
| GET | `/api/v1/runs/{run_id}/exports/download` | download the ZIP bundle |
| GET | `/api/v1/methods` | list method library |
| GET | `/api/v1/methods/{method_id}` | one method record |
| GET | `/api/v1/profiles/{profile_id}` | one competition profile |

## Example: create → upload → start (curl)

```bash
RUN=$(curl -s -X POST localhost:8000/api/v1/runs \
  -H 'content-type: application/json' \
  -d '{"mode":"practice","competition_profile_id":"practice"}' | jq -r .run_id)

curl -s -X POST localhost:8000/api/v1/runs/$RUN/files \
  -F files=@problem.txt -F files=@data.csv

curl -s -X POST localhost:8000/api/v1/runs/$RUN/start
curl -s localhost:8000/api/v1/runs/$RUN | jq
```

Errors are returned as structured JSON (`{error, detail, failure_type, context}`).
