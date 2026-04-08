---
title: "PolyHarness — 产品开发文档 / Product Development"
date: 2026-04-02
status: draft
version: "0.1.0"
---

# PolyHarness — 产品开发文档 / Product Development

## 1. 产品愿景

**PolyHarness 的目标是帮助现有 AI agent 持续迭代——让 Claude Code、Claw Code、Codex 等 agent 在你的任务上通过自动搜索寻找更合适的 harness 配置，减少手动调参。**

**PolyHarness aims to help existing AI agents iterate more systematically — enabling Claude Code, Claw Code, Codex, and similar agents to search for better task-specific harness configurations with less manual tuning.**

核心命题：Meta-Harness 论文证明了 "harness 设计是 agent 性能的主要杠杆"，且 harness 可以被自动搜索算法优化。当前论文只开源了最终产物（agent.py），未开源搜索框架本身。PolyHarness 填补这一空白，并将其产品化为 agent 开发者的标配工具。

Core proposition: The Meta-Harness paper proved that "harness design is the primary lever for agent performance" and that harnesses can be optimized via automated search. The paper only released the final artifact (agent.py), not the search framework itself. PolyHarness fills this gap and productizes it as a standard tool for agent developers.

### 1.0 项目决策原则（冻结）

根据当前阶段的产品目标，项目遵循以下四条不可偏离原则：

1. **产品优先**：先交付可安装、可运行的 CLI 产品，面向 agent 开发者和广泛用户，而非论文式一次性脚本。
2. **生态优先**：核心能力不绑定单一 Agent 代码库，作为 agent 生态的通用优化层存在。
3. **自动进化 + 研究验证并重**：主线价值是让现有 agent 能通过自动搜索持续迭代；同时支持 Meta-Harness 论文的复现与扩展实验。
4. **多后端优先，深度定制后置**：主线支持 Claude Code/Claw Code/Codex/OpenCode 等多后端；单一后端深度定制以插件方式落地。

这些原则直接决定了本项目采用 "通用优化框架 + 可插拔后端" 的路线，目标是成为 agent 生态的标配工具。

These principles establish the "universal optimization framework + pluggable backends" approach, aiming to become a standard tool in the agent ecosystem.

### 1.1 多 Proposer 后端架构

本项目的核心设计特性是 **Proposer 后端可插拔**——不绑定任何单一工具，支持三种 Proposer 后端：

```
PolyHarness 编排器
  │
  ├── 后端 A: Anthropic API 直连（不依赖任何 Code 工具）
  │     └── 适用于：任何人，只需 API Key
  │
  ├── 后端 B: Claude Code（官方闭源）
  │     └── claude --print
  │     └── 适用于：有 Claude Code 订阅的用户
  │
  ├── 后端 C: Claw Code（开源重写）
  │     └── claw --print
  │     └── 适用于：想完全开源自控的用户
  │
  └── 后端 D: 更多 agent（Codex / OpenCode / ...）
        └── 通过适配器扩展
        └── 适用于：任意 CLI agent
```

| 后端 | 论文还原度 | 成本控制 | 工具能力 | CLAW.md 支持 | 安全控制 | 部署门槛 |
|------|-----------|---------|---------|-------------|---------|----------|
| **API 直连** | 中（自建工具循环） | 最灵活（按 token 付费） | 4 个基础工具 | 需手动注入 | 完全自控 | `pip install` |
| **Claude Code 官方** | **最高**（论文 Proposer 就是它） | Pro/Teams 订阅 | 25+ 工具族 | ✅ 原生 | Anthropic 管理 | 需订阅 |
| **Claw Code 开源** | 高（clean-room 等价） | 按 token 付费 | 25+ 工具族 | ✅ 原生 | 完全自控 | 需 Node.js/Rust |

**这意味着项目有四层用户**：
1. **快速上手用户** → API 直连，`pip install` 零外部依赖
2. **Claude Code 用户** → 用官方工具做 Proposer，`ph init --agent claude-code` 一键配置
3. **开源优先用户** → Claw Code / OpenCode，完全可审计、可修改
4. **Agent 开发者** → 通过适配器接入自己的 agent，贡献插件给社区

### 1.2 产品定位

```
┌──────────────────────────────────────────────────────────┐
│                     产品定位矩阵                           │
│                                                          │
│  高                                                      │
│  ↑        ┌──────────────┐                               │ 
│  自       │ Meta-Harness │ ← 论文（闭源搜索框架）           │
│  动       │  (Stanford)  │                               │
│  化   ┌───┴──────────────┴───┐                           │
│  程   │  PolyHarness         │ ← 智能体生态的优化层         │
│  度   │  (多智能体适配)        │   让任意智能体自动进化       │
│       └───┬──────────────┬───┘                           │
│  ↓        │ Claude Code  │ ← 手动配置工作流                │
│  低       │ Codex / ...  │                               │
│           └──────────────┘                               │
│           低 ──── 适用范围 ────→ 高                        │
└──────────────────────────────────────────────────────────┘
```

**类比 / Analogy**：
- Supermemory → 给 agent 加记忆 / adds memory to agents
- PolyHarness → 给 agent 加自动进化 / adds self-evolution to agents

## 2. 目标用户与使用场景

### 2.1 目标用户

| 用户类型 | 需求 | PolyHarness 如何满足 |
|---------|------|---------------------|
| **Agent 用户（开发者）** | 提升日常使用的 agent（Claude Code/Codex 等）的表现 | `ph init --agent <name>` → `ph run` → `ph apply`，零配置升级 |
| **Agent 框架开发者** | 为自己的 agent 产品集成自动优化能力 | 适配器 API + 插件注册，3 个方法接入 |
| **Benchmark 竞赛参与者** | 快速迭代 agent 在特定 benchmark 上的表现 | 面向评估分数的自动搜索优化 |
| **研究者** | 复现/扩展 Meta-Harness 论文结果 | 提供可配置的开源实现 + 消融实验模式 |
| **Prompt 工程师** | 系统性优化复杂 prompt 流水线 | 将 prompt 优化从手动 trial-and-error 提升到自动搜索 |

### 2.2 核心使用场景

**场景 1：Agentic Coding Harness 优化**
```
输入：一个 coding agent 的 harness 代码 + 评估任务集
过程：Meta-Harness 搜索循环自动迭代优化
输出：候选 harness 变体 + 搜索日志（是否更优以评估结果为准）
```

**场景 2：Prompt Pipeline 优化**
```
输入：一个多步 prompt pipeline + 评分函数
过程：Proposer 阅读历史结果，提出 pipeline 修改
输出：候选 pipeline 版本 + 各版本评估对比
```

**场景 3：Tool Configuration 优化**
```
输入：agent 的工具集定义 + 使用场景
过程：搜索不同的工具组合/参数/调用策略
输出：最优工具配置 + 发现的工程洞察
```

## 3. 产品范围

### 3.1 MVP（最小可行产品）

**目标**：在单一任务上完成 Meta-Harness 搜索循环的端到端运行。

| 组件 | 范围 | 优先级 |
|------|------|--------|
| **编排器** | Python 脚本，循环调用 Proposer → 评估 → 存储 | P0（必须） |
| **文件系统 workspace** | 固定目录结构存储候选/分数/trace | P0 |
| **Proposer 接口** | API 直连后端（P0）+ Claude Code / Claw Code CLI 后端（P1） | P0 |
| **评估器** | 支持 Python 评分函数作为 evaluator | P0 |
| **CLI** | 单条命令启动搜索 | P0 |
| **日志** | 每轮候选的完整记录（代码 + 分数 + trace） | P0 |

### 3.2 V1.0（完整版本）

| 组件 | 范围 | 优先级 |
|------|------|--------|
| **Docker 沙箱评估** | 在 Docker 容器中运行候选 harness | P1 |
| **Claude Code / Claw Code CLI 集成** | 支持 `claude --print` 和 `claw --print` 作为 Proposer | P1 |
| **多任务评估** | 支持 task suite，汇总多任务分数 | P1 |
| **搜索策略配置** | 支持不同的候选选择/变异策略 | P1 |
| **Web Dashboard** | 可视化搜索进度、候选对比、trace 浏览 | P2 |
| **分布式评估** | 多机并行评估加速 | P2 |
| **CLAW.md Proposer 指令** | 通过 CLAW.md 自定义 Proposer 行为 | P1 |

### 3.3 明确不做的事

- ❌ 不复现 TerminalBench-2 评估基础设施（Harbor/Terminus 是闭源的）
- ❌ 不构建通用 LLM 编排框架（只做 harness 优化）
- ❌ 不实现 DSPy/MIPRO/GEPA 等竞品（只做 full-context Meta-Harness 方法）
- ❌ 不做模型微调（只优化 harness 代码，不改 LLM 权重）

## 4. 开发阶段与里程碑

### Phase 0：基础设施搭建（预计 1-2 周）

| 任务 | 交付物 | 完成标准 |
|------|--------|---------|
| 项目结构初始化 | 目录结构 + pyproject.toml + CI | `pip install -e .` 成功 |
| Workspace 文件系统设计 | 目录规范文档 + 初始化脚本 | 能创建标准 workspace |
| Anthropic API 工具循环 | Proposer agent 核心代码 | 能读写 workspace 文件 |
| 基础日志系统 | 每轮记录到文件系统 | 可浏览历史候选 |

### Phase 1：MVP 循环打通（预计 2-3 周）

| 任务 | 交付物 | 完成标准 |
|------|--------|---------|
| 编排器主循环 | `orchestrator.py` | 完整 propose → evaluate → store 循环 |
| Proposer prompt 设计 | `proposer_prompt.md` | Proposer 能诊断历史失败并提出改进 |
| 评估器接口 | `evaluator.py` 抽象基类 + Python 函数评估器 | 用户可定义评分函数 |
| 示例任务 | `src/polyharness/templates/text-classification/` | 端到端运行一个 toy 任务 |
| CLI 入口 | `ph run` | 一条命令启动搜索 |

**MVP 验收目标**：在 toy 文本分类任务上，10 轮搜索内至少出现一个评估分数高于初始 harness 的候选。该目标用于阶段验收，不表示对任意任务都保证改进。

### Phase 2：评估增强（预计 2-3 周）

| 任务 | 交付物 | 完成标准 |
|------|--------|---------|
| Docker 沙箱评估 | Docker 集成 + Dockerfile 模板 | 候选 harness 在隔离容器中运行 |
| Trace 收集增强 | stdout/stderr/exit code 全量记录 | Proposer 能看到完整执行轨迹 |
| 多任务支持 | task suite 配置 + 分数汇总 | 支持 N 个任务的平均分数 |
| 候选选择策略 | 基于历史分数的父候选选择 | 非 Best-of-N 的智能选择 |

### Phase 3：多 Agent 适配器集成（预计 2-4 周）

设计参考 [Supermemory](https://github.com/supermemoryai/supermemory) 的多 Agent 插件模式。

| 任务 | 交付物 | 完成标准 |
|------|--------|---------|
| 适配器抽象层 | `CLIAdapter` 基类 + 注册表 | 新增 Agent 只需实现 3 个方法 |
| Claude Code 适配器 | `adapters/claude_code.py` | 自动写入 CLAUDE.md + .claude/settings.json |
| Claw Code 适配器 | `adapters/claw_code.py` | 利用 CLAW.md 原生机制 |
| OpenCode 适配器（预留） | `adapters/opencode.py` | 占位，待 OpenCode 稳定后完善 |
| `ph doctor` 命令 | 自动检测所有可用后端 | 一条命令显示环境状态 |
| `ph init --agent <name>` 命令 | 自动配置 workspace | 注入原生指令文件 + 权限配置 |
| `ph apply` 命令 | 将最优配置回写到 agent | 自动更新 CLAUDE.md / CLAW.md 等 |
| Agent 记忆利用 | trace 信息通过 agentMemory 传递 | 跨轮次上下文保持 |

### Phase 4：可视化与生态（预计 3-4 周）

| 任务 | 交付物 | 完成标准 |
|------|--------|---------|
| Web Dashboard | React/Next.js 前端 | 搜索进度、候选对比、trace 浏览 |
| 消融分析工具 | 自动对比 Full vs Summary vs Scores | 一键验证信息瓶颈假说 |
| 社区 harness 模板库 | `templates/` 目录 + 贡献指南 | 用户可分享和复用 harness 模板 |
| 文档站 | mkdocs 或 docusaurus | 完整的用户指南和 API 文档 |

### Phase 3.5：CLI 优化（已完成） ✅

在 Phase 3 完成后，对 CLI 体验进行了三轮系统优化，新增 15 个功能特性，测试从 86 个增长到 121 个。

**低复杂度优化**

| 任务 | 交付物 | 状态 |
|------|--------|------|
| 全局 `--verbose`/`--quiet` 标志 | `main()` 全局选项 | ✅ |
| `ph run --dry-run` | 仅评估 base harness | ✅ |
| `ph status` 增强 | 已用时间、改进率、Δ | ✅ |
| `ph log` Δ 列 | tree/flat 模式均显示分数变化 | ✅ |
| `ph clean` 命令 | `--keep-best`、`-y` 免确认 | ✅ |
| Rich 进度条 | 编排器搜索循环实时进度 | ✅ |

**中复杂度优化**

| 任务 | 交付物 | 状态 |
|------|--------|------|
| `ph run --resume` | 断点续搜 | ✅ |
| `ph run --backend` | 运行时覆盖 Proposer 后端 | ✅ |
| `ph config show/set` | dot-notation 配置管理 + Pydantic 校验 | ✅ |
| `ph diff N` | `compare 0 N` 快捷方式 | ✅ |
| 编排器错误恢复 | 单轮失败不终止全局搜索 | ✅ |

**高复杂度优化**

| 任务 | 交付物 | 状态 |
|------|--------|------|
| `ph leaderboard` | 排行榜（`--top N`、`--tasks` 任务粒度） | ✅ |
| `ph trace N` | 查看 stdout/stderr/metrics/exitcode | ✅ |
| `ph report` | Markdown 报告（配置表 + 迭代日志 + ASCII sparkline） | ✅ |
| `ph run --strategy` | 运行时覆盖父候选选择策略 | ✅ |

## 5. 成功指标

以下指标分为产品目标和计划中的复现实验目标，用于路线图管理；除非另有说明，不代表仓库当前默认配置已经统一验证达到这些数值。

### 5.1 技术指标

| 指标 | MVP 目标 | V1.0 目标 |
|------|---------|----------|
| 搜索循环成功运行 | 10 轮无报错 | 50 轮无报错 |
| 候选提升率 | >50% 的候选优于前代 | >60% |
| 单轮延迟 | <5 min（含评估） | <3 min |
| Trace 完整度 | stdout + score | stdout + stderr + exit code + 资源使用 |

### 5.2 复现指标

| 指标 | 目标 | 对标论文 |
|------|------|---------|
| Full vs Scores Only 差距 | 可观测到显著差距 | 论文 Table 3: +15.4pp |
| 收敛效率 | 优于 Best-of-N 基线 | 论文 Figure 4 |
| Proposer 文件使用模式 | 非马尔可夫（读 >50% 历史） | 论文 Table 8: 82 文件/轮 |

### 5.3 产品指标（V1.0）

| 指标 | 目标 |
|------|------|
| GitHub Stars | >500 |
| 示例任务数 | >5 个不同领域 |
| 社区贡献的 harness 模板 | >10 |
| 文档覆盖率 | 所有公开 API 有文档 |

## 6. 风险与缓解

| 风险 | 影响 | 可能性 | 缓解策略 |
|------|------|--------|---------|
| **API 成本过高** | 每轮 ~$25，10 轮 ~$250 | 高 | 支持低成本模型（Haiku）作为 Proposer；实现 prompt caching |
| **Claw Code 项目不稳定** | 依赖的 clean-room 实现可能不完整 | 中 | MVP 不依赖任何 CLI；Phase 3 同时支持官方 Claude Code 和 Claw Code，任一可用即可 |
| **评估环境隔离不足** | 候选 harness 的代码可能损坏主机 | 中 | 强制 Docker 沙箱；MVP 限制为纯 Python 评估 |
| **搜索不收敛** | Proposer 无法有效利用诊断信息 | 中 | 从论文的 proposer prompt 出发；添加搜索多样性机制 |
| **法律/许可风险** | Claw Code 代码的法律地位 | 低 | 本项目只使用 Claw Code 作为外部工具，不包含其源码 |
| **上下文窗口不够** | 200K 窗口限制 vs 论文 10M | 中 | Proposer 通过工具选择性读取；实现智能 trace 检索 |

## 7. 项目命名与品牌

**品牌**：**PolyHarness**

**CLI 命令**：`ph`
```bash
# 环境与配置 / Environment
ph doctor                    # 检测已安装的 agent / Detect installed agents
ph init --agent claude-code  # 为指定 agent 创建优化 workspace / Create workspace for agent

# 优化 / Optimization
ph run                       # 启动自动搜索 / Start auto-search
ph status                    # 查看搜索进度 / View progress

# 应用 / Apply
ph apply                     # 将最优配置回写到 agent / Write best config back to agent
ph compare iter_3 iter_7     # 对比两个候选 / Compare candidates
ph best                      # 查看最佳候选 / View best candidate

# 可视化 / Visualization
ph dashboard                 # 启动 Web Dashboard
```

`ph doctor` 和 `ph init` 的设计参考 [Supermemory](https://github.com/supermemoryai/supermemory) 的多 Agent 插件对接模式——自动检测环境、利用各 Agent 的原生配置机制（CLAUDE.md / CLAW.md）注入 Proposer 指令，实现零手动配置。

**包名**：`polyharness`（PyPI / npm）

**一句话定位**：
PolyHarness 是面向 AI agent 的开源优化引擎，用迭代搜索把 Meta-Harness 的核心思路产品化，让现有 agent 在具体任务上持续试验并筛选更合适的 harness 方案。

**项目边界**：
- 它优化的是现有 agent 的工作方式，而不是替代它们成为新的通用 coding agent。
- 它更适合作为 Claude Code、Codex、ForgeCode 这类 agent 之上的搜索与改进引擎。
- 它的价值在于把 prompt、工具配置、harness 逻辑和评估反馈连接成一个可重复运行的闭环。

## 8. 与现有研究和生态的关系

```
PolyHarness 在 Agent 生态中的位置：
═══════════════════════════════════════

Meta-Harness 论文 (arXiv:2603.28052)
   │
   ├── TBench2 Artifact (开源产物)
   │   └── agent.py — 搜索产出的最优 harness
   │
   └── PolyHarness (开源优化框架)  ← 我们在这里
       │
       ├── 面向 agent 用户：
      │   └── pip install → ph run → 进入可重复优化循环
       │
       ├── 面向 agent 开发者：
       │   └── 适配器 API → 让自己的 agent 获得自动优化能力
       │
       └── 面向研究者：
           └── 复现论文 + 消融实验 + 新搜索策略探索

Agent 生态类比：
   Supermemory  = agent + memory layer
   PolyHarness  = agent + evolution layer
```
