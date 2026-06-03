"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, RunListItem, WORKFLOW_STAGES } from "@/lib/api";

// Runs overview / benchmark dashboard (spec §29.1 page 9, §29.2): all runs with
// status, progress, and completion. Aggregates a simple success-rate summary.
export default function BenchmarkDashboard() {
  const runs = useQuery<RunListItem[]>({
    queryKey: ["runs"],
    queryFn: () => api.listRuns(),
    refetchInterval: 4000,
  });

  const list = runs.data ?? [];
  const completed = list.filter((r) => r.status === "COMPLETED").length;
  const failed = list.filter((r) => r.status === "FAILED").length;
  const running = list.filter(
    (r) => !["COMPLETED", "FAILED", "CANCELLED"].includes(r.status),
  ).length;
  const successRate = list.length
    ? ((completed / (completed + failed || 1)) * 100).toFixed(0)
    : "—";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Runs &amp; benchmarks</h1>
        <p className="text-sm text-slate-600">
          Every run in this instance. The benchmark suite (spec §39) would
          orchestrate many of these; this view aggregates whatever has run.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total runs" value={list.length} />
        <Stat label="Completed" value={completed} />
        <Stat label="Failed" value={failed} />
        <Stat label="Completion rate" value={`${successRate}%`} />
      </div>

      {running > 0 && (
        <p className="text-sm text-sky-700">{running} run(s) in progress…</p>
      )}

      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b text-left text-slate-500">
            <tr>
              <th className="p-3">Run</th>
              <th>Mode</th>
              <th>Profile</th>
              <th>Status</th>
              <th className="w-1/3">Progress</th>
            </tr>
          </thead>
          <tbody>
            {list.map((r) => (
              <tr key={r.run_id} className="border-t">
                <td className="p-3 font-mono text-xs">
                  <Link href={`/runs/${r.run_id}`} className="text-sky-700 underline">
                    {r.run_id}
                  </Link>
                </td>
                <td>{r.mode}</td>
                <td className="text-xs">{r.competition_profile_id}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td className="pr-3">
                  <ProgressBar status={r.status} />
                </td>
              </tr>
            ))}
            {list.length === 0 && (
              <tr>
                <td colSpan={5} className="p-6 text-center text-slate-400">
                  No runs yet. <Link href="/" className="underline">Start one →</Link>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded border bg-white p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold">{value}</div>
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
  return <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{status}</span>;
}

function ProgressBar({ status }: { status: string }) {
  const idx = WORKFLOW_STAGES.indexOf(status);
  const pct =
    status === "COMPLETED"
      ? 100
      : idx >= 0
        ? Math.round((idx / (WORKFLOW_STAGES.length - 1)) * 100)
        : 0;
  return (
    <div className="h-2 w-full rounded bg-slate-200">
      <div
        className={`h-2 rounded ${status === "FAILED" ? "bg-red-400" : "bg-green-400"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
