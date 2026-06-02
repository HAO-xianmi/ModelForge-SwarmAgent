"""Docker sandbox runner (spec section 20).

Runs the entrypoint inside a container with the full set of spec controls:
non-root user, read-only input mount, writable output/logs, CPU/memory limits,
``--network none``, a runtime timeout, and captured stdout/stderr/exit code.

This uses the ``docker`` CLI (no Python SDK dependency). It is implemented in
full but, on a host without Docker, cannot be *executed* — see
IMPLEMENTATION_STATUS.md (marked 🚫). The subprocess runner is used instead.
Tests for this runner are marked ``requires_docker``.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from modelforge.common.config import get_settings
from modelforge.common.logging import get_logger
from modelforge.schemas.enums import SandboxStatus
from modelforge.schemas.experiment import SandboxResult
from modelforge.services.sandbox.base import SandboxRequest, collect_output_files
from modelforge.services.sandbox.workspace import collect_metrics, inspect_imports

_log = get_logger("modelforge.sandbox.docker")


class DockerSandboxRunner:
    backend_name = "docker"

    def __init__(self, image: str | None = None, docker_bin: str = "docker") -> None:
        self.image = image or get_settings().sandbox_image
        self.docker_bin = docker_bin

    def run(self, request: SandboxRequest) -> SandboxResult:
        workspace = Path(request.workspace).resolve()
        src_dir = workspace / "src"
        output_dir = workspace / "output"
        logs_dir = workspace / "logs"
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        violations = inspect_imports(src_dir, request.allowed_imports)
        if violations:
            return SandboxResult(
                status=SandboxStatus.POLICY_BLOCKED,
                backend=self.backend_name,
                policy_block_reason="disallowed imports: " + "; ".join(violations),
                stderr="\n".join(violations),
            )

        cmd = self._build_command(request, workspace)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds + 15,  # grace over the in-container limit
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            runtime = time.monotonic() - start
            self._force_remove(_container_name(request))
            return SandboxResult(
                status=SandboxStatus.TIMED_OUT,
                backend=self.backend_name,
                timed_out=True,
                runtime_seconds=runtime,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=f"[docker timeout after {request.timeout_seconds}s]",
            )

        runtime = time.monotonic() - start
        (logs_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8")
        (logs_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")

        # Docker timeout inside the container surfaces as exit code 124.
        if proc.returncode == 124:
            status = SandboxStatus.TIMED_OUT
            timed_out = True
        elif proc.returncode == 0:
            status = SandboxStatus.SUCCEEDED
            timed_out = False
        else:
            status = SandboxStatus.FAILED
            timed_out = False

        return SandboxResult(
            status=status,
            backend=self.backend_name,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            runtime_seconds=runtime,
            timed_out=timed_out,
            output_files=collect_output_files(output_dir),
            metrics=collect_metrics(output_dir),
        )

    def _build_command(self, request: SandboxRequest, workspace: Path) -> list[str]:
        """Assemble the hardened ``docker run`` command (spec 20.4)."""
        name = _container_name(request)
        # In-container wall clock via coreutils `timeout`; the entrypoint runs
        # with `-I` (isolated) and a fixed seed.
        in_container = (
            f"timeout {request.timeout_seconds} "
            f"python -I /workspace/src/{request.entrypoint}"
        )
        return [
            self.docker_bin,
            "run",
            "--rm",
            "--name",
            name,
            "--network",
            "none",  # spec: restrict outbound network
            "--user",
            "1000:1000",  # spec: non-root
            "--read-only",  # root fs read-only; only mounts are writable
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "256",
            "--memory",
            f"{request.memory_mb}m",
            "--memory-swap",
            f"{request.memory_mb}m",
            "--cpus",
            str(request.cpu),
            "--tmpfs",
            "/tmp:rw,size=64m",
            "-v",
            f"{workspace / 'input'}:/workspace/input:ro",  # read-only data
            "-v",
            f"{workspace / 'src'}:/workspace/src:ro",
            "-v",
            f"{workspace / 'output'}:/workspace/output:rw",
            "-v",
            f"{workspace / 'logs'}:/workspace/logs:rw",
            "-w",
            "/workspace/src",
            "-e",
            "MPLBACKEND=Agg",
            "-e",
            f"PYTHONHASHSEED={request.seed}",
            "-e",
            f"MODELFORGE_SEED={request.seed}",
            self.image,
            "bash",
            "-lc",
            in_container,
        ]

    def _force_remove(self, name: str) -> None:
        try:
            subprocess.run(
                [self.docker_bin, "rm", "-f", name],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (subprocess.SubprocessError, OSError):
            _log.warning("failed to remove container %s", name)


def _container_name(request: SandboxRequest) -> str:
    return f"mf-sbx-{request.run_id[-8:]}-{int(time.time() * 1000) % 100000}"


def docker_cli_present() -> bool:
    return shutil.which("docker") is not None
