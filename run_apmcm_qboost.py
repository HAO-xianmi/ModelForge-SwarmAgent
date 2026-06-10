"""
APMCM 2025 C题 演示脚本
=======================
通过 ModelForge-Swarm Agent (使用 DeepSeek LLM) 求解 QBoost 二分类问题。

运行方式:
    python run_apmcm_qboost.py

环境要求:
    - .env 已配置 OPENAI_API_KEY=sk-... 及 OPENAI_BASE_URL=https://api.deepseek.com
    - pip install -e ".[dev,science]"
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# ── 强制从项目根加载 .env ──────────────────────────────────────────────────
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path, override=True)

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ── 验证配置 ──────────────────────────────────────────────────────────────
console.print(Panel.fit(
    "[bold cyan]APMCM 2025 C题[/bold cyan]\n"
    "[white]基于 Quantum Boosting (QBoost) 的二分类模型[/white]\n"
    "[dim]ModelForge-Swarm Agent x DeepSeek LLM[/dim]",
    title="ModelForge Demo",
    border_style="cyan",
))

llm_backend = os.environ.get("MODELFORGE_LLM", "mock")
llm_model = os.environ.get("MODELFORGE_LLM_MODEL", "")
api_key = os.environ.get("OPENAI_API_KEY", "")
base_url = os.environ.get("OPENAI_BASE_URL", "")

config_table = Table(title="当前配置", show_header=False, box=None, padding=(0, 2))
config_table.add_row("[bold]LLM Backend[/bold]", llm_backend)
config_table.add_row("[bold]Model[/bold]", llm_model or "(provider default)")
config_table.add_row("[bold]Base URL[/bold]", base_url or "(default)")
config_table.add_row("[bold]API Key[/bold]", f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "(not set)")
config_table.add_row("[bold]Sandbox[/bold]", os.environ.get("MODELFORGE_SANDBOX", "auto"))
console.print(config_table)

# ── 快速连接测试 ──────────────────────────────────────────────────────────
console.print("\n[cyan]Step 1:[/cyan] 测试 LLM 连接...")
try:
    # Clear the lru_cache so settings reload from env
    from modelforge.common.config import get_settings
    get_settings.cache_clear()

    from modelforge.providers.llm.factory import get_llm_provider
    from modelforge.providers.llm.base import Message

    provider = get_llm_provider()
    ping_resp = provider.complete(
        [Message(role="user", content="请用一句中文确认你已连接成功，格式：「已连接，模型：{model_name}」")],
        max_tokens=64,
        temperature=0.0,
    )
    console.print(f"[green]✓ LLM连接成功[/green] — {ping_resp.text.strip()}")
    console.print(f"  延迟: {ping_resp.latency_ms}ms | 模型: {ping_resp.model} | 估算费用: ${ping_resp.estimated_cost:.5f}")
except Exception as e:
    console.print(f"[red]✗ LLM连接失败: {e}[/red]")
    console.print("[yellow]将回退到 Mock LLM (离线模式)[/yellow]")
    os.environ["MODELFORGE_LLM"] = "mock"
    from modelforge.common.config import get_settings
    get_settings.cache_clear()

# ── 初始化 ModelForge 运行 ────────────────────────────────────────────────
console.print("\n[cyan]Step 2:[/cyan] 初始化 ModelForge 运行...")
from modelforge.graph.coordinator import RunCoordinator, default_database
from modelforge.schemas.enums import CheckpointAction, RunStatus
from modelforge.services.ingestion import UploadedFile

db = default_database()
db.create_all()
coord = RunCoordinator(db)

run = coord.create_run(
    mode="practice",
    competition_profile="apmcm",
    budget_profile="standard",
)
console.print(f"[green]✓ 创建运行[/green] run_id={run.run_id}")

# ── 加载题目文件 ──────────────────────────────────────────────────────────
console.print("\n[cyan]Step 3:[/cyan] 加载 APMCM C题题目...")
problem_dir = Path(__file__).parent / "examples" / "apmcm_qboost"
uploads: list[UploadedFile] = []
for fname in ("problem.txt",):
    fpath = problem_dir / fname
    if fpath.exists():
        uploads.append(UploadedFile(filename=fname, data=fpath.read_bytes()))
        console.print(f"  + {fname} ({fpath.stat().st_size} bytes)")

coord.add_files(run.run_id, uploads)
console.print(f"[green]✓ 题目已加载[/green] ({len(uploads)} 个文件)")

# ── 运行 Agent 工作流 ─────────────────────────────────────────────────────
console.print("\n[cyan]Step 4:[/cyan] 启动 ModelForge Agent 工作流...")
console.print("[dim]Agent将依次执行: 题目解析 → 策略规划 → 代码生成 → 沙箱执行 → 结果分析 → 报告生成[/dim]\n")

MAX_ITERATIONS = 10
state = None
t_start = time.time()

for iteration in range(MAX_ITERATIONS):
    try:
        if state is None:
            state = coord.start(run.run_id)

        status = state.status.value
        console.print(f"  [yellow]迭代 {iteration+1}/{MAX_ITERATIONS}[/yellow] | 状态: [bold]{status}[/bold]", end="")

        if state.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            console.print()
            break

        if state.pending_checkpoint is not None:
            cp = state.pending_checkpoint
            console.print(f" | 检查点: [magenta]{cp.kind.value}[/magenta] → 自动审批")
            state = coord.resolve_checkpoint(
                run.run_id,
                cp.checkpoint_id,
                CheckpointAction.APPROVE,
                comments="Auto-approved by APMCM demo runner",
            )
        else:
            console.print(f" | 继续执行...")
            state = coord.start(run.run_id)

    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断[/yellow]")
        break
    except Exception as exc:
        console.print(f"\n[red]错误: {exc}[/red]")
        import traceback
        traceback.print_exc()
        break

elapsed = time.time() - t_start

# ── 结果展示 ──────────────────────────────────────────────────────────────
console.print(f"\n[cyan]Step 5:[/cyan] 运行结果\n")

if state is None:
    console.print("[red]运行未能启动[/red]")
    sys.exit(1)

final_status = state.status.value
status_color = "green" if state.status is RunStatus.COMPLETED else "red"

result_table = Table(title="ModelForge 运行摘要", show_header=False, box=None, padding=(0, 2))
result_table.add_row("[bold]运行ID[/bold]", run.run_id)
result_table.add_row("[bold]最终状态[/bold]", f"[{status_color}]{final_status}[/{status_color}]")
result_table.add_row("[bold]耗时[/bold]", f"{elapsed:.1f}s")
result_table.add_row("[bold]LLM调用[/bold]", str(len(state.model_call_log) if hasattr(state, "model_call_log") else "-"))

if state.experiment_records:
    for rec in state.experiment_records:
        if rec.metrics:
            result_table.add_row(f"[bold]{rec.experiment_type.value} 指标[/bold]", str(rec.metrics))

verified = state.verified_claims() if hasattr(state, "verified_claims") else []
result_table.add_row("[bold]已验证声明[/bold]", str(len(verified)))

if state.export_state and state.export_state.bundle_path:
    result_table.add_row("[bold]产出包[/bold]", str(state.export_state.bundle_path))

console.print(result_table)

# ── 沙箱执行结果 ──────────────────────────────────────────────────────────
if state.experiment_records:
    console.print("\n[bold]实验执行记录:[/bold]")
    for i, rec in enumerate(state.experiment_records, 1):
        exp_type = rec.experiment_type.value
        console.print(f"\n  [{i}] {exp_type} | status={rec.status.value} | {rec.runtime_seconds:.1f}s")
        if rec.code_artifact_id:
            console.print(f"      代码制品: {rec.code_artifact_id}")
        if rec.metrics:
            console.print(f"      指标: {rec.metrics}")
        if rec.failure_reason:
            console.print(f"      [red]失败原因: {rec.failure_reason}[/red]")

# ── 问题解析结果 ──────────────────────────────────────────────────────────
if state.problem_card is not None:
    console.print("\n[bold]题目解析:[/bold]")
    pc = state.problem_card
    if pc.problem_summary:
        console.print(f"  摘要: {pc.problem_summary[:200]}")
    if pc.objectives:
        console.print(f"  目标 ({len(pc.objectives)}个): {', '.join(str(o) for o in pc.objectives[:3])}")
    if pc.subproblems:
        console.print(f"  子问题 ({len(pc.subproblems)}个): {', '.join(sp.sub_id for sp in pc.subproblems)}")

# ── 最终提示 ──────────────────────────────────────────────────────────────
console.print()
if state.status is RunStatus.COMPLETED:
    console.print(Panel.fit(
        "[green bold]APMCM C题演示完成[/green bold]\n\n"
        "ModelForge Agent 已成功:\n"
        "  [+] 解析题目 (QBoost 二分类)\n"
        "  [+] 规划建模策略 (QUBO 转化)\n"
        "  [+] 生成并执行代码 (模拟退火求解)\n"
        "  [+] 评估模型性能 (accuracy/F1)\n"
        "  [+] 生成分析报告\n\n"
        f"[dim]总耗时: {elapsed:.1f}s[/dim]",
        border_style="green",
    ))
else:
    console.print(Panel.fit(
        f"[yellow]运行结束，状态: {final_status}[/yellow]\n\n"
        "[dim]提示: 如遇网络问题可设置 MODELFORGE_LLM=mock 使用离线模式[/dim]",
        border_style="yellow",
    ))

# ── 直接执行 QBoost 脚本展示核心结果 ─────────────────────────────────────
console.print("\n" + "─" * 70)
console.print("[cyan bold]直接执行 QBoost 核心算法 (展示数学建模结果):[/cyan bold]")
console.print("─" * 70 + "\n")

import subprocess
result = subprocess.run(
    [sys.executable, str(problem_dir / "qboost_solution.py")],
    capture_output=False,
    text=True,
    cwd=str(problem_dir),
)
if result.returncode != 0:
    console.print(f"[red]QBoost脚本执行失败 (exit code {result.returncode})[/red]")
