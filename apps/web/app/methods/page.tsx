"use client";

import { useQuery } from "@tanstack/react-query";

interface MethodRow {
  method_id: string;
  name: string;
  category: string;
}

export default function MethodsPage() {
  const q = useQuery<MethodRow[]>({
    queryKey: ["methods"],
    queryFn: async () => {
      const res = await fetch("/api/v1/methods");
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    refetchInterval: false,
  });
  const methods = q.data ?? [];
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Method library</h1>
      <p className="text-sm text-slate-600">
        {methods.length} registered methods. Retrieval only ever returns entries
        from this library.
      </p>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {methods.map((m) => (
          <div key={m.method_id} className="rounded border bg-white p-3">
            <div className="text-xs uppercase text-slate-400">{m.category}</div>
            <div className="font-medium">{m.name}</div>
            <div className="font-mono text-xs text-slate-500">{m.method_id}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
