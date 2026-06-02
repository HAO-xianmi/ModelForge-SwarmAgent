"""Phase G: CLI tests using Typer's CliRunner (mock LLM, real sandbox)."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    monkeypatch.setenv("MODELFORGE_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'cli.db').as_posix()}")
    monkeypatch.setenv("MODELFORGE_LLM", "mock")
    from modelforge.common import config

    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_doctor_runs(cli_env) -> None:
    from modelforge.cli.main import app

    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Doctor" in result.stdout
    assert "python_version" in result.stdout


def test_init_and_create_run(cli_env) -> None:
    from modelforge.cli.main import app

    assert runner.invoke(app, ["init"]).exit_code == 0
    result = runner.invoke(app, ["create-run", "--profile", "practice"])
    assert result.exit_code == 0
    assert "Created run" in result.stdout


def test_status_unknown_run(cli_env) -> None:
    from modelforge.cli.main import app

    result = runner.invoke(app, ["status", "run_does_not_exist"])
    assert result.exit_code == 1


def test_create_upload_start_flow(cli_env, tmp_path) -> None:
    from modelforge.cli.main import app

    runner.invoke(app, ["init"])
    create = runner.invoke(app, ["create-run", "--profile", "practice"])
    # Extract run id from output.
    run_id = next(w for w in create.stdout.split() if w.startswith("run_"))

    csv = tmp_path / "data.csv"
    csv.write_text(
        "f0,f1,target\n" + "\n".join(f"{i * 0.1},{i * 0.2},{i * 0.5}" for i in range(40)) + "\n"
    )
    problem = tmp_path / "problem.txt"
    problem.write_text("Forecast target from features. Report RMSE.")

    up = runner.invoke(app, ["upload", run_id, str(problem), str(csv)])
    assert up.exit_code == 0, up.stdout

    start = runner.invoke(app, ["start", run_id])
    assert start.exit_code == 0
    assert "COMPLETED" in start.stdout

    status = runner.invoke(app, ["status", run_id])
    assert status.exit_code == 0
    assert "COMPLETED" in status.stdout

    arts = runner.invoke(app, ["artifacts", run_id])
    assert arts.exit_code == 0
    assert "REPORT_MARKDOWN" in arts.stdout


def test_demo_command(cli_env) -> None:
    from modelforge.cli.main import app

    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0
    assert "Run completed" in result.stdout
    assert "Reproducibility bundle" in result.stdout
