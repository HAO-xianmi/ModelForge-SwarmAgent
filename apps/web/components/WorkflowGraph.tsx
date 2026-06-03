"use client";

import { useMemo } from "react";
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
  Position,
} from "reactflow";
import "reactflow/dist/style.css";

// The spec workflow as a directed graph. Each entry: [id, label, [next ids]].
// Checkpoints and the debug/audit loops are encoded so the graph mirrors §13.
const FLOW: { id: string; label: string; next: string[] }[] = [
  { id: "PARSING", label: "Parse + Analyze", next: ["WAITING_FOR_CHECKPOINT_1"] },
  { id: "WAITING_FOR_CHECKPOINT_1", label: "① Problem", next: ["RETRIEVING_METHODS"] },
  { id: "RETRIEVING_METHODS", label: "Retrieve methods", next: ["GENERATING_STRATEGIES"] },
  { id: "GENERATING_STRATEGIES", label: "Generate 3 strategies", next: ["CRITIQUING_STRATEGIES"] },
  { id: "CRITIQUING_STRATEGIES", label: "Skeptic", next: ["RUNNING_PILOTS"] },
  { id: "RUNNING_PILOTS", label: "Pilots", next: ["SELECTING_STRATEGY"] },
  { id: "SELECTING_STRATEGY", label: "Judge / select", next: ["WAITING_FOR_CHECKPOINT_2"] },
  { id: "WAITING_FOR_CHECKPOINT_2", label: "② Strategy", next: ["PROFILING_DATA"] },
  { id: "PROFILING_DATA", label: "Profile data", next: ["GENERATING_CODE"] },
  { id: "GENERATING_CODE", label: "Generate code", next: ["RUNNING_SANDBOX"] },
  { id: "RUNNING_SANDBOX", label: "Run sandbox", next: ["RUNNING_BASELINES", "GENERATING_CODE"] },
  { id: "RUNNING_BASELINES", label: "Baselines", next: ["RUNNING_ROBUSTNESS_TESTS"] },
  { id: "RUNNING_ROBUSTNESS_TESTS", label: "Robustness", next: ["AUDITING_EXPERIMENTS"] },
  { id: "AUDITING_EXPERIMENTS", label: "Audit", next: ["REGISTERING_EVIDENCE", "GENERATING_STRATEGIES"] },
  { id: "REGISTERING_EVIDENCE", label: "Register evidence", next: ["ARCHITECTING_REPORT"] },
  { id: "ARCHITECTING_REPORT", label: "Architect report", next: ["WRITING_REPORT"] },
  { id: "WRITING_REPORT", label: "Write report", next: ["VERIFYING_CITATIONS"] },
  { id: "VERIFYING_CITATIONS", label: "Verify citations", next: ["RUNNING_JUDGE_PANEL"] },
  { id: "RUNNING_JUDGE_PANEL", label: "Judge panel", next: ["WAITING_FOR_CHECKPOINT_3"] },
  { id: "WAITING_FOR_CHECKPOINT_3", label: "③ Final draft", next: ["EXPORTING"] },
  { id: "EXPORTING", label: "Export bundle", next: ["COMPLETED"] },
  { id: "COMPLETED", label: "Completed", next: [] },
];

const ORDER = FLOW.map((f) => f.id);

function nodeStyle(state: "done" | "current" | "pending" | "failed") {
  const palette = {
    done: { background: "#dcfce7", border: "#22c55e", color: "#14532d" },
    current: { background: "#e0f2fe", border: "#0ea5e9", color: "#075985" },
    pending: { background: "#f1f5f9", border: "#cbd5e1", color: "#475569" },
    failed: { background: "#fee2e2", border: "#ef4444", color: "#7f1d1d" },
  }[state];
  return {
    background: palette.background,
    border: `2px solid ${palette.border}`,
    color: palette.color,
    borderRadius: 8,
    padding: 6,
    fontSize: 11,
    width: 150,
  };
}

export function WorkflowGraph({ status }: { status: string }) {
  const { nodes, edges } = useMemo(() => {
    const currentIdx = ORDER.indexOf(status);
    const failed = status === "FAILED";

    const nodes: Node[] = FLOW.map((f, i) => {
      const isCheckpoint = f.id.startsWith("WAITING");
      let state: "done" | "current" | "pending" | "failed" = "pending";
      if (failed && currentIdx >= 0 && i === currentIdx) state = "failed";
      else if (currentIdx >= 0 && i < currentIdx) state = "done";
      else if (f.id === status) state = "current";
      return {
        id: f.id,
        data: { label: f.label },
        position: { x: (i % 4) * 200, y: Math.floor(i / 4) * 110 },
        style: { ...nodeStyle(state), ...(isCheckpoint ? { fontWeight: 700 } : {}) },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      };
    });

    const edges: Edge[] = [];
    for (const f of FLOW) {
      for (const target of f.next) {
        const isLoop = ORDER.indexOf(target) < ORDER.indexOf(f.id);
        edges.push({
          id: `${f.id}->${target}`,
          source: f.id,
          target,
          animated: f.id === status,
          style: { stroke: isLoop ? "#f59e0b" : "#94a3b8", strokeDasharray: isLoop ? "4 4" : undefined },
          markerEnd: { type: MarkerType.ArrowClosed },
          label: isLoop ? "revise" : undefined,
        });
      }
    }
    return { nodes, edges };
  }, [status]);

  return (
    <div className="h-[420px] rounded-lg border bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background gap={16} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
