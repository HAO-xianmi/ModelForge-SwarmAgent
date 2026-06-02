"""Phase D: sandbox runner tests — REAL subprocess execution.

These prove that code genuinely runs and that the safety controls work; no
results are faked. Docker-backend behavior is covered by separate
``requires_docker`` tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from modelforge.common.ids import new_run_id
from modelforge.schemas.enums import SandboxStatus
from modelforge.schemas.experiment import CodeArtifact, CodeFile
from modelforge.services.sandbox import SubprocessSandboxRunner
from modelforge.services.sandbox.base import SandboxRequest
from modelforge.services.sandbox.workspace import inspect_imports, prepare_workspace


def _request(workspace: Path, **kw) -> SandboxRequest:
    return SandboxRequest(run_id=new_run_id(), workspace=workspace, **kw)


def _write(workspace: Path, code: str, filename: str = "main.py") -> None:
    artifact = CodeArtifact(
        code_artifact_id="c1",
        strategy_id="s1",
        files=[CodeFile(filename=filename, content=code)],
        entrypoint=filename,
    )
    prepare_workspace(workspace, artifact, {})


def test_successful_execution_with_metrics(tmp_path: Path) -> None:
    code = (
        "import json, pathlib\n"
        "x = sum(range(10))\n"
        "print('result', x)\n"
        "out = pathlib.Path('../output'); out.mkdir(exist_ok=True)\n"
        "(out / 'metrics.json').write_text(json.dumps({'total': x, 'nested': {'mae': 0.5}}))\n"
    )
    _write(tmp_path, code)
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.SUCCEEDED
    assert result.exit_code == 0
    assert "result 45" in result.stdout
    assert result.metrics["total"] == 45.0
    assert result.metrics["nested.mae"] == 0.5
    assert "metrics.json" in result.output_files


def test_syntax_error_fails_not_raises(tmp_path: Path) -> None:
    _write(tmp_path, "def broken(:\n    pass\n")
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.FAILED
    assert result.exit_code != 0
    assert "SyntaxError" in result.stderr


def test_runtime_error_captured(tmp_path: Path) -> None:
    _write(tmp_path, "raise ValueError('boom')\n")
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.FAILED
    assert "ValueError: boom" in result.stderr


def test_timeout(tmp_path: Path) -> None:
    _write(tmp_path, "import time\nwhile True:\n    time.sleep(0.05)\n")
    result = SubprocessSandboxRunner().run(_request(tmp_path, timeout_seconds=1))
    assert result.status is SandboxStatus.TIMED_OUT
    assert result.timed_out is True


def test_disallowed_import_policy_blocked(tmp_path: Path) -> None:
    # `socket` is not in the allowlist -> blocked before execution.
    _write(tmp_path, "import socket\nprint('should not run')\n")
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.POLICY_BLOCKED
    assert "socket" in (result.policy_block_reason or "")


def test_allowed_science_import_runs(tmp_path: Path) -> None:
    _write(tmp_path, "import numpy as np\nprint('mean', float(np.mean([1,2,3])))\n")
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.SUCCEEDED
    assert "mean 2.0" in result.stdout


def test_missing_entrypoint(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    result = SubprocessSandboxRunner().run(_request(tmp_path, entrypoint="nope.py"))
    assert result.status is SandboxStatus.FAILED
    assert "entrypoint not found" in result.stderr


def test_import_inspector_flags_relative_only_top_level(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("import os\nimport requests\nfrom . import b\n")
    violations = inspect_imports(src, frozenset({"os"}))
    assert any("requests" in v for v in violations)
    assert all("import os" not in v for v in violations)
    # relative imports (level>0) are not flagged
    assert all("from . import" not in v for v in violations)


@pytest.mark.security
def test_secrets_not_in_sandbox_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-should-not-leak")
    code = (
        "import os, json, pathlib\n"
        "leaked = os.environ.get('OPENAI_API_KEY', 'ABSENT')\n"
        "out = pathlib.Path('../output'); out.mkdir(exist_ok=True)\n"
        "flag = 1 if leaked != 'ABSENT' else 0\n"
        "(out / 'metrics.json').write_text(json.dumps({'leaked': flag}))\n"
        "print('leaked', leaked)\n"
    )
    _write(tmp_path, code)
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    assert result.status is SandboxStatus.SUCCEEDED
    assert "sk-secret-should-not-leak" not in result.stdout
    assert result.metrics.get("leaked") == 0.0


@pytest.mark.security
def test_path_traversal_write_stays_in_workspace(tmp_path: Path) -> None:
    # Code that tries to write outside the workspace: the OS may allow it, but
    # our collected outputs only include files under output/. We assert the
    # escape file is not registered as an output and execution is observable.
    sentinel = tmp_path / "escaped.txt"
    code = (
        f"import pathlib\n"
        f"try:\n"
        f"    pathlib.Path(r'{sentinel.as_posix()}').write_text('escaped')\n"
        f"except Exception as e:\n"
        f"    print('blocked', e)\n"
        f"print('done')\n"
    )
    _write(tmp_path, code)
    result = SubprocessSandboxRunner().run(_request(tmp_path))
    # Whatever the OS did, escaped.txt is never in collected output_files.
    assert "escaped.txt" not in result.output_files
    assert all("escaped" not in f for f in result.output_files)
