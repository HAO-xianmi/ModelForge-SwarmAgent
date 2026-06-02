"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

const PROFILES = ["practice", "generic_contest", "cumcm", "mcm_icm", "apmcm"];

export default function NewRunPage() {
  const router = useRouter();
  const [profile, setProfile] = useState("practice");
  const [mode, setMode] = useState("practice");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onCreate() {
    setBusy(true);
    setError(null);
    try {
      const { run_id } = await api.createRun(profile, mode);
      if (files.length) await api.uploadFiles(run_id, files);
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Start a new run</h1>
        <p className="mt-1 text-sm text-slate-600">
          Upload a problem statement and a dataset. Practice mode runs
          end-to-end; contest profiles pause at human checkpoints.
        </p>
      </div>

      <div className="grid gap-4 rounded-lg border bg-white p-6 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block font-medium">Operating mode</span>
          <select
            className="w-full rounded border px-3 py-2"
            value={mode}
            onChange={(e) => setMode(e.target.value)}
          >
            <option value="practice">practice</option>
            <option value="contest_compliant">contest_compliant</option>
            <option value="research">research</option>
          </select>
        </label>

        <label className="block text-sm">
          <span className="mb-1 block font-medium">Competition profile</span>
          <select
            className="w-full rounded border px-3 py-2"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
          >
            {PROFILES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>

        <label className="block text-sm sm:col-span-2">
          <span className="mb-1 block font-medium">
            Input files (problem.txt / data.csv / …)
          </span>
          <input
            type="file"
            multiple
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="w-full rounded border px-3 py-2"
          />
        </label>
      </div>

      {error && (
        <div className="rounded border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <button
        onClick={onCreate}
        disabled={busy}
        className="rounded bg-slate-900 px-5 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "Creating…" : "Create run & start"}
      </button>
    </div>
  );
}
