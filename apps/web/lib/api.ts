// Typed client for the ModelForge-Swarm API. Requests are proxied to the
// FastAPI backend via next.config rewrites (/api/v1/* -> backend).

export interface RunSummary {
  run_id: string;
  mode: string;
  status: string;
  competition_profile_id: string | null;
  current_state_version: number;
  total_cost_estimate: number;
  total_runtime_seconds: number;
}

export interface Checkpoint {
  checkpoint_id: string;
  kind: string;
  status: string;
  context: Record<string, unknown>;
}

export interface Artifact {
  artifact_id: string;
  artifact_type: string;
  filename: string;
  size_bytes: number;
}

export interface AuditEvent {
  event_id: string;
  event_type: string;
  actor_id: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createRun: (profile: string, mode: string) =>
    req<{ run_id: string; status: string }>("/api/v1/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ mode, competition_profile_id: profile }),
    }),

  uploadFiles: (runId: string, files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return req<{ run_id: string; files: string[] }>(
      `/api/v1/runs/${runId}/files`,
      { method: "POST", body: fd },
    );
  },

  start: (runId: string) =>
    req<RunSummary>(`/api/v1/runs/${runId}/start`, { method: "POST" }),

  getRun: (runId: string) => req<RunSummary>(`/api/v1/runs/${runId}`),

  getState: (runId: string) =>
    req<Record<string, unknown>>(`/api/v1/runs/${runId}/state`),

  getEvents: (runId: string) =>
    req<AuditEvent[]>(`/api/v1/runs/${runId}/events`),

  getArtifacts: (runId: string) =>
    req<Artifact[]>(`/api/v1/runs/${runId}/artifacts`),

  getCheckpoints: (runId: string) =>
    req<{ pending: Checkpoint | null; resolved: unknown[] }>(
      `/api/v1/runs/${runId}/checkpoints`,
    ),

  resolveCheckpoint: (runId: string, checkpointId: string, action: string) =>
    req<RunSummary>(
      `/api/v1/runs/${runId}/checkpoints/${checkpointId}/resolve`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action }),
      },
    ),

  cancel: (runId: string) =>
    req<RunSummary>(`/api/v1/runs/${runId}/cancel`, { method: "POST" }),

  exports: (runId: string) =>
    req<{ bundle_path: string | null; exported_at: string | null }>(
      `/api/v1/runs/${runId}/exports`,
    ),

  downloadUrl: (runId: string) => `/api/v1/runs/${runId}/exports/download`,
};

// The spec workflow stages, used to render a progress graph.
export const WORKFLOW_STAGES = [
  "CREATED",
  "PARSING",
  "WAITING_FOR_CHECKPOINT_1",
  "RETRIEVING_METHODS",
  "GENERATING_STRATEGIES",
  "CRITIQUING_STRATEGIES",
  "RUNNING_PILOTS",
  "SELECTING_STRATEGY",
  "WAITING_FOR_CHECKPOINT_2",
  "PROFILING_DATA",
  "GENERATING_CODE",
  "RUNNING_SANDBOX",
  "RUNNING_BASELINES",
  "RUNNING_ROBUSTNESS_TESTS",
  "AUDITING_EXPERIMENTS",
  "REGISTERING_EVIDENCE",
  "ARCHITECTING_REPORT",
  "WRITING_REPORT",
  "VERIFYING_CITATIONS",
  "RUNNING_JUDGE_PANEL",
  "WAITING_FOR_CHECKPOINT_3",
  "EXPORTING",
  "COMPLETED",
];
