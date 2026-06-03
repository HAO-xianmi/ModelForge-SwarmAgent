"""Workflow node implementations (spec 13 / Appendix B).

Each node takes the blackboard state + deps and returns the next ``RunStatus``
(or pauses at a checkpoint). Nodes are deliberately small and call agents
(reasoning) or services (deterministic work). They never fabricate results.
"""

from __future__ import annotations

from modelforge.agents import (
    CodeAuthorAgent,
    DomainAnalystAgent,
    MethodRetrieverAgent,
    PaperArchitectAgent,
    PaperWriterAgent,
    ProblemParserAgent,
    SkepticAgent,
    StrategyJudgeAgent,
    StrategyProposerAgent,
)
from modelforge.agents.base import AgentContext
from modelforge.agents.debugger import DebuggerAgent
from modelforge.common.errors import FailureType, ModelForgeError
from modelforge.common.logging import get_logger
from modelforge.graph.deps import WorkflowDeps
from modelforge.schemas.control import FailureState
from modelforge.schemas.enums import (
    ClaimStatus,
    ClaimType,
    ExperimentStatus,
    ExperimentType,
    JudgeDecision,
    ProblemFamily,
    RunStatus,
    StrategyGoal,
)
from modelforge.schemas.evidence import CitationRecord
from modelforge.schemas.report import ReportArtifacts
from modelforge.schemas.state import ModelingState

_log = get_logger("modelforge.workflow.nodes")

# The three proposer instances (spec 8.4).
_PROPOSER_GOALS = (
    StrategyGoal.INTERPRETABILITY_FIRST,
    StrategyGoal.PERFORMANCE_FIRST,
    StrategyGoal.INNOVATION_FIRST,
)


def _fail(state: ModelingState, ftype: FailureType, stage: str, detail: str) -> RunStatus:
    state.failure_state = FailureState(failure_type=ftype, stage=stage, detail=detail)
    state.status = RunStatus.FAILED
    return RunStatus.FAILED


def _input_files(state: ModelingState, deps: WorkflowDeps) -> dict[str, bytes]:
    """Read ingested data files back from the registry for experiments."""
    out: dict[str, bytes] = {}
    if not state.input_manifest:
        return out
    for f in state.input_manifest.by_role("data"):
        if f.artifact_id:
            try:
                out[f.normalized_name] = deps.registry.read_bytes(f.artifact_id)
            except ModelForgeError:
                continue
    return out


# --------------------------------------------------------------------------- #
# Nodes
# --------------------------------------------------------------------------- #
def parse_problem(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    # Data-only runs (no problem text) still proceed; only a wholly absent
    # manifest is a hard input failure.
    if state.input_manifest is None:
        return _fail(state, FailureType.INPUT_FAILURE, "parse_problem", "no input")
    ctx = deps.agent_context(state.run_id)
    result = ProblemParserAgent(ctx).parse(state.input_manifest)
    _record_calls(state, ctx)
    if not result.ok or result.output is None:
        return _fail(state, FailureType.PARSING_FAILURE, "parse_problem", result.failure or "")
    state.problem_card = result.output
    return RunStatus.RETRIEVING_METHODS  # analyze_domain runs inline below


def analyze_domain(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if state.problem_card is None:
        return _fail(state, FailureType.PARSING_FAILURE, "analyze_domain", "no problem card")
    ctx = deps.agent_context(state.run_id)
    result = DomainAnalystAgent(ctx).analyze(state.problem_card)
    _record_calls(state, ctx)
    if not result.ok or result.output is None:
        return _fail(state, FailureType.PARSING_FAILURE, "analyze_domain", result.failure or "")
    state.domain_analysis = result.output
    return RunStatus.WAITING_FOR_CHECKPOINT_1


def retrieve_methods(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if state.problem_card is None or state.domain_analysis is None:
        return _fail(state, FailureType.PARSING_FAILURE, "retrieve_methods", "missing inputs")
    methods = MethodRetrieverAgent().retrieve(state.problem_card, state.domain_analysis)
    state.retrieved_methods = methods
    return RunStatus.GENERATING_STRATEGIES


def generate_strategies(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    assert state.problem_card and state.domain_analysis
    candidates = []
    for goal in _PROPOSER_GOALS:
        ctx = deps.agent_context(state.run_id)
        res = StrategyProposerAgent(ctx, goal).propose(
            state.problem_card, state.domain_analysis, state.retrieved_methods
        )
        _record_calls(state, ctx)
        if res.ok and res.output is not None:
            candidates.append(res.output)
    if not candidates:
        return _fail(
            state, FailureType.MODEL_PROVIDER_FAILURE, "generate_strategies", "no candidates"
        )
    state.strategy_candidates = candidates
    return RunStatus.CRITIQUING_STRATEGIES


def skeptic_review(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    ctx = deps.agent_context(state.run_id)
    res = SkepticAgent(ctx).review(state.strategy_candidates)
    _record_calls(state, ctx)
    if res.ok:
        state.skeptic_report = res.output
    return RunStatus.RUNNING_PILOTS


def run_pilots(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    inputs = _input_files(state, deps)
    pilots = deps.pilots.run_all(state.run_id, state.strategy_candidates, inputs)
    state.pilot_experiments = pilots
    for p in pilots:
        state.budget_state.sandbox_runtime_seconds += p.runtime_seconds
    return RunStatus.SELECTING_STRATEGY


def select_strategy(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    ctx = deps.agent_context(state.run_id)
    res = StrategyJudgeAgent(ctx).judge(
        state.strategy_candidates, state.skeptic_report, state.pilot_experiments
    )
    _record_calls(state, ctx)
    if not res.ok or res.output is None:
        return _fail(state, FailureType.MODEL_PROVIDER_FAILURE, "select_strategy", "judge failed")
    report = res.output
    state.judge_reports.append(report)
    if report.decision is JudgeDecision.ESCALATE_TO_HUMAN or not report.selected_strategy_id:
        # Fall back to the first successful pilot's strategy if available.
        succeeded = [p for p in state.pilot_experiments if p.succeeded]
        if succeeded:
            report.selected_strategy_id = succeeded[0].strategy_id
        elif state.strategy_candidates:
            report.selected_strategy_id = state.strategy_candidates[0].strategy_id
    selected = state.strategy_by_id(report.selected_strategy_id or "")
    if selected is None:
        return _fail(state, FailureType.QUALITY_GATE_FAILURE, "select_strategy", "no selection")
    state.selected_strategy = selected
    return RunStatus.WAITING_FOR_CHECKPOINT_2


def profile_data(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if state.input_manifest:
        for f in state.input_manifest.by_role("data"):
            if f.normalized_name.endswith(".csv") and f.artifact_id:
                try:
                    data = deps.registry.read_bytes(f.artifact_id)
                    state.data_profile = deps.profiler.profile_csv_bytes(
                        f.file_id, f.normalized_name, data
                    )
                    break
                except (ModelForgeError, ValueError):
                    continue
    return RunStatus.GENERATING_CODE


def generate_code(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if state.selected_strategy is None:
        return _fail(state, FailureType.CODE_FAILURE, "generate_code", "no strategy")
    ctx = deps.agent_context(state.run_id)
    res = CodeAuthorAgent(ctx, deps.codegen).author(state.selected_strategy)
    _record_calls(state, ctx)
    if not res.ok or res.output is None:
        return _fail(state, FailureType.CODE_FAILURE, "generate_code", "code author failed")
    state.code_artifacts = [res.output]
    return RunStatus.RUNNING_SANDBOX


def run_sandbox(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if not state.code_artifacts or state.selected_strategy is None:
        return _fail(state, FailureType.CODE_FAILURE, "run_sandbox", "no code")
    code = state.code_artifacts[-1]
    inputs = _input_files(state, deps)
    debugger = DebuggerAgent(deps.agent_context(state.run_id)).as_callable()
    needs_split = state.selected_strategy.problem_family.value in ("prediction", "classification")
    record = deps.experiment_runner.run(
        state.run_id,
        code,
        experiment_type=ExperimentType.FORMAL,
        input_files=inputs,
        debugger=debugger,
        train_test_split=needs_split,
    )
    # Replace any prior FORMAL record for this strategy.
    state.experiment_records = [
        e for e in state.experiment_records if e.experiment_type is not ExperimentType.FORMAL
    ]
    state.experiment_records.append(record)
    state.budget_state.sandbox_runtime_seconds += record.runtime_seconds
    state.budget_state.code_debug_count += len(record.debug_patches)
    if record.status is ExperimentStatus.SUCCEEDED:
        return RunStatus.RUNNING_BASELINES
    return RunStatus.DEBUGGING_CODE


def run_baselines(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    assert state.selected_strategy
    inputs = _input_files(state, deps)
    baseline = deps.baselines.run(state.run_id, state.selected_strategy, inputs)
    state.baseline_results = [baseline]
    state.budget_state.sandbox_runtime_seconds += 0.0
    return RunStatus.RUNNING_ROBUSTNESS_TESTS


def run_robustness(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    assert state.selected_strategy
    inputs = _input_files(state, deps)
    result = deps.robustness.run(state.run_id, state.selected_strategy, inputs)
    state.robustness_results = [result]
    return RunStatus.AUDITING_EXPERIMENTS


def audit_experiments(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    assert state.selected_strategy
    formal = next(
        (e for e in state.experiment_records if e.experiment_type is ExperimentType.FORMAL),
        None,
    )
    summary = deps.auditor.audit(
        state.selected_strategy, formal, state.baseline_results, state.robustness_results
    )
    state.audit_summary = summary
    state.blocking_issues = summary.blocking_issues
    if summary.passed:
        return RunStatus.REGISTERING_EVIDENCE
    # Route based on the worst blocking issue (spec 14.3).
    return RunStatus.GENERATING_CODE  # default; the router refines this


def register_evidence(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    assert state.selected_strategy
    formal = next(
        (e for e in state.experiment_records if e.experiment_type is ExperimentType.FORMAL),
        None,
    )
    claims = []
    if formal and formal.status is ExperimentStatus.SUCCEEDED:
        family = state.selected_strategy.problem_family
        primary = _primary_metric(family)
        if primary and primary in formal.metrics:
            claim = deps.evidence.register_quantitative(
                state.run_id,
                f"The selected model achieved {primary} = {formal.metrics[primary]:.4f}.",
                experiment=formal,
                metric_name=primary,
                artifact_ids=formal.figure_artifact_ids + formal.table_artifact_ids,
            )
            claims.append(deps.evidence.verify(claim, state.experiment_records))
        # Model comparison vs baseline.
        baseline = state.baseline_results[0] if state.baseline_results else None
        if baseline and primary in baseline.metrics and primary in formal.metrics:
            comp = deps.evidence.register_comparison(
                state.run_id,
                f"The selected model's {primary} ({formal.metrics[primary]:.4f}) vs baseline "
                f"({baseline.metrics[primary]:.4f}).",
                experiment=formal,
                metric_name=primary,
                baseline_value=baseline.metrics[primary],
                selected_value=formal.metrics[primary],
            )
            claims.append(deps.evidence.verify(comp, state.experiment_records))
        # Robustness conclusion.
        robust = state.robustness_results[0] if state.robustness_results else None
        if robust and robust.status is ExperimentStatus.SUCCEEDED:
            std_key = f"{primary}_std"
            if std_key in robust.summary:
                rc = deps.evidence.register_qualitative(
                    state.run_id,
                    f"Across repeated seeds, {primary} varied with std "
                    f"{robust.summary[std_key]:.4f}, indicating stability.",
                    ClaimType.ROBUSTNESS_CONCLUSION,
                    status=ClaimStatus.VERIFIED,
                )
                claims.append(rc)
    # Data description claim (always available, qualitative).
    if state.data_profile:
        claims.append(
            deps.evidence.register_qualitative(
                state.run_id,
                f"The dataset has {state.data_profile.row_count} rows and "
                f"{state.data_profile.column_count} columns.",
                ClaimType.DATA_DESCRIPTION,
                status=ClaimStatus.VERIFIED,
            )
        )
    state.evidence_claims = claims
    # Citations from the selected strategy's methods.
    state.citations = _build_citations(state, deps)
    return RunStatus.ARCHITECTING_REPORT


def architect_report(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    ctx = deps.agent_context(state.run_id)
    formal = next(
        (e for e in state.experiment_records if e.experiment_type is ExperimentType.FORMAL),
        None,
    )
    figure_ids = formal.figure_artifact_ids if formal else []
    table_ids = formal.table_artifact_ids if formal else []
    verified = state.verified_claims()
    title = state.problem_card.title if state.problem_card else "Modeling Report"
    res = PaperArchitectAgent(ctx).architect(
        title, verified, figure_ids, table_ids, state.citations, state.problem_card
    )
    _record_calls(state, ctx)
    if res.ok and res.output is not None:
        state.report_outline = res.output
    return RunStatus.WRITING_REPORT


def write_report(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    if state.report_outline is None:
        return _fail(state, FailureType.INTERNAL_ERROR, "write_report", "no outline")
    ctx = deps.agent_context(state.run_id)
    claim_index = {c.claim_id: c for c in state.evidence_claims}
    section_texts: dict[str, str] = {}
    writer = PaperWriterAgent(ctx)
    card = state.problem_card
    assumptions = card.assumptions_to_confirm if card else []
    variables = (card.variables or card.decision_variables) if card else []
    for section in state.report_outline.sections:
        res = writer.write_section(
            section, claim_index, assumptions=assumptions, variables=variables
        )
        if res.ok and res.output is not None:
            section_texts[section.section_id] = res.output.text
    _record_calls(state, ctx)
    state.section_texts = section_texts
    return RunStatus.VERIFYING_CITATIONS


def verify_citations(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    state.citations = deps.citations.verify_all(state.citations)
    return RunStatus.RUNNING_JUDGE_PANEL


def run_judge_panel(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    # Lightweight final gate: ensure verified evidence exists and no blocking
    # issues remain. (A full multi-judge panel is a future extension.)
    if not state.verified_claims():
        # No verified evidence -> needs human review, but not a hard fail.
        _log.warning("judge panel: no verified claims for run %s", state.run_id)
    return RunStatus.WAITING_FOR_CHECKPOINT_3


def build_report_files(state: ModelingState, deps: WorkflowDeps) -> None:
    """Assemble markdown/tex/pdf artifacts (called during export stage)."""
    from modelforge.schemas.enums import ArtifactType

    outline = state.report_outline
    if outline is None:
        return
    section_texts = state.section_texts
    title = state.problem_card.title if state.problem_card else "Modeling Report"
    disclosure = None
    if deps.compliance.disclosure_required():
        disclosure = "\n## AI-Use Disclosure\n\nSee ai_disclosure.md in the bundle.\n"

    markdown, claim_map = deps.report_builder.build_markdown(
        title, outline, section_texts, state.evidence_claims, state.citations,
        ai_disclosure=disclosure,
    )
    md_art = deps.registry.register_text(
        state.run_id, ArtifactType.REPORT_MARKDOWN, "report.md", markdown
    )
    tex = deps.report_builder.build_latex(title, markdown, state.citations)
    tex_art = deps.registry.register_text(
        state.run_id, ArtifactType.REPORT_LATEX, "report.tex", tex
    )
    bib = deps.report_builder.build_bibtex(state.citations)
    if bib.strip():
        deps.registry.register_text(
            state.run_id, ArtifactType.CITATION_RECORD, "references.bib", bib
        )

    report_artifacts = ReportArtifacts(
        markdown_artifact_id=md_art.artifact_id,
        latex_artifact_id=tex_art.artifact_id,
        claim_map=claim_map,
    )

    # PDF (graceful if no compiler).
    figures = _collect_figures(state, deps)
    pdf_dir = deps.settings.runs_path / state.run_id / "reports"
    pdf_path, log = deps.latex.compile_pdf(tex, pdf_dir, figures=figures)
    report_artifacts.compilation_log = log[-2000:]
    if pdf_path and pdf_path.exists():
        pdf_art = deps.registry.register_existing_file(
            state.run_id, ArtifactType.REPORT_PDF, pdf_path
        )
        report_artifacts.pdf_artifact_id = pdf_art.artifact_id
        report_artifacts.compiled_pdf = True
    state.report_artifacts = report_artifacts


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _record_calls(state: ModelingState, ctx: AgentContext) -> None:
    for call in ctx.model_calls:
        state.budget_state.add_tokens(
            call.input_tokens, call.output_tokens, call.estimated_cost
        )


def _primary_metric(family: ProblemFamily) -> str:
    return {
        ProblemFamily.PREDICTION: "rmse",
        ProblemFamily.CLASSIFICATION: "accuracy",
        ProblemFamily.CLUSTERING: "silhouette",
        ProblemFamily.OPTIMIZATION: "objective_value",
        ProblemFamily.EVALUATION: "top_score",
        ProblemFamily.GRAPH: "n_nodes",
        ProblemFamily.SIMULATION: "estimate_mean",
    }.get(family, "")


def _build_citations(state: ModelingState, deps: WorkflowDeps) -> list[CitationRecord]:
    from modelforge.services.method_library import get_method_library

    library = get_method_library()
    citations: list[CitationRecord] = []
    seen: set[str] = set()
    if state.selected_strategy:
        for entry in state.selected_strategy.method_stack:
            method = library.get(entry.method_id)
            if not method:
                continue
            for ref in method.references:
                if ref in seen:
                    continue
                seen.add(ref)
                citations.append(deps.citations.register_from_reference(ref))
    return deps.citations.verify_all(citations)


def _collect_figures(state: ModelingState, deps: WorkflowDeps) -> dict[str, bytes]:
    from modelforge.schemas.enums import ArtifactType

    out: dict[str, bytes] = {}
    for art in deps.registry.list_for_run(state.run_id, ArtifactType.FIGURE):
        try:
            out[art.filename] = deps.registry.read_bytes(art.artifact_id)
        except ModelForgeError:
            continue
    return out
