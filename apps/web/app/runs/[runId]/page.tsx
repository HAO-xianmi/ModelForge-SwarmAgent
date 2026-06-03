"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { WorkflowGraph } from "@/components/WorkflowGraph";
import { api } from "@/lib/api";

const TERMINAL = ["COMPLETED", "FAILED", "CANCELLED"];

export default function RunDashboard({
  params,
}: {
  params: { runId: string };
}) {
  const runId = params.runId;
  const qc = useQueryClient();
  const [tab, setTab] = useState<
    "overview" | "strategies" | "evidence" | "artifacts" | "events"
  >("overview");

  const run = useQuery({ queryKey: ["run", runId], queryFn: () => api.getRun(runId) });
  const state = useQuery({
    queryKey: ["state", runId],
    queryFn: () => api.getState(runId),
  });
  const checkpoints = useQuery({
    queryKey: ["checkpoints", runId],
    queryFn: () => api.getCheckpoints(runId),
  });

  const start = useMutation({
    mutationFn: () => api.start(runId),
    onSuccess: () => invalidate(),
  });
  const resolve = useMutation({
    mutationFn: (vars: { id: string; action: string }) =>
      api.resolveCheckpoint(runId, vars.id, vars.action),
    onSuccess: () => invalidate(),
  });

  function invalidate() {
    ["run", "state", "checkpoints", "artifacts", "events"].forEach((k) =>
      qc.invalidateQueries({ queryKey: [k, runId] }),
    );
  }

  const status = run.data?.status ?? "…";
  const s = (state.data ?? {}) as any;
  const pending = checkpoints.data?.pending ?? null;
  const isTerminal = TERMINAL.includes(status);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-mono text-lg">{runId}</h1>
          <StatusBadge status={status} />
        </div>
        <div className="flex gap-2">
          <Link
            href={`/runs/${runId}/evidence`}
            className="rounded border px-4 py-2 text-sm"
          >
            Evidence Explorer
          </Link>
          {!isTerminal && !pending && (
            <button
              onClick={() => start.mutate()}
              className="rounded bg-slate-900 px-4 py-2 text-sm text-white"
            >
              {status === "CREATED" ? "Start" : "Continue"}
            </button>
          )}
          {status === "COMPLETED" && (
            <a
              href={api.downloadUrl(runId)}
              className="rounded border px-4 py-2 text-sm"
            >
              Download bundle
            </a>
          )}
        </div>
      </div>

      <WorkflowGraph status={status} />

      {pending && (
        <CheckpointCard
          checkpoint={pending}
          onResolve={(action) =>
            resolve.mutate({ id: pending.checkpoint_id, action })
          }
        />
      )}

      <Metrics run={run.data} state={s} />

      <div className="border-b">
        <nav className="flex gap-4 text-sm">
          {(
            ["overview", "strategies", "evidence", "artifacts", "events"] as const
          ).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`pb-2 ${
                tab === t
                  ? "border-b-2 border-slate-900 font-medium"
                  : "text-slate-500"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      {tab === "overview" && <Overview state={s} />}
      {tab === "strategies" && <Strategies state={s} />}
      {tab === "evidence" && <Evidence state={s} />}
      {tab === "artifacts" && <Artifacts runId={runId} />}
      {tab === "events" && <Events runId={runId} />}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "COMPLETED"
      ? "bg-green-100 text-green-800"
      : status === "FAILED"
        ? "bg-red-100 text-red-800"
        : status.startsWith("WAITING")
          ? "bg-amber-100 text-amber-800"
          : "bg-sky-100 text-sky-800";
  return (
    <span className={`mt-1 inline-block rounded px-2 py-0.5 text-xs ${color}`}>
      {status}
    </span>
  );
}

function CheckpointCard({
  checkpoint,
  onResolve,
}: {
  checkpoint: any;
  onResolve: (action: string) => void;
}) {
  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <h3 className="font-medium">Human checkpoint: {checkpoint.kind}</h3>
      <pre className="mt-2 overflow-auto rounded bg-white p-3 text-xs">
        {JSON.stringify(checkpoint.context, null, 2)}
      </pre>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => onResolve("APPROVE")}
          className="rounded bg-green-600 px-3 py-1.5 text-sm text-white"
        >
          Approve
        </button>
        <button
          onClick={() => onResolve("REJECT_AND_RETRY")}
          className="rounded border px-3 py-1.5 text-sm"
        >
          Reject & retry
        </button>
        <button
          onClick={() => onResolve("CANCEL_RUN")}
          className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-700"
        >
          Cancel run
        </button>
      </div>
    </div>
  );
}

function Metrics({ run, state }: { run: any; state: any }) {
  const budget = state?.budget_state ?? {};
  const cells = [
    ["Mode", run?.mode ?? "—"],
    ["Version", run?.current_state_version ?? "—"],
    ["Input tokens", budget.input_tokens ?? 0],
    ["Est. cost (USD)", (run?.total_cost_estimate ?? 0).toFixed?.(4) ?? 0],
    ["Sandbox runtime (s)", (run?.total_runtime_seconds ?? 0).toFixed?.(1) ?? 0],
    ["Strategies", state?.strategy_candidates?.length ?? 0],
    ["Experiments", state?.experiment_records?.length ?? 0],
    ["Verified claims", (state?.evidence_claims ?? []).filter(
      (c: any) => c.verification_status === "VERIFIED",
    ).length],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {cells.map(([k, v]) => (
        <div key={k as string} className="rounded border bg-white p-3">
          <div className="text-xs text-slate-500">{k}</div>
          <div className="text-lg font-semibold">{String(v)}</div>
        </div>
      ))}
    </div>
  );
}

function Overview({ state }: { state: any }) {
  const card = state?.problem_card;
  return (
    <div className="space-y-3">
      {card ? (
        <div className="rounded border bg-white p-4">
          <h3 className="font-medium">{card.title}</h3>
          <p className="mt-1 text-sm text-slate-600">{card.problem_summary}</p>
          <p className="mt-2 text-xs text-slate-500">
            Confidence: {card.confidence}
          </p>
        </div>
      ) : (
        <p className="text-sm text-slate-500">No problem card yet.</p>
      )}
      {state?.failure_state && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {state.failure_state.detail}
        </div>
      )}
    </div>
  );
}

function Strategies({ state }: { state: any }) {
  const cands = state?.strategy_candidates ?? [];
  const pilots: any[] = state?.pilot_experiments ?? [];
  const selected = state?.selected_strategy?.strategy_id;
  if (!cands.length) return <p className="text-sm text-slate-500">No strategies yet.</p>;
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {cands.map((c: any) => {
        const pilot = pilots.find((p) => p.strategy_id === c.strategy_id);
        return (
          <div
            key={c.strategy_id}
            className={`rounded border bg-white p-4 ${
              c.strategy_id === selected ? "ring-2 ring-green-500" : ""
            }`}
          >
            <div className="text-xs uppercase text-slate-400">
              {c.design_goal}
            </div>
            <h4 className="font-medium">{c.strategy_name}</h4>
            <div className="mt-1 text-xs text-slate-500">
              {(c.method_stack ?? []).map((m: any) => m.method_id).join(", ")}
            </div>
            {pilot && (
              <div className="mt-2 text-xs">
                Pilot: {pilot.status}{" "}
                {pilot.metrics &&
                  Object.entries(pilot.metrics)
                    .slice(0, 2)
                    .map(([k, v]) => `${k}=${Number(v).toFixed(3)}`)
                    .join(" ")}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function Evidence({ state }: { state: any }) {
  const claims = state?.evidence_claims ?? [];
  if (!claims.length) return <p className="text-sm text-slate-500">No evidence yet.</p>;
  return (
    <ul className="space-y-2">
      {claims.map((c: any) => (
        <li key={c.claim_id} className="rounded border bg-white p-3 text-sm">
          <span
            className={`mr-2 rounded px-1.5 py-0.5 text-xs ${
              c.verification_status === "VERIFIED"
                ? "bg-green-100 text-green-800"
                : c.verification_status === "REJECTED"
                  ? "bg-red-100 text-red-800"
                  : "bg-amber-100 text-amber-800"
            }`}
          >
            {c.verification_status}
          </span>
          {c.statement}
        </li>
      ))}
    </ul>
  );
}

function Artifacts({ runId }: { runId: string }) {
  const q = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.getArtifacts(runId),
  });
  const arts = q.data ?? [];
  return (
    <table className="w-full text-sm">
      <thead className="text-left text-slate-500">
        <tr>
          <th className="py-1">Type</th>
          <th>Filename</th>
          <th>Size</th>
        </tr>
      </thead>
      <tbody>
        {arts.map((a) => (
          <tr key={a.artifact_id} className="border-t">
            <td className="py-1 font-mono text-xs">{a.artifact_type}</td>
            <td>{a.filename}</td>
            <td>{a.size_bytes}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Events({ runId }: { runId: string }) {
  const q = useQuery({
    queryKey: ["events", runId],
    queryFn: () => api.getEvents(runId),
  });
  const events = (q.data ?? []).slice(-50).reverse();
  return (
    <ul className="space-y-1 text-xs">
      {events.map((e) => (
        <li key={e.event_id} className="flex gap-3 border-b py-1">
          <span className="text-slate-400">{e.timestamp.slice(11, 19)}</span>
          <span className="font-mono">{e.event_type}</span>
          <span className="text-slate-500">{e.actor_id}</span>
        </li>
      ))}
    </ul>
  );
}
