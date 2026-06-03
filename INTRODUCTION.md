# Project Introduction | 项目介绍

## English

### Overview

ModelForge-Swarm is an auditable multi-agent copilot for mathematical modeling.
It is built for a simple but demanding goal:

> help users move from an open-ended modeling problem to a reproducible,
> evidence-grounded, reviewable solution workflow.

Instead of treating "multi-agent" as a chat gimmick, this project treats it as
an engineering control problem. The system is structured around a typed shared
state, a workflow driver, deterministic execution services, and explicit human
checkpoints.

That means the project is not mainly about agents "speaking well". It is about:

- whether the task was understood clearly,
- whether alternative strategies were actually compared,
- whether code really ran,
- whether reported metrics came from execution,
- whether final writing stayed inside verified evidence boundaries,
- whether the whole process can be audited later.

### What makes it different

Many AI workflow demos look impressive in screenshots but become difficult to
trust when you ask deeper questions:

- Where did this number come from?
- Was this conclusion supported by an actual experiment?
- Did the system test a baseline?
- What happened when the first generated solution failed?
- Can we replay the run and inspect the artifacts?

ModelForge-Swarm is designed around those questions.

Its answer is a workflow with:

- typed state,
- bounded retries,
- evidence registration,
- claim verification,
- checkpoint-based control,
- reproducibility bundles,
- audit events for meaningful state changes.

### Intended audiences

This repository is useful for several groups:

#### 1. Students and teams in mathematical modeling

They can use it to practice structured problem solving, compare strategies,
generate first-pass analysis code, and produce a more reproducible record of
their work.

#### 2. Instructors and mentors

They can use it to teach:

- structured decomposition of modeling tasks,
- method selection tradeoffs,
- experiment discipline,
- evidence-aware writing,
- transparent AI assistance.

#### 3. Engineers building agent systems

They can use this repository as a reference for:

- typed shared-blackboard orchestration,
- audit-friendly workflow design,
- sandboxed code execution pipelines,
- integrating LLM reasoning into deterministic systems safely.

#### 4. Researchers studying controlled autonomy

The codebase is a practical example of how to combine:

- agent-style reasoning,
- deterministic service layers,
- safety constraints,
- reproducibility requirements,
- human-in-the-loop governance.

### Design philosophy

The project follows a few strong principles.

#### Reasoning and execution should be separated

Language models are useful for proposing, critiquing, and structuring ideas.
They are not trusted as the source of final quantitative truth. Real execution
and deterministic validation are handled by other parts of the system.

#### Reports should be downstream of evidence

A polished narrative is not enough. If a claim cannot be tied to verified
evidence, it should not appear as a factual statement in the final report.

#### Agent autonomy should be bounded, not romanticized

Retries, debugging loops, and workflow transitions are capped and governed.
This prevents the system from drifting into uncontrolled behavior.

#### Auditability is a product feature, not a debugging afterthought

State changes, artifacts, checkpoints, and outputs should remain inspectable so
that users can understand not only the final answer, but how the system reached
it.

### Example: what a run looks like

Imagine a user uploads:

- `problem.txt`
- `data.csv`

The system may proceed roughly like this:

1. Parse the problem and classify it as prediction, optimization, graph
   analysis, or another family.
2. Profile the uploaded data and flag quality concerns.
3. Retrieve relevant modeling methods from the library.
4. Generate several strategy candidates with different goals.
5. Critique those strategies with a skeptic role.
6. Run pilot experiments for candidate approaches.
7. Select one strategy based on observed pilot evidence.
8. Generate runnable code and execute it in the sandbox.
9. Run baselines and robustness checks.
10. Register verified evidence claims.
11. Draft a report structure and write evidence-constrained prose.
12. Export a reproducibility bundle with code, logs, metrics, figures, and manifests.

### Example output value

At the end of a successful run, you do not only get prose. You can also get:

- experiment metrics,
- generated code,
- logs,
- evidence records,
- citations,
- report markdown,
- LaTeX output,
- optional PDF,
- reproducibility ZIP bundle,
- audit history.

That makes the system more useful for serious iteration, review, and teaching.

### Practical note

The repository already supports local zero-key execution using a deterministic
mock provider. This makes it suitable for:

- local development,
- test-driven iteration,
- demos,
- classroom environments,
- offline architectural validation.

Real OpenAI or Anthropic providers can be enabled later through environment
configuration.

### Summary

ModelForge-Swarm is best understood as a reproducibility-first multi-agent
modeling system. It is not just trying to generate answers. It is trying to
generate workflows, artifacts, and reports that remain inspectable and
defensible after the run is over.

---

## 中文

### 概述

ModelForge-Swarm 是一个面向数学建模的、可审计、可复现、可控的多智能体协作系统。
它的目标很明确：

> 把一道开放式建模题，从题面输入推进到“有真实实验、有证据约束、有人工检查点、
> 有完整导出结果”的工程化流程。

这个项目并不把“多智能体”理解成几个 Agent 聊天，而是把它当成一个
**工程控制问题** 来做：

- 状态必须结构化
- 角色必须边界清晰
- 指标必须来自真实运行
- 报告必须受证据约束
- 自动化必须可暂停、可审批、可追踪

### 它和普通 Agent Demo 有什么不同？

很多 AI Demo 看起来很厉害，但一追问就会暴露问题：

- 这个数字是从哪来的？
- 这个结论有没有跑实验验证？
- 有没有 baseline？
- 第一版代码失败以后系统做了什么？
- 能不能复盘整个过程？

ModelForge-Swarm 的设计核心，就是让这些问题都有答案。

它通过以下机制来保证这一点：

- 类型化共享状态
- 有边界的重试与调试循环
- 证据注册与 claim 校验
- 基于检查点的人机协同
- 可导出的复现包
- 关键状态变化的审计事件记录

### 适合谁使用？

#### 1. 数学建模训练者和竞赛团队

可以把它当成一个有约束的建模协作助手，用来：

- 梳理题目
- 对比方法
- 生成初版代码
- 留下更完整的实验与报告记录

#### 2. 教师、导师、课程设计者

可以把它当成教学工具，用于展示：

- 如何结构化拆解题目
- 为什么策略选择不能只靠直觉
- 为什么 baseline 和 robustness 很重要
- 为什么报告写作不能脱离证据
- AI 辅助系统如何做到透明

#### 3. 多智能体系统工程师

这个仓库也是一个很好的工程参考，用于研究：

- 类型化共享黑板协作
- 可审计工作流编排
- 沙箱代码执行链路
- 如何把 LLM 推理安全接入确定性系统

#### 4. 研究受控自治系统的研究者

如果你关注的是“如何让 AI 自动化既有能力又有边界”，这个项目提供了一个
实际的实现样本：

- 有推理
- 有执行
- 有验证
- 有约束
- 有人工治理点

### 设计哲学

#### 推理和执行要分开

LLM 适合做分析、提案、批判、组织表达，但不应该直接充当最终定量事实来源。
真正的执行、检验和导出要交给确定性组件。

#### 报告应该是证据的下游产物

最终文稿不是“写得像”就够了。如果某个结论没有对应到已验证证据，就不应该被
当成事实写进报告。

#### 自动化必须有边界

调试循环、重试次数、工作流转移、预算消耗都应该被限制和记录，而不是无边界地
自动尝试。

#### 可审计性本身就是产品能力

很多系统只在出错时才想起日志，而这个项目把“可复盘、可检查、可解释过程”视为
一等能力。

### 一个典型运行流程

假设用户上传：

- `problem.txt`
- `data.csv`

系统可能会依次完成：

1. 解析题目并判断属于预测、优化、图分析等哪一类问题。
2. 对数据做质量画像与结构分析。
3. 从方法库里检索可能适用的方法。
4. 生成多种策略候选。
5. 由 skeptic 角色对策略做质疑与挑错。
6. 对候选策略做试跑实验。
7. 根据试跑结果选择正式路线。
8. 生成可运行代码并放入沙箱执行。
9. 跑 baseline 和稳健性分析。
10. 注册经过验证的证据 claim。
11. 基于证据规划报告结构并写作。
12. 导出包含代码、日志、指标、图表、清单文件的复现包。

### 最终会得到什么？

一次成功运行结束后，用户拿到的不只是几段文字，还包括：

- 实验指标
- 生成代码
- 执行日志
- 证据记录
- 引用信息
- markdown 报告
- LaTeX 输出
- 可选 PDF
- 可复现 ZIP 包
- 审计历史

这让项目更适合真实迭代、教学复盘和系统研究，而不只是演示效果。

### 一个很实用的点

当前仓库已经支持 **无 API Key 的本地运行模式**，通过确定性的 mock provider
就可以完成：

- 本地开发
- 自动化测试
- 教学演示
- 离线架构验证

后续如果需要，也可以再切换到真实的 OpenAI 或 Anthropic provider。

### 总结

ModelForge-Swarm 最适合被理解为一个 **以可复现性为优先级的多智能体建模系统**。
它不仅想“生成答案”，更想生成一套在运行结束之后依然可以检查、复盘、辩护的
工作流、证据链和结果包。
