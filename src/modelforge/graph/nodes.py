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
    ProblemParserAgent,
    RouteGeneratorAgent,
    SkepticAgent,
    StrategyJudgeAgent,
    StrategyProposerAgent,
)
from modelforge.agents.base import AgentContext
from modelforge.agents.competition_writer import CompetitionWriterAgent
from modelforge.agents.debugger import DebuggerAgent
from modelforge.agents.red_team import RedTeamAgent
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
from modelforge.schemas.evidence import CitationRecord, EvidenceClaim
from modelforge.schemas.experiment import ExperimentRecord
from modelforge.schemas.problem import SourceReference, SubProblem
from modelforge.schemas.report import ReportArtifacts
from modelforge.schemas.state import ModelingState
from modelforge.services.evaluation import MethodFitGate
from modelforge.services.routes import RouteTournament

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
    state.subproblem_routes = {}
    state.subproblem_selected_routes = {}
    tournament = RouteTournament()
    for subproblem in state.problem_card.subproblems:
        ctx = deps.agent_context(state.run_id)
        route_res = RouteGeneratorAgent(ctx).generate(
            state.problem_card, state.domain_analysis, subproblem=subproblem
        )
        _record_calls(state, ctx)
        if route_res.ok and route_res.output is not None:
            route_set = route_res.output
            state.subproblem_routes[subproblem.sub_id] = route_set
            selected = tournament.run(route_set).selected_route_id
            route = next((r for r in route_set.routes if r.route_id == selected), None)
            if route is not None:
                state.subproblem_selected_routes[subproblem.sub_id] = route

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
    fit_failure = _run_method_fit_gate(state)
    if fit_failure:
        return _fail(state, FailureType.QUALITY_GATE_FAILURE, "method_fit_gate", fit_failure)
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
        subproblems = state.problem_card.subproblems if state.problem_card else []
        targets: list[SubProblem | None] = list(subproblems) if subproblems else [None]
        evidence_artifacts = _experiment_source_artifacts(formal)
        if primary and primary in formal.metrics:
            for subproblem in targets:
                statement = (
                    f"For subproblem {subproblem.sub_id}, the selected model achieved "
                    f"{primary} = {formal.metrics[primary]:.4f}."
                    if subproblem is not None
                    else (
                        f"The selected model achieved "
                        f"{primary} = {formal.metrics[primary]:.4f}."
                    )
                )
                claim = deps.evidence.register_quantitative(
                    state.run_id,
                    statement,
                    experiment=formal,
                    metric_name=primary,
                    artifact_ids=evidence_artifacts,
                    subproblem_id=subproblem.sub_id if subproblem else None,
                    metric_refs=[primary],
                    table_refs=formal.table_artifact_ids,
                    figure_refs=formal.figure_artifact_ids,
                    source_map=_source_map_for_subproblem(subproblem),
                )
                claims.append(deps.evidence.verify(claim, state.experiment_records))
        # Model comparison vs baseline.
        baseline = state.baseline_results[0] if state.baseline_results else None
        if baseline and primary in baseline.metrics and primary in formal.metrics:
            for subproblem in targets:
                prefix = (
                    f"For subproblem {subproblem.sub_id}, "
                    if subproblem is not None
                    else "The selected model's "
                )
                comp = deps.evidence.register_comparison(
                    state.run_id,
                    f"{prefix}{primary} ({formal.metrics[primary]:.4f}) vs baseline "
                    f"({baseline.metrics[primary]:.4f}).",
                    experiment=formal,
                    metric_name=primary,
                    baseline_value=baseline.metrics[primary],
                    selected_value=formal.metrics[primary],
                    artifact_ids=evidence_artifacts,
                    subproblem_id=subproblem.sub_id if subproblem else None,
                    metric_refs=[primary],
                    table_refs=formal.table_artifact_ids,
                    figure_refs=formal.figure_artifact_ids,
                    source_map=_source_map_for_subproblem(subproblem),
                )
                claims.append(deps.evidence.verify(comp, state.experiment_records))
        # Robustness conclusion.
        robust = state.robustness_results[0] if state.robustness_results else None
        if robust and robust.status is ExperimentStatus.SUCCEEDED:
            std_key = f"{primary}_std"
            if std_key in robust.summary:
                for subproblem in targets:
                    prefix = (
                        f"For subproblem {subproblem.sub_id}, "
                        if subproblem is not None
                        else ""
                    )
                    rc = deps.evidence.register_qualitative(
                        state.run_id,
                        f"{prefix}across repeated seeds, {primary} varied with std "
                        f"{robust.summary[std_key]:.4f}, indicating stability.",
                        ClaimType.ROBUSTNESS_CONCLUSION,
                        artifact_ids=evidence_artifacts,
                        subproblem_id=subproblem.sub_id if subproblem else None,
                        metric_refs=[std_key],
                        table_refs=formal.table_artifact_ids,
                        figure_refs=formal.figure_artifact_ids,
                        source_map=_source_map_for_subproblem(subproblem),
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
                artifact_ids=(
                    [f.artifact_id for f in state.input_manifest.files if f.artifact_id]
                    if state.input_manifest
                    else []
                ),
                status=ClaimStatus.VERIFIED,
            )
        )
    state.evidence_claims = claims
    state.subproblem_evidence = _group_claims_by_subproblem(claims)
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
    writer = CompetitionWriterAgent(ctx)
    card = state.problem_card
    assumptions = card.assumptions_to_confirm if card else []
    variables = (card.variables or card.decision_variables) if card else []
    # Slice 4: match each sub-problem section to its best-fit domain model so the
    # writer (real provider) weaves the right governing equations in. Under the
    # mock provider the writer emits the same clean scaffolding (no regression).
    sub_to_dm: dict[str, dict] = {}
    if card:
        from modelforge.services.method_library.domain_models import (
            get_domain_model_library,
        )

        kb = get_domain_model_library()
        for sp in card.subproblems:
            hits = kb.retrieve(sp.statement, None, top_k=1)
            if hits:
                sub_to_dm[sp.sub_id] = hits[0].model_dump()
    for section in state.report_outline.sections:
        dm = (
            sub_to_dm.get(section.section_id.replace("model_", ""))
            if section.section_id.startswith("model_")
            else None
        )
        res = writer.write_section(
            section, claim_index, assumptions=assumptions, variables=variables,
            domain_model=dm,
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
    if state.report_outline is None:
        return _fail(state, FailureType.INTERNAL_ERROR, "run_judge_panel", "no outline")

    title = state.problem_card.title if state.problem_card else "Modeling Report"
    markdown, _claim_map = deps.report_builder.build_markdown(
        title,
        state.report_outline,
        state.section_texts,
        state.evidence_claims,
        state.citations,
    )
    latex_source = deps.report_builder.build_latex(title, markdown, state.citations)
    report = deps.judge_panel.evaluate(
        state, markdown=markdown, latex_source=latex_source
    )
    state.judge_panel_reports.append(report)
    _log.info(
        "judge panel: passed=%s final_score=%.2f issues=%d hints=%s",
        report.passed,
        report.final_score,
        len(report.issues),
        ",".join(report.routing_hints),
    )
    if report.passed:
        # Advisory adversarial RedTeam review on the accepted draft (Slice 4: the
        # "full panel" the stub promised). Findings are logged for the human
        # reviewer at checkpoint 3; the deterministic panel above is the hard gate.
        if not state.verified_claims():
            _log.warning("judge panel: no verified claims for run %s", state.run_id)
        draft = "\n\n".join(state.section_texts.values())
        if draft.strip():
            ctx = deps.agent_context(state.run_id)
            rt = RedTeamAgent(ctx).review(draft)
            _record_calls(state, ctx)
            if rt.ok and rt.output is not None:
                _log.info(
                    "red-team: verdict=%s findings=%d",
                    rt.output.verdict,
                    len(rt.output.findings),
                )
        return RunStatus.WAITING_FOR_CHECKPOINT_3
    detail = (
        f"judge panel failed with score {report.final_score:.2f}: "
        + "; ".join(report.revision_plan[:4])
    )
    _log.warning(detail)
    # The workflow router inspects the latest report's hints. A repairable LaTeX
    # defect is routed to REPORT_REPAIR (bounded by the quality budget); other
    # failures fall through to the existing quality-gate handling.
    return RunStatus.FAILED


def repair_report(state: ModelingState, deps: WorkflowDeps) -> RunStatus:
    """Deterministic report-repair stage (no LLM).

    Rebuilds the markdown/LaTeX from the existing outline + section drafts via the
    ``ReportBuilder``, which strips internal claim-id leaks, drops references to
    unverified claims, and emits well-formed LaTeX (balanced environments, proper
    document structure). On success the run returns to RUNNING_JUDGE_PANEL for
    re-evaluation. Content the repair cannot synthesize — an empty outline or
    empty section bodies — is an unrecoverable structural dead-end and fails fast
    with a recorded reason (QUALITY_GATE_FAILURE), not a wasted budget loop.
    """
    from modelforge.schemas.enums import ArtifactType

    outline = state.report_outline
    if outline is None or not outline.sections:
        return _fail(
            state,
            FailureType.QUALITY_GATE_FAILURE,
            "repair_report",
            "cannot repair report: empty outline (no sections to rebuild)",
        )
    if not any(text.strip() for text in state.section_texts.values()):
        return _fail(
            state,
            FailureType.QUALITY_GATE_FAILURE,
            "repair_report",
            "cannot repair report: empty section_texts (no drafted content)",
        )

    title = state.problem_card.title if state.problem_card else "Modeling Report"
    # build_markdown drops unverified/illegal [claim:id] refs and strips leaked
    # internal claim ids; build_latex re-renders a structurally valid document.
    markdown, claim_map = deps.report_builder.build_markdown(
        title, outline, state.section_texts, state.evidence_claims, state.citations
    )
    latex_source = deps.report_builder.build_latex(title, markdown, state.citations)

    md_art = deps.registry.register_text(
        state.run_id, ArtifactType.REPORT_MARKDOWN, "report.md", markdown
    )
    tex_art = deps.registry.register_text(
        state.run_id, ArtifactType.REPORT_LATEX, "report.tex", latex_source
    )
    state.report_artifacts = ReportArtifacts(
        markdown_artifact_id=md_art.artifact_id,
        latex_artifact_id=tex_art.artifact_id,
        claim_map=claim_map,
    )
    state.failure_state = None
    _log.info(
        "report repair: rebuilt markdown+latex for run %s (revision %d)",
        state.run_id,
        state.budget_state.paper_revision_count,
    )
    return RunStatus.RUNNING_JUDGE_PANEL


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


def _experiment_source_artifacts(record: ExperimentRecord) -> list[str]:
    return list(
        dict.fromkeys(
            [
                *record.output_artifact_ids,
                *record.table_artifact_ids,
                *record.figure_artifact_ids,
                *record.log_artifact_ids,
            ]
        )
    )


def _source_map_for_subproblem(subproblem: SubProblem | None) -> list[SourceReference]:
    if subproblem is not None and subproblem.source is not None:
        return [subproblem.source]
    return []


def _group_claims_by_subproblem(
    claims: list[EvidenceClaim],
) -> dict[str, list[EvidenceClaim]]:
    grouped: dict[str, list[EvidenceClaim]] = {}
    for claim in claims:
        if claim.subproblem_id:
            grouped.setdefault(claim.subproblem_id, []).append(claim)
    return grouped


def _run_method_fit_gate(state: ModelingState) -> str:
    if state.problem_card is None or state.selected_strategy is None:
        return ""
    gate = MethodFitGate()
    reports = []
    subproblems = state.problem_card.subproblems or []
    if not subproblems:
        return ""
    available = (
        [f.normalized_name for f in state.input_manifest.files]
        if state.input_manifest
        else []
    )
    for subproblem in subproblems:
        reports.append(
            gate.evaluate(
                state.problem_card,
                subproblem,
                state.selected_strategy,
                available_input_files=available,
                method_library_hits=state.retrieved_methods,
            )
        )
        route = state.subproblem_selected_routes.get(subproblem.sub_id)
        if route is not None:
            reports.append(
                gate.evaluate(
                    state.problem_card,
                    subproblem,
                    route,
                    available_input_files=available,
                    method_library_hits=state.retrieved_methods,
                )
            )
    state.method_fit_reports = reports
    failed = [r for r in reports if not r.passed]
    if not failed:
        return ""
    worst = sorted(failed, key=lambda r: r.score)[0]
    return (
        f"method-fit failed for {worst.subproblem_id or 'global'} "
        f"candidate={worst.candidate_id} score={worst.score}: "
        + "; ".join(worst.issues)
    )


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
