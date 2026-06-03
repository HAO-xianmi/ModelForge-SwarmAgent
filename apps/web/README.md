# ModelForge-Swarm Web Console

A lean Next.js (App Router + TypeScript + Tailwind + TanStack Query) console for
the ModelForge-Swarm API.

## Pages

- **/** — New Run: pick mode + competition profile, upload files, start.
- **/runs/[runId]** — Run Dashboard: an interactive **React Flow workflow graph**
  (done/current/pending nodes, debug + audit revise loops), human checkpoint
  resolution, live metrics (tokens/cost/runtime/strategies/experiments/verified
  claims), and tabs for overview, strategies (with pilot metrics), evidence,
  artifacts, and audit events. Polls every 2.5s.
- **/runs/[runId]/evidence** — Evidence Explorer: search/filter claims and inspect
  full provenance (experiment id, metric values, linked artifacts, citations).
- **/benchmarks** — Runs dashboard: all runs with status + progress bars and an
  aggregate completion-rate summary.
- **/methods** — the registered method library.

## Run it

The console proxies `/api/v1/*` to the FastAPI backend (default
`http://localhost:8000`, override with `NEXT_PUBLIC_API_BASE`).

```bash
# 1. Start the backend (from repo root):
python -m uvicorn modelforge.api.main:app --port 8000

# 2. Start the console:
cd apps/web
npm install
npm run dev      # http://localhost:3000
```

## Scope

This is a functional console, not a polished product. It demonstrates the full
run lifecycle against the real API, including the React Flow workflow graph,
Evidence Explorer, and Runs/Benchmark dashboard. A Monaco-based code/report
viewer remains noted as future work in the root `IMPLEMENTATION_STATUS.md`.
