"""Experiment orchestration (spec 9.4 / 18 / 20 / 21).

Ties together code generation, the sandbox, and the artifact registry to run
real experiments and capture full reproducibility metadata. Everything here
operates on the outputs of the SandboxRunner — no metric is ever invented.
"""

from modelforge.services.experiments.auditor import ExperimentAuditor
from modelforge.services.experiments.baselines import BaselineRunner
from modelforge.services.experiments.pilots import PilotService
from modelforge.services.experiments.robustness import RobustnessRunner
from modelforge.services.experiments.runner import ExperimentRunner

__all__ = [
    "BaselineRunner",
    "ExperimentAuditor",
    "ExperimentRunner",
    "PilotService",
    "RobustnessRunner",
]
