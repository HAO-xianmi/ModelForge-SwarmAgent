"""Sandbox runner selection (spec 5 mode + 34 deployment).

``select_sandbox_runner`` honors the configured backend; ``auto`` picks Docker
when the daemon is reachable, otherwise the subprocess runner. ``modelforge
doctor`` surfaces which backend is active.
"""

from __future__ import annotations

import subprocess

from modelforge.common.config import SandboxBackend, get_settings
from modelforge.common.logging import get_logger
from modelforge.services.sandbox.base import SandboxRunner
from modelforge.services.sandbox.docker_runner import DockerSandboxRunner, docker_cli_present
from modelforge.services.sandbox.subprocess_runner import SubprocessSandboxRunner

_log = get_logger("modelforge.sandbox")


def docker_available() -> bool:
    """True if the Docker CLI exists AND the daemon responds to ``docker info``."""
    if not docker_cli_present():
        return False
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        return proc.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def select_sandbox_runner(backend: SandboxBackend | None = None) -> SandboxRunner:
    chosen = backend or get_settings().sandbox
    if chosen is SandboxBackend.DOCKER:
        return DockerSandboxRunner()
    if chosen is SandboxBackend.SUBPROCESS:
        return SubprocessSandboxRunner()
    # AUTO
    if docker_available():
        _log.info("sandbox: using Docker backend")
        return DockerSandboxRunner()
    _log.info("sandbox: Docker unavailable, using subprocess backend")
    return SubprocessSandboxRunner()
