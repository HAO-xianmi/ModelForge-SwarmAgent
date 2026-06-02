# Workflow

The workflow is a state machine over `ModelingState`. The driver
(`graph/workflow.py`) executes one node per step, persists + audits the
blackboard, then routes to the next state. Human checkpoints pause execution and
resume on resolution (so a run survives across requests/processes).

## States (spec §10.3)

`CREATED → INGESTING → PARSING → WAITING_FOR_CHECKPOINT_1 → RETRIEVING_METHODS →
GENERATING_STRATEGIES → CRITIQUING_STRATEGIES → RUNNING_PILOTS →
SELECTING_STRATEGY → WAITING_FOR_CHECKPOINT_2 → PROFILING_DATA →
GENERATING_CODE → RUNNING_SANDBOX → DEBUGGING_CODE → RUNNING_BASELINES →
RUNNING_ROBUSTNESS_TESTS → AUDITING_EXPERIMENTS → REGISTERING_EVIDENCE →
ARCHITECTING_REPORT → WRITING_REPORT → VERIFYING_CITATIONS →
RUNNING_JUDGE_PANEL → WAITING_FOR_CHECKPOINT_3 → EXPORTING → COMPLETED`
(plus `FAILED`, `CANCELLED`).

## Diagram

```
START
  └─ ingest → parse_problem (+ analyze_domain)
       └─ [Checkpoint 1: confirm problem understanding]
            └─ retrieve_methods → generate_strategies ×3 (independent)
                 └─ skeptic_review → run_pilots → select_strategy
                      └─ [Checkpoint 2: confirm strategy]
                           └─ profile_data → generate_code → run_sandbox
                                ├─ FAILED → debug_code (bounded) → generate_code
                                └─ SUCCEEDED → run_baselines → run_robustness
                                     └─ audit_experiments
                                          ├─ blocking: model defect → generate_strategies
                                          ├─ blocking: code defect   → generate_code
                                          └─ pass → register_evidence
                                               └─ architect_report → write_report
                                                    → verify_citations → judge_panel
                                                         └─ [Checkpoint 3: confirm draft]
                                                              └─ build_latex → export_pdf
                                                                   → export_bundle → COMPLETED
```

## Conditional routing (spec §14.3)

| From | Condition | To |
|---|---|---|
| RUNNING_SANDBOX | execution FAILED & debug budget left | GENERATING_CODE (retry) |
| RUNNING_SANDBOX | SUCCEEDED | RUNNING_BASELINES |
| AUDITING_EXPERIMENTS | blocking model-design defect & budget left | GENERATING_STRATEGIES |
| AUDITING_EXPERIMENTS | blocking implementation defect & budget left | GENERATING_CODE |
| AUDITING_EXPERIMENTS | no blocking issues | REGISTERING_EVIDENCE |
| any | retry/loop budget exhausted | escalate → FAILED (human review) |

## Loop protection (spec §14.4 / 7.3)

Counters on `budget_state`: `code_debug_count`, `model_revision_count`,
`report_revision_count`, `citation_retry_count`, `total_loop_count`. Each is
capped by `Settings` (`MODELFORGE_MAX_*`). On exhaustion the run escalates with a
human-visible failure record.

## Checkpoints (spec §25)

| # | Status | Reviews | Required when |
|---|---|---|---|
| 1 | WAITING_FOR_CHECKPOINT_1 | problem understanding | profile requires it |
| 2 | WAITING_FOR_CHECKPOINT_2 | strategy selection | profile requires it |
| 3 | WAITING_FOR_CHECKPOINT_3 | final draft + disclosure | profile requires it |

Actions: `APPROVE`, `APPROVE_WITH_EDITS`, `REJECT_AND_RETRY`, `RETURN_TO_STAGE`,
`CANCEL_RUN`. In practice mode (no required checkpoints) the driver auto-advances
and records the auto-pass in the audit log.

## LangGraph

`graph.workflow.build_langgraph()` constructs a LangGraph `StateGraph` that
documents the node topology (Appendix B of the spec) for validation and
visualization. Execution uses the explicit driver because checkpoints require
pause/resume that a single `graph.invoke` cannot provide cleanly against a
DB-persisted blackboard.
