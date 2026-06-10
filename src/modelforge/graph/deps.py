"""Dependency bundle for the workflow.

Groups the registries, services, and the LLM provider the workflow nodes need,
so nodes stay thin and testable. Construct once per run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from modelforge.agents.base import AgentContext
from modelforge.common.config import Settings, get_settings
from modelforge.providers.llm import get_llm_provider
from modelforge.providers.llm.base import LLMProvider
from modelforge.services.citations import CitationRegistry
from modelforge.services.codegen import CodeGenerator
from modelforge.services.compliance import ComplianceEngine
from modelforge.services.evaluation import JudgePanel
from modelforge.services.evidence import EvidenceRegistry
from modelforge.services.experiments import (
    BaselineRunner,
    ExperimentAuditor,
    ExperimentRunner,
    PilotService,
    RobustnessRunner,
)
from modelforge.services.exporters import BundleExporter
from modelforge.services.ingestion import IngestionService
from modelforge.services.profiling import DataProfiler
from modelforge.services.report import LatexBuilder, ReportBuilder
from modelforge.services.sandbox.base import SandboxRunner
from modelforge.services.sandbox.factory import select_sandbox_runner
from modelforge.storage.database import Database
from modelforge.storage.repositories import ArtifactRegistry, RunRepository


@dataclass
class WorkflowDeps:
    """Everything the workflow nodes need."""

    db: Database
    run_repo: RunRepository
    registry: ArtifactRegistry
    provider: LLMProvider
    compliance: ComplianceEngine
    settings: Settings = field(default_factory=get_settings)
    sandbox: SandboxRunner | None = None

    # Lazily-built services (populated in __post_init__).
    ingestion: IngestionService = field(init=False)
    profiler: DataProfiler = field(init=False)
    codegen: CodeGenerator = field(init=False)
    experiment_runner: ExperimentRunner = field(init=False)
    pilots: PilotService = field(init=False)
    baselines: BaselineRunner = field(init=False)
    robustness: RobustnessRunner = field(init=False)
    auditor: ExperimentAuditor = field(init=False)
    evidence: EvidenceRegistry = field(init=False)
    judge_panel: JudgePanel = field(init=False)
    citations: CitationRegistry = field(init=False)
    report_builder: ReportBuilder = field(init=False)
    latex: LatexBuilder = field(init=False)
    exporter: BundleExporter = field(init=False)

    def __post_init__(self) -> None:
        self.sandbox = self.sandbox or select_sandbox_runner()
        self.ingestion = IngestionService(self.registry)
        self.profiler = DataProfiler()
        self.codegen = CodeGenerator()
        self.experiment_runner = ExperimentRunner(self.registry, self.sandbox)
        self.pilots = PilotService(self.experiment_runner, self.codegen)
        self.baselines = BaselineRunner(self.experiment_runner, self.codegen)
        self.robustness = RobustnessRunner(self.experiment_runner, self.codegen)
        self.auditor = ExperimentAuditor()
        self.evidence = EvidenceRegistry()
        self.judge_panel = JudgePanel()
        self.citations = CitationRegistry()
        self.report_builder = ReportBuilder()
        self.latex = LatexBuilder()
        self.exporter = BundleExporter(self.registry)

    def agent_context(self, run_id: str) -> AgentContext:
        return AgentContext(run_id=run_id, provider=self.provider)

    @classmethod
    def build(
        cls,
        db: Database,
        compliance: ComplianceEngine,
        *,
        provider: LLMProvider | None = None,
        sandbox: SandboxRunner | None = None,
    ) -> WorkflowDeps:
        registry = ArtifactRegistry(db)
        return cls(
            db=db,
            run_repo=RunRepository(db),
            registry=registry,
            provider=provider or get_llm_provider(),
            compliance=compliance,
            sandbox=sandbox,
        )
