"""Sandbox execution (spec 9.3 / 20.3-20.5).

Public surface:
    SandboxRunner     — the Protocol all runners implement.
    SandboxRequest    — a structured execution request.
    SubprocessSandboxRunner — local execution with resource/time/path limits.
    DockerSandboxRunner     — isolated container execution (spec §20).
    select_sandbox_runner   — auto-select based on settings + Docker availability.
"""

from modelforge.services.sandbox.base import SandboxRequest, SandboxRunner
from modelforge.services.sandbox.docker_runner import DockerSandboxRunner
from modelforge.services.sandbox.factory import docker_available, select_sandbox_runner
from modelforge.services.sandbox.subprocess_runner import SubprocessSandboxRunner

__all__ = [
    "DockerSandboxRunner",
    "SandboxRequest",
    "SandboxRunner",
    "SubprocessSandboxRunner",
    "docker_available",
    "select_sandbox_runner",
]
