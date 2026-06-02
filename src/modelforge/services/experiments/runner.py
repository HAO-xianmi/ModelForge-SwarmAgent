"""Experiment runner + tracker (spec 9.4 / 20).

Given a CodeArtifact and the run's input data, this:
  * builds an isolated workspace under ``runs/{run_id}/experiments/{exp_id}``,
  * executes it via the selected SandboxRunner (real run),
  * records reproducibility metadata (seed, input hash, dependencies, runtime),
  * registers output files (figures -> figures/, tables -> tables/, metrics ->
    metrics/, logs -> logs/) as immutable artifacts,
  * returns a populated :class:`ExperimentRecord` whose metrics came ONLY from
    the executed code.

It also drives the bounded debug loop (spec 8.8 / 20.5): on failure it asks a
debugger callable for a minimal patch and retries, up to a configured cap.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from modelforge.common.config import get_settings
from modelforge.common.hashing import hash_bytes, hash_text
from modelforge.common.ids import new_experiment_id
from modelforge.common.logging import get_logger
from modelforge.schemas.enums import ArtifactType, ExperimentStatus, ExperimentType, SandboxStatus
from modelforge.schemas.experiment import (
    CodeArtifact,
    DebugPatch,
    ExperimentRecord,
    SandboxResult,
)
from modelforge.services.sandbox.base import SandboxRequest, SandboxRunner
from modelforge.services.sandbox.factory import select_sandbox_runner
from modelforge.services.sandbox.workspace import prepare_workspace
from modelforge.storage.repositories.artifact_registry import ArtifactRegistry

_log = get_logger("modelforge.experiments")

# A debugger takes (code, sandbox_result, attempt) and returns a patched
# CodeArtifact + a DebugPatch, or None to give up.
DebuggerFn = Callable[[CodeArtifact, SandboxResult, int], "tuple[CodeArtifact, DebugPatch] | None"]

# Figures vs tables collected from sandbox output by extension.
_FIGURE_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
_TABLE_EXTS = {".csv", ".tsv"}


class ExperimentRunner:
    def __init__(
        self,
        registry: ArtifactRegistry,
        runner: SandboxRunner | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner or select_sandbox_runner()

    # ------------------------------------------------------------------ #
    def run(
        self,
        run_id: str,
        code: CodeArtifact,
        *,
        experiment_type: ExperimentType,
        input_files: dict[str, bytes] | None = None,
        timeout_seconds: int | None = None,
        seed: int | None = None,
        debugger: DebuggerFn | None = None,
        max_debug_retries: int | None = None,
        train_test_split: bool = False,
    ) -> ExperimentRecord:
        settings = get_settings()
        experiment_id = new_experiment_id()
        seed = seed if seed is not None else code.seed
        timeout = timeout_seconds or settings.sandbox_timeout
        max_retries = (
            max_debug_retries if max_debug_retries is not None else settings.max_debug_retries
        )
        inputs = input_files or {}
        input_hash = hash_bytes(b"".join(sorted(inputs.values()))) if inputs else ""

        workspace = self._workspace(run_id, experiment_id)

        record = ExperimentRecord(
            experiment_id=experiment_id,
            run_id=run_id,
            strategy_id=code.strategy_id,
            experiment_type=experiment_type,
            seed=seed,
            code_artifact_id=code.code_artifact_id,
            input_manifest_hash=input_hash,
            dependencies=list(code.dependencies),
            sandbox_backend=self.runner.backend_name,
            train_test_split=train_test_split,
            leakage_checked=train_test_split,
        )

        current_code = code
        result: SandboxResult | None = None
        for attempt in range(max_retries + 1):
            prepare_workspace(workspace, current_code, inputs)
            result = self.runner.run(
                SandboxRequest(
                    run_id=run_id,
                    workspace=workspace,
                    entrypoint=current_code.entrypoint,
                    timeout_seconds=timeout,
                    seed=seed,
                )
            )
            if result.status is SandboxStatus.SUCCEEDED:
                break
            if attempt >= max_retries or debugger is None:
                break
            patched = debugger(current_code, result, attempt + 1)
            if patched is None:
                break
            current_code, patch = patched
            record.debug_patches.append(patch)
            _log.info(
                "debug attempt %d for experiment %s: %s",
                attempt + 1,
                experiment_id,
                patch.reason,
            )

        assert result is not None
        self._finalize(record, current_code, result, workspace)
        return record

    # ------------------------------------------------------------------ #
    def _finalize(
        self,
        record: ExperimentRecord,
        code: CodeArtifact,
        result: SandboxResult,
        workspace: Path,
    ) -> None:
        record.runtime_seconds = result.runtime_seconds
        record.metrics = dict(result.metrics)

        if result.status is SandboxStatus.SUCCEEDED:
            record.status = ExperimentStatus.SUCCEEDED
        elif result.status is SandboxStatus.TIMED_OUT:
            record.status = ExperimentStatus.FAILED
            record.failure_reason = "timed out"
        elif result.status is SandboxStatus.POLICY_BLOCKED:
            record.status = ExperimentStatus.FAILED
            record.failure_reason = f"policy blocked: {result.policy_block_reason}"
        else:
            record.status = ExperimentStatus.FAILED
            record.failure_reason = _short_error(result.stderr)

        # Register the code artifact itself (entrypoint) for provenance.
        main_file = code.file("main.py")
        main_content = main_file.content if main_file else ""
        self.registry.register_text(
            record.run_id,
            ArtifactType.SCRIPT,
            f"{record.experiment_id}_main.py",
            main_content,
            experiment_id=record.experiment_id,
            metadata={"code_hash": hash_text(main_content)} if main_content else {},
        )
        # Dependency lock.
        self.registry.register_text(
            record.run_id,
            ArtifactType.DEPENDENCY_LOCK,
            f"{record.experiment_id}_requirements.txt",
            "\n".join(code.dependencies) + "\n",
            experiment_id=record.experiment_id,
        )
        # Logs.
        log_text = f"# stdout\n{result.stdout}\n\n# stderr\n{result.stderr}\n"
        log_art = self.registry.register_text(
            record.run_id,
            ArtifactType.EXECUTION_LOG,
            f"{record.experiment_id}_execution.log",
            log_text,
            experiment_id=record.experiment_id,
        )
        record.log_artifact_ids.append(log_art.artifact_id)

        # Output files -> figures / tables / metrics.
        output_dir = workspace / "output"
        for rel in result.output_files:
            path = output_dir / rel
            if not path.exists():
                continue
            ext = path.suffix.lower()
            data = path.read_bytes()
            if ext in _FIGURE_EXTS:
                art = self.registry.register_bytes(
                    record.run_id, ArtifactType.FIGURE, path.name, data,
                    experiment_id=record.experiment_id,
                )
                record.figure_artifact_ids.append(art.artifact_id)
            elif ext in _TABLE_EXTS:
                art = self.registry.register_bytes(
                    record.run_id, ArtifactType.TABLE, path.name, data,
                    experiment_id=record.experiment_id,
                )
                record.table_artifact_ids.append(art.artifact_id)
            elif path.name == "metrics.json":
                art = self.registry.register_bytes(
                    record.run_id, ArtifactType.METRICS_FILE, path.name, data,
                    experiment_id=record.experiment_id,
                )
                record.output_artifact_ids.append(art.artifact_id)

    def _workspace(self, run_id: str, experiment_id: str) -> Path:
        base = (get_settings().runs_path / run_id / "experiments" / experiment_id).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base


def _short_error(stderr: str) -> str:
    lines = [ln for ln in stderr.strip().splitlines() if ln.strip()]
    return lines[-1] if lines else "execution failed"
