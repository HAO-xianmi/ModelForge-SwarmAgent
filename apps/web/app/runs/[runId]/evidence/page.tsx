"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";

// Evidence Explorer (spec §29.4): search claims, inspect provenance
// (experiment id, metric values, artifact ids, citations), open source artifacts.
export default function EvidenceExplorer({
  params,
}: {
  params: { runId: string };
}) {
  const runId = params.runId;
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("ALL");

  const state = useQuery({
    queryKey: ["state", runId],
    queryFn: () => api.getState(runId),
    refetchInterval: false,
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.getArtifacts(runId),
    refetchInterval: false,
  });

  const s = (state.data ?? {}) as any;
  const claims: any[] = s.evidence_claims ?? [];
  const citations: any[] = s.citations ?? [];
  const artifactById = useMemo(() => {
    const m = new Map<string, any>();
    (artifacts.data ?? []).forEach((a) => m.set(a.artifact_id, a));
    return m;
  }, [artifacts.data]);
  const citationById = useMemo(() => {
    const m = new Map<string, any>();
    citations.forEach((c) => m.set(c.citation_id, c));
    return m;
  }, [citations]);

  const filtered = claims.filter((c) => {
    if (statusFilter !== "ALL" && c.verification_status !== statusFilter) return false;
    if (query && !c.statement.toLowerCase().includes(query.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Evidence Explorer</h1>
          <p className="text-sm text-slate-600">
            Run <span className="font-mono">{runId}</span> ·{" "}
            {claims.length} claims ·{" "}
            {claims.filter((c) => c.verification_status === "VERIFIED").length} verified
          </p>
        </div>
        <Link href={`/runs/${runId}`} className="rounded border px-4 py-2 text-sm">
          ← Dashboard
        </Link>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          placeholder="Search claims…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded border px-3 py-2 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border px-3 py-2 text-sm"
        >
          {["ALL", "VERIFIED", "PENDING", "REJECTED", "NEEDS_HUMAN_REVIEW"].map((v) => (
            <option key={v} value={v}>
              {v}
            </option>
          ))}
        </select>
      </div>

      {filtered.length === 0 && (
        <p className="text-sm text-slate-500">No claims match.</p>
      )}

      <div className="space-y-3">
        {filtered.map((c) => (
          <ClaimCard
            key={c.claim_id}
            claim={c}
            artifactById={artifactById}
            citationById={citationById}
            runId={runId}
          />
        ))}
      </div>
    </div>
  );
}

function ClaimCard({
  claim,
  artifactById,
  citationById,
  runId,
}: {
  claim: any;
  artifactById: Map<string, any>;
  citationById: Map<string, any>;
  runId: string;
}) {
  const badge =
    claim.verification_status === "VERIFIED"
      ? "bg-green-100 text-green-800"
      : claim.verification_status === "REJECTED"
        ? "bg-red-100 text-red-800"
        : "bg-amber-100 text-amber-800";

  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm">{claim.statement}</p>
        <span className={`shrink-0 rounded px-2 py-0.5 text-xs ${badge}`}>
          {claim.verification_status}
        </span>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-slate-600 sm:grid-cols-2">
        <div>
          <span className="font-medium">Type:</span> {claim.claim_type}
        </div>
        {claim.experiment_id && (
          <div>
            <span className="font-medium">Experiment:</span>{" "}
            <span className="font-mono">{claim.experiment_id}</span>
          </div>
        )}
        {claim.metric_name && (
          <div>
            <span className="font-medium">Metric:</span> {claim.metric_name} ={" "}
            <span className="font-mono">
              {typeof claim.metric_value === "object"
                ? JSON.stringify(claim.metric_value)
                : String(claim.metric_value)}
            </span>
          </div>
        )}
        {claim.verified_by && (
          <div>
            <span className="font-medium">Verified by:</span> {claim.verified_by}
          </div>
        )}
      </div>

      {claim.artifact_ids?.length > 0 && (
        <div className="mt-3">
          <div className="text-xs font-medium text-slate-500">Evidence artifacts</div>
          <ul className="mt-1 space-y-0.5 text-xs">
            {claim.artifact_ids.map((id: string) => {
              const art = artifactById.get(id);
              return (
                <li key={id} className="font-mono">
                  {art ? `${art.artifact_type} · ${art.filename}` : id}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {claim.citation_ids?.length > 0 && (
        <div className="mt-2">
          <div className="text-xs font-medium text-slate-500">Citations</div>
          <ul className="mt-1 space-y-0.5 text-xs">
            {claim.citation_ids.map((id: string) => {
              const cit = citationById.get(id);
              return (
                <li key={id}>{cit ? `${cit.title} (${cit.year ?? "n.d."})` : id}</li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
