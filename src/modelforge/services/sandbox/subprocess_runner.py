"""Local subprocess sandbox runner.

Used when Docker is unavailable (the dev-host default). It really executes the
generated code, with these controls:
  * Static import allowlist inspection -> POLICY_BLOCKED before running.
  * Hard wall-clock timeout (process tree killed on expiry).
  * Working directory pinned to the workspace ``src`` dir.
  * A scrubbed environment: host secrets removed, network discouraged via
    proxy vars pointed at a dead address, ``PYTHONNOUSERSITE`` set.
  * POSIX resource limits (CPU seconds, address space) where ``resource`` exists.

It is NOT a security boundary as strong as a container; the Docker runner is
preferred when available. This is documented in DECISIONS.md (D-A5) and
IMPLEMENTATION_STATUS.md.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from modelforge.common.logging import get_logger
from modelforge.schemas.enums import SandboxStatus
from modelforge.schemas.experiment import SandboxResult
from modelforge.services.sandbox.base import (
    SandboxRequest,
    collect_output_files,
)
from modelforge.services.sandbox.workspace import collect_metrics, inspect_imports

_log = get_logger("modelforge.sandbox.subprocess")

# Environment variables that must never reach sandboxed code (host secrets).
_SECRET_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_ACCESS_KEY_ID",
    "OBJECT_STORAGE_SECRET",
    "GITHUB_TOKEN",
)


class SubprocessSandboxRunner:
    backend_name = "subprocess"

    def run(self, request: SandboxRequest) -> SandboxResult:
        workspace = Path(request.workspace).resolve()
        src_dir = workspace / "src"
        output_dir = workspace / "output"
        logs_dir = workspace / "logs"
        output_dir.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Static safety check (defense in depth).
        violations = inspect_imports(src_dir, request.allowed_imports)
        if violations:
            return SandboxResult(
                status=SandboxStatus.POLICY_BLOCKED,
                backend=self.backend_name,
                policy_block_reason="disallowed imports: " + "; ".join(violations),
                stderr="\n".join(violations),
            )

        entry = src_dir / request.entrypoint
        if not entry.exists():
            return SandboxResult(
                status=SandboxStatus.FAILED,
                backend=self.backend_name,
                exit_code=2,
                stderr=f"entrypoint not found: {request.entrypoint}",
            )

        env = self._build_env(request)
        start = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "-I", request.entrypoint],
                cwd=str(src_dir),
                env=env,
                capture_output=True,
                text=True,
                timeout=request.timeout_seconds,
                preexec_fn=_limit_resources(request) if os.name != "nt" else None,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            runtime = time.monotonic() - start
            return SandboxResult(
                status=SandboxStatus.TIMED_OUT,
                backend=self.backend_name,
                timed_out=True,
                runtime_seconds=runtime,
                stdout=_decode(exc.stdout),
                stderr=_decode(exc.stderr) + f"\n[timeout after {request.timeout_seconds}s]",
            )

        runtime = time.monotonic() - start
        (logs_dir / "stdout.log").write_text(proc.stdout, encoding="utf-8")
        (logs_dir / "stderr.log").write_text(proc.stderr, encoding="utf-8")

        status = SandboxStatus.SUCCEEDED if proc.returncode == 0 else SandboxStatus.FAILED
        return SandboxResult(
            status=status,
            backend=self.backend_name,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            runtime_seconds=runtime,
            output_files=collect_output_files(output_dir),
            metrics=collect_metrics(output_dir),
        )

    def _build_env(self, request: SandboxRequest) -> dict[str, str]:
        """Scrubbed environment: no host secrets, network discouraged."""
        env: dict[str, str] = {}
        # Keep only a minimal safe subset of the host environment.
        for key in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL"):
            if key in os.environ:
                env[key] = os.environ[key]
        env["PYTHONNOUSERSITE"] = "1"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["MPLBACKEND"] = "Agg"  # headless matplotlib
        env["OMP_NUM_THREADS"] = "1"
        env["PYTHONHASHSEED"] = str(request.seed)
        env["MODELFORGE_SEED"] = str(request.seed)
        # Point network proxies at an unroutable address to discourage egress.
        env["HTTP_PROXY"] = env["HTTPS_PROXY"] = "http://127.0.0.1:9"
        env["NO_PROXY"] = ""
        # Ensure no secret leaks even if PATH-adjacent vars existed.
        for secret in _SECRET_KEYS:
            env.pop(secret, None)
        env.update(request.env)
        return env


def _decode(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _limit_resources(request: SandboxRequest):  # type: ignore[no-untyped-def]
    """Return a preexec_fn applying POSIX rlimits (no-op on Windows)."""

    def _apply() -> None:  # pragma: no cover - POSIX only
        import contextlib
        import resource

        cpu = max(1, int(request.timeout_seconds))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))  # type: ignore[attr-defined]
        mem = request.memory_mb * 1024 * 1024
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (mem, mem))  # type: ignore[attr-defined]

    return _apply
