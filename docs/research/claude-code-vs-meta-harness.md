---
title: "Claude Code 的 Skill/Agent 体系是否采用了 Meta-Harness 概念？"
date: 2026-04-02
status: draft
sources:
  - https://github.com/ultraworkers/claw-code (clean-room 重写，原 instructkr/claw-code)
  - https://arxiv.org/abs/2603.28052 (Meta-Harness 论文)
  - https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact
evidence:
  - rust/crates/runtime/src/prompt.rs — 系统提示词组装 + CLAW.md 发现
  - src/reference_data/tools_snapshot.json — 完整工具注册表
  - src/reference_data/subsystems/skills.json — 20 个 skill 模块
  - PARITY.md — TS vs Rust 功能对齐分析
---

# Claude Code 的 Skill/Agent 体系是否采用了 Meta-Harness 概念？

## 核心结论

**Claude Code 的 Skill/Agent 体系本身就是一个精心设计的 Model Harness——但它是手动设计的、面向人类可配置的 harness, 而非 Meta-Harness 论文中的自动优化 harness。**

用 Meta-Harness 论文的术语来说：Claude Code 的整个 Skill + Agent + Hook + CLAW.md 系统 **就是** "model harness"，Meta-Harness 框架所优化的正是这类系统。两者的关系不是"采用"，而是 **Claude Code 是 harness 的工程实践，Meta-Harness 是 harness 的自动优化理论**。

---

## 1. 什么是 Meta-Harness 中的 "Model Harness"？

回顾论文定义：

> **Model Harness** = 包裹在 LLM 周围的一切代码：系统提示词（system prompt）、工具定义（tool definitions）、完成检查逻辑（completion-checking）、上下文管理（context management）。

Meta-Harness 的核心洞察：**在相同 LLM 上，不同 harness 设计导致巨大的性能差异。Harness 是最值得优化的杠杆。**

## 2. Claude Code 的 Harness 解剖：Skill / Agent / Hook / CLAW.md

基于泄露源码的 Rust 重写（`prompt.rs`）和工具注册表（`tools_snapshot.json`），Claude Code 的完整 harness 结构如下：

### 2.1 系统提示词组装流程（= Harness 的核心）

来自 `rust/crates/runtime/src/prompt.rs` 的 `SystemPromptBuilder::build()`：

```
System Prompt 组装顺序：
═══════════════════════

 ①  Intro Section           ← 身份定义（"You are an interactive agent..."）
 ②  Output Style            ← 可选的输出风格覆盖
 ③  System Section          ← 核心行为规则（权限、压缩、注入检测）
 ④  Doing Tasks Section     ← 编码行为准则（先读后改、不加多余抽象）
 ⑤  Actions Section         ← 操作安全（可逆性、影响范围）

 ── DYNAMIC_BOUNDARY ──     ← 静态/动态内容分界线

 ⑥  Environment Context     ← 运行环境（模型=Opus 4.6、OS、cwd、日期）
 ⑦  Project Context         ← 项目感知（git status、git diff）
 ⑧  Instruction Files       ← CLAW.md 层级发现（见 §2.2）
 ⑨  Runtime Config          ← 加载的配置文件（permissionMode 等）
 ⑩  Append Sections         ← LSP 上下文、自定义追加内容
```

这个组装流程 **精确对应** Meta-Harness 论文中 "model harness" 的定义。每一层都是 harness 的一个组件。

### 2.2 CLAW.md 指令发现系统（= 项目级 Harness 配置）

```rust
// 从 cwd 向上遍历到文件系统根目录
// 在每一层查找以下文件：
fn discover_instruction_files(cwd: &Path) {
    for dir in [cwd, cwd.parent(), cwd.parent().parent(), ...root] {
        // 每层检查 4 个位置：
        dir.join("CLAW.md")
        dir.join("CLAW.local.md")
        dir.join(".claw/CLAW.md")
        dir.join(".claw/instructions.md")
    }
}
```

**预算限制**：
- 单个文件最大 4,000 字符
- 所有指令文件总计最大 12,000 字符
- 相同内容跨层级自动去重

**这是什么？** 这是一个 **分层的、目录作用域的 harness 配置系统**。项目根目录的 CLAW.md 定义全局行为规则，子目录的 CLAW.md 可以追加局部规则。与 Meta-Harness 参考实现中 `_gather_env_snapshot()` 收集环境信息的逻辑高度同构。

### 2.3 Skill 系统（= 可复用的 Harness 模块）

来自 `skills.json`，Claude Code 有 20 个 skill 模块：

| Skill 类别 | 具体模块 | Harness 层影响 |
|------------|---------|---------------|
| **行为模式** | `batch`, `loop`, `simplify`, `stuck` | 修改 agent 的推理策略 |
| **验证** | `verify`, `verifyContent` | 添加完成检查逻辑 |
| **记忆** | `remember` | 持久化上下文管理 |
| **配置** | `updateConfig`, `keybindings` | 修改运行时参数 |
| **生成** | `skillify`, `loremIpsum` | 创建新 skill / 测试内容 |
| **调试** | `debug` | 增强诊断能力 |
| **调度** | `scheduleRemoteAgents` | 编排多 agent 执行 |
| **外部** | `clawApi`, `clawApiContent`, `clawInChrome` | 扩展工具连接 |

**Skill 在 harness 中的角色**：每个 skill 通过 SKILL.md 文件向系统提示词注入特定指令，改变 agent 的行为模式。这 **等价于** Meta-Harness 中对 system prompt 的一次修改——只是它是人工选择的，而非搜索算法发现的。

### 2.4 Agent 系统（= 完整的替代 Harness）

```
AgentTool
├── 内置 Agent（不同的 Harness 配置）：
│   ├── exploreAgent          ← 只读探索（工具子集 + 不同提示）
│   ├── planAgent             ← 规划模式（限制执行，强调分析）
│   ├── verificationAgent     ← 验证模式（聚焦测试和检查）
│   ├── generalPurposeAgent   ← 通用配置
│   └── clawCodeGuideAgent    ← 项目引导
│
├── 运行机制：
│   ├── forkSubagent    — 分叉子 agent（独立上下文）
│   ├── runAgent        — 运行 agent
│   ├── resumeAgent     — 恢复 agent
│   └── agentMemory     — 跨 agent 记忆共享
│
└── 用户自定义 Agent：
    └── loadAgentsDir   — 从 .agents/ 目录加载 .agent.md 文件
```

**关键洞察**：每个内置 agent 就是一个 **预定义的 harness 变体**——不同的系统提示词 + 不同的工具集 + 不同的行为约束。这与 Meta-Harness 搜索不同 harness 候选的逻辑一致，只是 Claude Code 的候选是**人工预设**的。

### 2.5 Hook 系统（= 运行时 Harness 修改）

```
Hook 系统：
├── PreToolUse   — 工具执行前的拦截/重写/拒绝
├── PostToolUse  — 工具执行后的结果修改/重试
└── 配置方式     — 通过 CLAW.md 或 settings 定义
```

Hook 系统允许 **在运行时动态修改 harness 行为**——拦截工具调用、重写参数、拒绝操作、修改结果。这是 Meta-Harness 中 "completion-checking logic" 组件的工程实现。

## 3. 逐组件对照：Claude Code Harness vs Meta-Harness 概念

| Meta-Harness 论文中的 Harness 组件 | Claude Code 中的实现 | 配置方式 |
|-----------------------------------|---------------------|---------|
| **System Prompt** | `SystemPromptBuilder` 多层组装 | 代码写死 + CLAW.md + Skill 注入 |
| **Tool Definitions** | `tools_snapshot.json`（25+ 工具族） | 代码注册 + `simple_mode` 切换 + `ToolPermissionContext` 过滤 |
| **Completion-checking Logic** | Hook 系统（PreToolUse/PostToolUse） | CLAW.md 配置 + 内置规则 |
| **Context Management** | 自动上下文压缩 + 会话历史 + 记忆系统 | `compact` 命令 + `remember` skill + `agentMemory` |
| **Environment Bootstrap** | CLAW.md 层级发现 + git status/diff 快照 | 自动运行（`ProjectContext::discover_with_git`） |

### 匹配度评估

**完全匹配的组件**：
- ✅ System prompt 复杂组装 = harness 的提示层
- ✅ Tool definitions 动态注册 = harness 的工具层
- ✅ CLAW.md 项目发现 = harness 的环境引导
- ✅ Hook 拦截/重写 = harness 的完成检查

**Claude Code 超出 Meta-Harness 定义的**：
- 🔸 多 Agent 编排（Team/Task）— Meta-Harness 不涉及
- 🔸 MCP 协议扩展 — Meta-Harness 不涉及
- 🔸 插件生态 — Meta-Harness 不涉及
- 🔸 权限分级 — Meta-Harness 在沙箱中无需此功能

**Meta-Harness 有而 Claude Code 缺少的**：
- ❌ **自动优化循环** — Claude Code 无法自动搜索更好的 harness 配置
- ❌ **全量诊断上下文** — Claude Code 受标准上下文窗口限制（~200K tokens vs ~10M tokens）
- ❌ **反事实诊断** — Claude Code 无法回溯"哪个 harness 决策导致了失败"

## 4. 深层分析：Claude Code 是"手动版 Meta-Harness"吗？

### 4.1 相同的核心理念

Meta-Harness 论文的中心论点是：**harness 设计是 agent 性能的主要杠杆**。

Claude Code 的架构用工程实践验证了这一点：

```
Claude Code 的 Harness 可配置维度：
════════════════════════════════

1. 提示层    → CLAW.md 分层指令（人工编写）
2. 工具层    → simple_mode / include_mcp / ToolPermissionContext（配置选择）
3. 行为层    → Skill 加载（人工选择哪些 skill 激活）
4. 拦截层    → Hook 规则（人工定义 PreToolUse/PostToolUse）
5. Agent 层  → 内置/自定义 Agent 切换（人工选择 harness 变体）
6. 记忆层    → agentMemory / session memory（积累上下文）
```

这 **就是** 一个 model harness 的完整工程实现。Claude Code 团队（无论是否读过 Meta-Harness 论文）事实上构建了一个 **高度模块化、用户可配置的 harness 系统**。

### 4.2 关键差异：人工 vs 自动

```
                  Claude Code                  Meta-Harness
                  ══════════                   ════════════
harness 设计者：   Anthropic 工程师 + 用户       搜索算法（Proposer = Claude Code）
迭代方式：         人工试错、A/B 测试            自动搜索循环（~10 步）
反馈信号：         用户满意度、内部指标           benchmark 分数 + 执行 trace
迭代速度：         周/月级                       小时级（每步约 10M tokens）
优化空间：         所有用户的所有场景             特定 benchmark 的特定任务
```

### 4.3 使用关系

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  Meta-Harness 论文使用 Claude Code 做了什么？                     │
│                                                                 │
│  Claude Code 的 Harness 系统                                    │
│  （BashTool + FileEdit + FileRead + grep...）                    │
│       │                                                         │
│       │  作为 Proposer，操作文件系统                               │
│       ▼                                                         │
│  优化另一个 Harness（Terminus-KIRA 的 agent.py）                  │
│       │                                                         │
│       │  关键发现：~60 行 env bootstrap 代码 = 巨大性能提升         │
│       ▼                                                         │
│  这个发现反过来验证了 Claude Code 自身的 CLAW.md 设计理念            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 5. Skill/Agent 系统的具体 Harness 模式

### 5.1 Skill 作为 Harness 模块（Prompt 注入）

每个 skill 本质上是一个 **harness 补丁**——向系统提示词注入特定行为指令：

| Skill | 注入的 Harness 行为 | 等价的 Meta-Harness 操作 |
|-------|-------------------|------------------------|
| `verify` | 任务完成前强制验证 | 修改 harness 的 completion-checking |
| `stuck` | 遇到困难时切换策略 | 修改 harness 的 fallback 逻辑 |
| `batch` | 批量处理模式 | 修改 harness 的 task 编排方式 |
| `loop` | 持续迭代模式 | 修改 harness 的 agent 循环终止条件 |
| `simplify` | 简化输出 | 修改 harness 的 output 策略 |
| `remember` | 持久化关键上下文 | 修改 harness 的 context management |
| `debug` | 增强诊断输出 | 类似 Meta-Harness 的 full diagnostic context |

### 5.2 Agent 作为 Harness 变体（完整替换）

不同 Agent 代表不同的 harness 配置组合：

```
┌─────────────────────────────────────────────────────────────┐
│  Default Agent (全功能 Harness)                              │
│  ├── System Prompt: 完整版                                   │
│  ├── Tools: 25+ 工具族                                       │
│  ├── Hooks: 用户定义                                         │
│  └── Mode: 读写执行                                          │
├─────────────────────────────────────────────────────────────┤
│  Explore Agent (只读 Harness)                                │
│  ├── System Prompt: 探索专用指令                              │
│  ├── Tools: 只读子集（FileRead, Glob, Grep）                 │
│  ├── Hooks: 拒绝写入操作                                     │
│  └── Mode: 只读                                              │
├─────────────────────────────────────────────────────────────┤
│  Plan Agent (规划 Harness)                                   │
│  ├── System Prompt: 强调分析和规划                             │
│  ├── Tools: 受限子集                                          │
│  ├── Hooks: 限制执行                                          │
│  └── Mode: 计划模式                                           │
├─────────────────────────────────────────────────────────────┤
│  Verification Agent (验证 Harness)                            │
│  ├── System Prompt: 聚焦测试和检查                             │
│  ├── Tools: 包含测试执行工具                                   │
│  ├── Hooks: 强制验证步骤                                      │
│  └── Mode: 验证模式                                           │
└─────────────────────────────────────────────────────────────┘
```

**每切换一个 Agent = 切换一个 harness。** 这与 Meta-Harness 搜索不同 harness 候选的行为在概念上等价。

### 5.3 CLAW.md + Config 作为 Harness 参数化

```
项目 A（Python 后端）                  项目 B（React 前端）
├── CLAW.md                           ├── CLAW.md
│   "使用 pytest 做测试"                │   "使用 vitest 做测试"
│   "遵循 PEP 8 风格"                  │   "使用 TypeScript strict mode"
│   "部署前运行 mypy"                   │   "组件使用函数式风格"
├── .claw/settings.json                ├── .claw/settings.json
│   permissionMode: "acceptEdits"      │   permissionMode: "dontAsk"
└── apps/api/CLAW.md                   └── packages/ui/CLAW.md
    "API 层使用 FastAPI"                    "UI 使用 Tailwind CSS"
```

**同一个 Claude Code，不同的 CLAW.md = 不同的 harness。** 这是一种 **声明式的 harness 配置系统**。

## 6. 时间线与因果关系

| 事件 | 时间 |
|------|------|
| Claude Code 原始开发（Anthropic 内部） | 2025 年起 |
| Claude Code 公开使用 | 2025 年中 |
| Meta-Harness 论文发表（arXiv:2603.28052） | 2026-03 |
| Claude Code 源码泄露 | 2026-03-31 |
| claw-code 重写启动 | 2026-03-31 之后 |

**因果方向**：Claude Code 的 Skill/Agent 系统设计 **先于** Meta-Harness 论文。两者不存在直接借鉴关系。但可能存在以下间接联系：

1. **共同的智力背景**：两者都出自对 "LLM agent 的包装层很重要" 这一认识
2. **Omar Khattab 的双重角色**：Khattab 是 Meta-Harness 论文共同作者，也是 DSPy 创始人。DSPy 的 "程序化优化 LLM 管道" 思路与 Claude Code 的 Skill 系统有理念相通之处
3. **Meta-Harness 使用了 Claude Code**：论文中 Proposer = Claude Code，说明作者们熟悉 Claude Code 的 harness 架构

## 7. 结论

### Claude Code 的 Skill/Agent 是否"采用了" Meta-Harness 概念？

**准确答案：不是"采用"，而是"天然就是"。**

Claude Code 的 Skill/Agent/Hook/CLAW.md 系统 **本身就是** 一个高度工程化的 Model Harness。它涵盖了 Meta-Harness 论文定义的 harness 全部四个组件（system prompt、tool definitions、completion-checking、context management），并且在工程深度上远超论文的参考实现。

```
Meta-Harness 论文的 "Harness" 概念
        ║
        ║  Claude Code 的实现 ←── 事实上的工程标杆
        ║
        ╠══ System Prompt          ✅ SystemPromptBuilder（10 层组装）
        ╠══ Tool Definitions       ✅ 25+ 工具族 + 动态过滤
        ╠══ Completion-checking    ✅ Hook 系统 + verify skill
        ╠══ Context Management     ✅ 自动压缩 + 记忆 + 会话持久化
        ║
        ╠══ ** 环境引导 **         ✅ CLAW.md 层级发现 + git 快照
        ╠══ ** 模块化配置 **       ✅ Skill 热加载 + Agent 切换
        ╠══ ** 多 Agent 编排 **    ✅ SubAgent + Team + Task
        ║
        ║  但缺少 Meta-Harness 的核心：
        ╠══ ❌ 自动搜索优化循环
        ╠══ ❌ 全量诊断上下文（~10M tokens）
        ╚══ ❌ 反事实诊断能力
```

### 一句话总结

**Claude Code 是目前已知的最复杂的 Model Harness 工程实现，Meta-Harness 是优化这类 harness 的理论框架。两者不是采用/被采用的关系，而是"工程实践"与"优化理论"的互补。**

### 启示

如果将 Meta-Harness 的自动优化循环应用到 Claude Code 的 Skill/Agent 系统上——自动搜索最优的 CLAW.md 内容、Skill 组合、Agent 配置、Hook 规则——这将是 Meta-Harness 最有价值的工程应用方向。
