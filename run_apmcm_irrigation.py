"""Run APMCM 2025 A (agricultural irrigation) through ModelForge-Swarm.

This runner is intentionally thin: it uploads prepared input artifacts and then
lets the framework's agents, sandbox, evidence registry, and report writer do
the work. API keys are read from the environment/.env and are never persisted by
this script.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table


ROOT = Path(__file__).resolve().parent
INPUT_DIR = ROOT / "examples" / "apmcm_irrigation"
INPUT_FILES = [
    "problem.txt",
    "problem.pdf",
    "aa_irrigation_model_data.csv",
    "soil_moisture_daily.csv",
    "weather_daily_features.csv",
]


def configure_environment() -> None:
    load_dotenv(ROOT / ".env", override=False)
    os.environ.setdefault("MODELFORGE_LLM", "openai")
    os.environ.setdefault("OPENAI_BASE_URL", "https://api.deepseek.com")
    os.environ.setdefault("MODELFORGE_SANDBOX", "subprocess")
    # Force the model requested for this test run while leaving the key external.
    os.environ["MODELFORGE_LLM_MODEL"] = "deepseek-v4-flash"


def masked_key() -> str:
    key = os.environ.get("OPENAI_API_KEY", "")
    if len(key) <= 12:
        return "(missing)" if not key else "(set)"
    return f"{key[:8]}...{key[-4:]}"


def main() -> int:
    configure_environment()

    from modelforge.common.config import get_settings
    from modelforge.graph.coordinator import RunCoordinator, default_database
    from modelforge.providers.llm.base import Message
    from modelforge.providers.llm.factory import get_llm_provider
    from modelforge.schemas.enums import CheckpointAction, RunStatus
    from modelforge.services.ingestion import UploadedFile

    get_settings.cache_clear()
    console = Console()
    console.print(
        Panel.fit(
            "[bold cyan]APMCM 2025 A Agricultural Irrigation[/bold cyan]\n"
            "[white]ModelForge-Swarm multi-agent workflow x DeepSeek-compatible API[/white]",
            title="ModelForge Run",
            border_style="cyan",
        )
    )

    config = Table(title="Runtime Config", show_header=False, box=None)
    config.add_row("LLM backend", os.environ.get("MODELFORGE_LLM", ""))
    config.add_row("Model", os.environ.get("MODELFORGE_LLM_MODEL", ""))
    config.add_row("Base URL", os.environ.get("OPENAI_BASE_URL", ""))
    config.add_row("API key", masked_key())
    config.add_row("Input dir", str(INPUT_DIR))
    console.print(config)

    missing = [name for name in INPUT_FILES if not (INPUT_DIR / name).exists()]
    if missing:
        console.print(f"[red]Missing prepared input file(s):[/red] {missing}")
        return 2

    console.print("\n[cyan]Step 1[/cyan] LLM connectivity check")
    provider = get_llm_provider()
    ping = provider.complete(
        [Message(role="user", content="用一句中文确认连接成功，只输出这句话。")],
        max_tokens=64,
        temperature=0.0,
    )
    console.print(
        f"[green]LLM OK[/green] model={ping.model} latency={ping.latency_ms}ms "
        f"tokens={ping.usage.input_tokens}/{ping.usage.output_tokens}"
    )

    console.print("\n[cyan]Step 2[/cyan] Create run and upload files")
    db = default_database()
    coord = RunCoordinator(db)
    run = coord.create_run(
        mode="practice",
        competition_profile="apmcm",
        budget_profile="standard",
    )
    uploads = [
        UploadedFile(filename=name, data=(INPUT_DIR / name).read_bytes())
        for name in INPUT_FILES
    ]
    state = coord.add_files(run.run_id, uploads)
    console.print(
        f"[green]Created run[/green] {run.run_id}; uploaded "
        f"{len(state.input_manifest.files) if state.input_manifest else 0} files"
    )

    console.print("\n[cyan]Step 3[/cyan] Run workflow with automatic checkpoint approvals")
    start = time.time()
    max_iterations = 30
    for i in range(max_iterations):
        state = coord.start(run.run_id)
        console.print(f"  iteration {i + 1}: status={state.status.value}")
        if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            break
        if state.pending_checkpoint is not None:
            cp = state.pending_checkpoint
            console.print(f"    approving checkpoint={cp.kind.value} id={cp.checkpoint_id}")
            state = coord.resolve_checkpoint(
                run.run_id,
                cp.checkpoint_id,
                CheckpointAction.APPROVE,
                comments="Auto-approved by run_apmcm_irrigation.py for framework test.",
            )
            console.print(f"    after approval status={state.status.value}")
            if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
                break
    else:
        console.print("[yellow]Maximum iterations reached before terminal status.[/yellow]")

    elapsed = time.time() - start
    summary = Table(title="Run Summary", show_header=False, box=None)
    summary.add_row("run_id", run.run_id)
    summary.add_row("status", state.status.value)
    summary.add_row("elapsed_seconds", f"{elapsed:.1f}")
    summary.add_row(
        "tokens_in/out",
        f"{state.budget_state.input_tokens}/{state.budget_state.output_tokens}",
    )
    summary.add_row("estimated_cost_usd", f"{state.budget_state.estimated_cost_usd:.6f}")
    summary.add_row("verified_claims", str(len(state.verified_claims())))
    summary.add_row(
        "bundle_path",
        state.export_state.bundle_path if state.export_state else "",
    )
    if state.failure_state:
        summary.add_row("failure", state.failure_state.detail)
    console.print(summary)

    return 0 if state.status is RunStatus.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
