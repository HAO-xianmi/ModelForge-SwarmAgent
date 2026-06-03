# ModelForge-SwarmAgent

> Bilingual GitHub project page for `ModelForge-Swarm`
>
> `ModelForge-SwarmAgent` is the public repository name. The runnable Python package,
> CLI command, and source namespace in this project remain `modelforge-swarm` /
> `modelforge`.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![Frontend](https://img.shields.io/badge/Web-Next.js-black.svg)](https://nextjs.org/)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-MVP%20Complete-success.svg)](IMPLEMENTATION_STATUS.md)

## Quick Links

- Chinese project guide: [README.zh-CN.md](README.zh-CN.md)
- Bilingual extended introduction: [INTRODUCTION.md](INTRODUCTION.md)
- Implementation status: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)

## English

### What is this?

**ModelForge-Swarm** is an auditable multi-agent copilot for mathematical modeling.
It helps turn a problem statement into a reproducible modeling workflow with:

- problem parsing and domain analysis,
- multi-strategy proposal and critique,
- real code generation and sandbox execution,
- evidence registration and citation checks,
- report drafting with human checkpoints,
- full run history and audit trails.

This repository is designed for people building or studying:

- AI-assisted mathematical modeling systems,
- competition-support tooling,
- reproducible experiment pipelines,
- multi-agent reasoning workflows with strict control boundaries.

It is a **stateful engineering system**, not a free-form chat between agents.
Language models are used for reasoning. Anything that must be reproducible is
handled by deterministic services and tracked in structured state.

### One-sentence positioning

From problem statement to reproducible model report, with checkpoints, evidence,
and an auditable workflow.

### Why this project matters

Many "agent" demos can talk convincingly but cannot prove where numbers came
from, whether code was truly executed, or whether the final report is grounded
in verified evidence. ModelForge-Swarm is built to solve exactly that gap.

Its core design principles are:

- **Evidence before prose**: report writers can only use verified claims.
- **Real execution before metrics**: quantitative results must come from actual sandbox runs.
- **Bounded autonomy**: retries, loops, budgets, and escalations are explicit.
- **Human checkpoints**: key decisions are paused for review when needed.
- **Full auditability**: state changes and artifacts are tracked end to end.

### Key features

#### 1. Multi-agent reasoning with clear role boundaries

The system includes specialized agents such as:

- Problem Parser
- Domain Analyst
- Method Retriever
- Strategy Proposers
- Skeptic
- Strategy Judge
- Code Author
- Debugger
- Paper Architect
- Paper Writer

These agents do not operate as an uncontrolled chat swarm. They communicate
through a typed shared blackboard and a workflow driver.

#### 2. Deterministic services for reproducible work

Critical steps are implemented as deterministic services, including:

- ingestion and file sanitation,
- data profiling,
- method-library retrieval,
- code template generation,
- sandbox execution,
- experiment management,
- baseline and robustness analysis,
- evidence registration,
- citation validation,
- compliance checks,
- report and bundle export.

#### 3. Real experiments, not invented metrics

The system runs generated code in a sandbox and collects structured outputs such
as metrics, logs, figures, and artifacts. The final report is built from those
verified outputs instead of fabricated performance claims.

#### 4. Multiple interfaces

The project already includes:

- a Typer CLI,
- a FastAPI backend,
- a Next.js web console,
- deterministic example workflows,
- test coverage across unit, integration, and end-to-end paths.

### Typical workflow

```text
ingest -> parse -> analyze -> checkpoint
       -> retrieve methods -> propose strategies -> critique -> pilot runs
       -> select strategy -> profile data -> generate code -> run sandbox
       -> debug if needed -> baseline -> robustness -> audit
       -> register evidence -> structure report -> draft report
       -> verify citations -> checkpoint -> export bundle
```

### Architecture at a glance

```text
User Interfaces   -> CLI / REST API / Web Console
Control Plane     -> Workflow driver / checkpoints / budgets / loop guards
Shared Blackboard -> Typed ModelingState as the single source of truth
Agents            -> Reasoning-only, bounded, structured outputs
Services          -> Deterministic execution, evidence, compliance, export
Storage / Infra   -> SQLite/Postgres / object store / run directory / sandbox
```

### Repository status

The MVP implementation is complete in this workspace.

- Full phase status: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- Architecture notes: [docs/architecture/overview.md](docs/architecture/overview.md)
- Workflow detail: [docs/architecture/workflow.md](docs/architecture/workflow.md)
- API reference: [docs/api/README.md](docs/api/README.md)
- Deployment notes: [docs/deployment/README.md](docs/deployment/README.md)
- Validation summary: [FINAL_VALIDATION_REPORT.md](FINAL_VALIDATION_REPORT.md)

Current status snapshot:

- 7 implementation phases completed
- 136 tests passing
- CLI, API, frontend, examples, and export pipeline implemented
- Mock LLM mode available for zero-key local runs

### Quick start

#### Option A: zero external dependencies

This is the easiest way to try the project locally.

```bash
pip install -e ".[dev,science]"
python -m modelforge.cli.main doctor
python -m modelforge.cli.main demo
```

This mode uses:

- SQLite
- subprocess sandbox
- deterministic mock LLM

No Docker, no Postgres, and no API key are required.

#### Option B: install the CLI entrypoint

```bash
pip install -e ".[dev,science]"
modelforge doctor
modelforge demo
```

### Enable real providers and infrastructure

Optional environment settings:

```ini
MODELFORGE_LLM=openai
OPENAI_API_KEY=sk-...

# or
MODELFORGE_LLM=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# or
MODELFORGE_LLM=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# optional
MODELFORGE_SANDBOX=docker
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
```

### CLI usage examples

#### Example 1: run the built-in demo

```bash
modelforge demo
```

Expected outcome:

- creates a deterministic example run,
- executes real experiment code,
- produces verified claims,
- exports a reproducibility bundle.

#### Example 2: create a new run from your own files

```bash
modelforge init
modelforge create-run --profile practice
modelforge upload <run_id> problem.txt data.csv
modelforge start <run_id>
modelforge status <run_id>
modelforge artifacts <run_id>
modelforge export <run_id> --out bundle.zip
```

#### Example 3: contest-like checkpoint flow

```bash
modelforge checkpoints <run_id>
modelforge resolve-checkpoint <run_id> <checkpoint_id> APPROVE
```

This is useful when a human reviewer needs to approve strategy selection,
problem understanding, or final output.

### REST API example

Start the backend:

```bash
python -m uvicorn modelforge.api.main:app --port 8000
```

Then create and start a run:

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "content-type: application/json" \
  -d "{\"mode\":\"practice\",\"competition_profile_id\":\"practice\"}"
```

Upload files:

```bash
curl -X POST http://localhost:8000/api/v1/runs/<run_id>/files \
  -F files=@problem.txt \
  -F files=@data.csv
```

Start the workflow:

```bash
curl -X POST http://localhost:8000/api/v1/runs/<run_id>/start
```

### Example scenarios

#### Scenario A: mathematical modeling competition practice

You provide:

- a problem statement,
- one or more CSV/XLSX/TXT/PDF files,
- a competition profile such as `practice` or `mcm_icm`.

The system can help:

- identify the task family,
- compare candidate modeling strategies,
- run pilots and baselines,
- generate a reproducible draft report,
- keep a trackable audit history.

#### Scenario B: teaching reproducible modeling

An instructor can use this system to demonstrate:

- how to move from narrative problem statements to structured tasks,
- why baselines and robustness checks matter,
- how evidence should support report writing,
- how audit logs improve transparency in AI-assisted work.

#### Scenario C: research prototype for controlled multi-agent systems

This codebase is suitable for studying:

- typed shared-state orchestration,
- bounded agent autonomy,
- verification-aware reporting,
- reproducibility pipelines for AI-generated code.

### Project structure

```text
src/modelforge/
  agents/        reasoning agents
  api/           FastAPI backend
  cli/           Typer CLI
  common/        config, ids, hashing, logging, errors
  graph/         workflow driver and coordinator
  providers/     mock / OpenAI / Anthropic providers
  schemas/       typed domain contracts
  services/      deterministic execution services
  storage/       database, repositories, artifacts, run directories

apps/web/        Next.js web console
examples/        deterministic end-to-end examples
docs/            architecture, API, deployment
tests/           unit + integration + e2e coverage
```

### Safety and boundaries

This project is intentionally designed with constraints:

- it is not a hidden autonomous contest submission bot,
- it does not treat agent text as trusted ground truth,
- it does not allow report claims to bypass evidence checks,
- it uses bounded retries and policy checks instead of unlimited agent loops.

Final responsibility remains with the human user.

### Development commands

```bash
pip install -e ".[dev,science]"
make lint
make type
make test
make api
make web
```

### Frontend

The web console lives in `apps/web`.

```bash
cd apps/web
npm install
npm run dev
```

Main pages include:

- run dashboard,
- workflow graph,
- evidence explorer,
- methods page,
- benchmark overview.

### Deployment

For a production-like local stack:

```bash
docker compose up --build
```

This brings up:

- PostgreSQL,
- Redis,
- FastAPI backend,
- sandbox image build flow.

See [docs/deployment/README.md](docs/deployment/README.md) for details.

### Documentation map

- [README.zh-CN.md](README.zh-CN.md) - Chinese illustrated guide
- [INTRODUCTION.md](INTRODUCTION.md) - extended bilingual project introduction
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - completion status by phase
- [DECISIONS.md](DECISIONS.md) - architecture and implementation decisions
- [docs/architecture/overview.md](docs/architecture/overview.md) - architecture summary
- [docs/architecture/workflow.md](docs/architecture/workflow.md) - workflow detail
- [docs/api/README.md](docs/api/README.md) - API endpoints
- [examples/README.md](examples/README.md) - example walkthroughs

### License

Apache-2.0. See [LICENSE](LICENSE).

---

## 中文

### 这是什么项目？

**ModelForge-Swarm** 是一个面向数学建模的、可审计的多智能体协作系统。
它的目标不是“让几个 Agent 聊一聊”，而是把一道建模题从题目输入一路推进到
**可复现实验、可追踪证据、可导出报告** 的完整流程。

它可以帮助你完成：

- 题目解析与任务分类
- 领域分析与方法检索
- 多策略生成、对比与质疑
- 真实代码生成与沙箱执行
- 基线实验、稳健性实验与审计检查
- 证据注册、引用校验与报告草稿生成
- 人工检查点审批与全流程审计留痕

### 一句话介绍

从题目描述到可复现建模报告，用多智能体协作完成，但每一步都有状态、证据、约束和审计记录。

### 为什么这个项目有价值？

很多 Agent 项目“会说”，但不会证明：

- 指标是不是跑出来的，
- 代码是不是实际执行过，
- 报告里的结论是不是基于真实证据，
- 多轮自动修复是不是可控的。

ModelForge-Swarm 的设计重点恰好就是这些问题：

- **先有证据，再写结论**
- **先真实执行，再谈指标**
- **自动化必须有边界**
- **关键节点允许人工审批**
- **全过程可追踪、可复盘**

### 核心特性

#### 1. 多智能体分工明确

系统内置多个职责明确的角色，例如：

- Problem Parser（题目解析）
- Domain Analyst（领域分析）
- Method Retriever（方法检索）
- Strategy Proposers（多策略生成）
- Skeptic（质疑与挑错）
- Strategy Judge（策略评审）
- Code Author（代码生成）
- Debugger（受限修复）
- Paper Architect（报告结构规划）
- Paper Writer（基于证据写作）

这些角色并不是自由聊天，而是通过 **类型化共享黑板** 和 **工作流控制器**
进行协作。

#### 2. 可复现步骤由确定性服务完成

凡是必须保证可复现、可校验的部分，都由确定性服务负责，例如：

- 文件摄取与安全清洗
- 数据画像分析
- 方法库检索
- 代码模板生成
- 沙箱执行
- 实验调度
- 基线与稳健性分析
- 证据与引用管理
- 合规检查
- 报告与可复现包导出

#### 3. 强调真实实验，而不是“编指标”

系统会把代码放到沙箱里真实运行，收集：

- metrics
- logs
- figures
- 产物文件
- 审计事件

最终报告只能使用已经校验通过的 claim，避免“看起来像结果，其实没跑过”的问题。

#### 4. 提供多种使用入口

当前仓库已经包含：

- Typer CLI
- FastAPI 后端
- Next.js Web 控制台
- 示例数据与示例流程
- 单元测试、集成测试、端到端测试

### 典型工作流

```text
导入题目 -> 解析题目 -> 分析任务 -> 人工检查点
        -> 检索方法 -> 生成多种策略 -> 质疑评审 -> 试跑实验
        -> 选择策略 -> 数据画像 -> 生成代码 -> 沙箱执行
        -> 必要时调试 -> 跑基线 -> 做稳健性分析 -> 审计检查
        -> 注册证据 -> 规划报告 -> 撰写报告 -> 校验引用
        -> 人工检查点 -> 导出可复现结果包
```

### 架构概览

```text
用户接口层      -> CLI / REST API / Web 控制台
控制平面        -> 工作流驱动 / 检查点 / 预算 / 循环保护
共享黑板        -> 类型化 ModelingState，作为唯一真实状态源
智能体层        -> 只负责推理，不直接替代可复现执行
确定性服务层    -> 实验、证据、合规、导出等
存储与基础设施层 -> SQLite/Postgres / 对象存储 / 运行目录 / 沙箱
```

### 当前完成度

本工作区中的 MVP 已完成，当前状态包括：

- 7 个阶段实现完成
- 136 项测试通过
- CLI / API / 前端 / 示例 / 导出链路都已具备
- 支持无 API Key 的本地 Mock 模式

详细说明见：

- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)
- [FINAL_VALIDATION_REPORT.md](FINAL_VALIDATION_REPORT.md)

### 快速开始

#### 方案 A：零外部依赖体验

```bash
pip install -e ".[dev,science]"
python -m modelforge.cli.main doctor
python -m modelforge.cli.main demo
```

这一模式默认使用：

- SQLite
- 本地 subprocess 沙箱
- 确定性的 mock LLM

不需要：

- Docker
- PostgreSQL
- OpenAI / Anthropic API Key

#### 方案 B：直接使用 CLI 命令

```bash
pip install -e ".[dev,science]"
modelforge doctor
modelforge demo
```

### 开启真实模型或生产式基础设施

可选环境变量如下：

```ini
MODELFORGE_LLM=openai
OPENAI_API_KEY=sk-...

# 或者
MODELFORGE_LLM=anthropic
ANTHROPIC_API_KEY=sk-ant-...

# 或者
MODELFORGE_LLM=deepseek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1

# 可选
MODELFORGE_SANDBOX=docker
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname
```

### CLI 示例

#### 示例 1：直接运行内置 Demo

```bash
modelforge demo
```

运行后会得到：

- 一个完整 run
- 真实执行得到的实验指标
- 已验证证据
- 可导出的复现包

#### 示例 2：对你自己的题目启动流程

```bash
modelforge init
modelforge create-run --profile practice
modelforge upload <run_id> problem.txt data.csv
modelforge start <run_id>
modelforge status <run_id>
modelforge artifacts <run_id>
modelforge export <run_id> --out bundle.zip
```

#### 示例 3：带人工审批的流程

```bash
modelforge checkpoints <run_id>
modelforge resolve-checkpoint <run_id> <checkpoint_id> APPROVE
```

这适合用于：

- 教学场景
- 竞赛训练场景
- 需要人工确认策略选择的场景

### API 示例

启动后端：

```bash
python -m uvicorn modelforge.api.main:app --port 8000
```

创建 run：

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "content-type: application/json" \
  -d "{\"mode\":\"practice\",\"competition_profile_id\":\"practice\"}"
```

上传文件：

```bash
curl -X POST http://localhost:8000/api/v1/runs/<run_id>/files \
  -F files=@problem.txt \
  -F files=@data.csv
```

启动流程：

```bash
curl -X POST http://localhost:8000/api/v1/runs/<run_id>/start
```

### 适用场景举例

#### 场景 A：数学建模竞赛训练

你提供：

- 题目文本
- 数据文件
- 指定竞赛配置

系统可以帮助你：

- 识别问题类型
- 比较多种建模路线
- 进行试验、基线和稳健性验证
- 生成可复盘的报告草稿
- 沉淀完整审计记录

#### 场景 B：课堂教学与科研训练

教师或学生可以利用本项目演示：

- 如何把自然语言题目转换为结构化建模任务
- 为什么 baseline 和 robustness 很重要
- 为什么报告结论必须来自真实证据
- AI 辅助系统如何做到透明可追踪

#### 场景 C：多智能体系统研究原型

如果你关心的是系统研究，本仓库也很适合作为：

- 类型化共享状态协作范式的实验平台
- 受约束 Agent 工作流的参考实现
- 面向可验证报告生成的研究原型
- AI 代码生成与复现实验链路的工程样板

### 项目结构

```text
src/modelforge/
  agents/        智能体角色
  api/           FastAPI 后端
  cli/           命令行入口
  common/        配置、日志、ID、错误等通用模块
  graph/         工作流驱动与协调器
  providers/     mock / OpenAI / Anthropic 接入
  schemas/       类型化领域模型
  services/      确定性服务
  storage/       数据库、仓库层、产物管理、运行目录

apps/web/        Next.js Web 控制台
examples/        可直接运行的示例
docs/            架构、API、部署文档
tests/           单元 / 集成 / 端到端测试
```

### 安全边界与约束

这个项目的设计是有意识地“收紧边界”的：

- 它不是偷偷替你全自动提交竞赛答案的黑盒机器人
- 它不会把 Agent 文本当成天然可信结果
- 它不会允许报告跳过证据校验
- 它不会无限制地自动循环修复

最终决策责任依然在使用者手里。

### 开发命令

```bash
pip install -e ".[dev,science]"
make lint
make type
make test
make api
make web
```

### 前端界面

前端位于 `apps/web`：

```bash
cd apps/web
npm install
npm run dev
```

当前主要页面包括：

- 运行总览页
- Workflow Graph
- Evidence Explorer
- Methods 页面
- Benchmark 总览页

### 部署方式

如果你希望拉起接近生产的本地环境：

```bash
docker compose up --build
```

会启动：

- PostgreSQL
- Redis
- FastAPI 后端
- 沙箱镜像构建流程

详细见 [docs/deployment/README.md](docs/deployment/README.md)。

### 文档索引

- [README.zh-CN.md](README.zh-CN.md) - 中文图文说明入口
- [INTRODUCTION.md](INTRODUCTION.md) - 独立的中英双语项目介绍
- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - 分阶段完成情况
- [DECISIONS.md](DECISIONS.md) - 设计决策记录
- [docs/architecture/overview.md](docs/architecture/overview.md) - 架构概览
- [docs/architecture/workflow.md](docs/architecture/workflow.md) - 工作流细节
- [docs/api/README.md](docs/api/README.md) - API 文档
- [examples/README.md](examples/README.md) - 示例说明

### 许可证

Apache-2.0，详见 [LICENSE](LICENSE)。
