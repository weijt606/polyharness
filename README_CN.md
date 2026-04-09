# PolyHarness

```text
  _____      _        _    _                                   
 |  __ \    | |      | |  | |                                  
 | |__) |__ | |_   _ | |__| | __ _ _ __ _ __   ___  ___ ___    
 |  ___/ _ \| | | | ||  __  |/ _` | '__| '_ \ / _ \/ __/ __|   
 | |  | (_) | | |_| || |  | | (_| | |  | | | |  __/\__ \__ \   
 |_|   \___/|_|\__, ||_|  |_|\__,_|_|  |_| |_|\___||___/___/   
                __/ |                                          
               |___/                                           
```

**让你的 AI Agent 自动进化。**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-212%20passing-brightgreen.svg)]()
[![English](https://img.shields.io/badge/Docs-English-blue.svg)](README.md)

---

> **什么是 "Harness"？**
> Harness 是包裹你的 AI agent 与任务交互的那层代码——包括 prompt 模板、工具配置、输出解析逻辑，以及任何预处理/后处理步骤。它是 agent *如何*解决问题的方式，而不是模型本身。PolyHarness 通过迭代搜索自动寻找更优的 harness 配置，省去你手动调参的功夫。

你的 AI agent 每次都用同一套 harness 跑任务。同样的 prompt，同样的工具配置，同样的策略，不管它失败多少次都如此。

**PolyHarness 用搜索循环来处理这个问题。** 它记录每轮迭代、评估候选 harness 变更，并利用累计历史去搜索更高分的配置。你只需执行一个命令来启动这个流程。

| | |
|---|---|
| **自动进化** | 通过迭代搜索探索 harness 变更，并把完整评估历史保存在同一个 workspace 中。 |
| **8 个 Agent 后端** | Claude Code · Claw Code · Codex · Hermes · OpenCode · API 直连 · OpenAI 兼容 · Local，可接入任何 CLI agent。 |
| **完整历史** | 每轮迭代的代码、分数、执行轨迹完整保留。Meta-Harness 论文报告非马尔可夫搜索优于盲目重试。 |
| **搜索树** | 可视化优化路径，对比任意两个候选的逐任务差异。 |
| **一条命令完成初始化** | `ph init --base-harness ... --task-dir ...`，复制文件、配置 workspace，一步完成。 |
| **在线进化** | `ph wrap` 记录每次 agent 调用。当 traces 积累足够多后，`ph evolve` 会触发一轮轻量搜索循环——agent 在你工作的同时持续改进。 |
| **闭环流程** | init → run → inspect → apply。由你决定何时把当前最佳候选回写到项目。 |

---

## 背景故事

斯坦福的 [Meta-Harness 论文](https://arxiv.org/abs/2603.28052)（IRIS Lab，2026）证明了一个很重要的结论：**harness 设计是影响 agent 性能的首要杠杆**，其影响甚至可能超过模型选择、prompt 工程或微调。

关键洞察在于：当你给 AI agent 提供的是*完整诊断历史*，而不只是最新分数，它就能*系统性地进化*自己的 harness 配置。这份历史包含每次尝试的代码、轨迹和失败模式。论文把这种方法称为“非马尔可夫搜索”，并证明它明显优于简单的 best-of-N 采样。

但论文只发布了最终优化产物（`agent.py`）。**搜索框架本身从未开源。**

PolyHarness 填补了这个空白。它把 Meta-Harness 搜索变成了一个任何人都能使用的开源引擎，适用于任意 agent、任意任务和任意评估流程。

> **可以这样理解：**
> - 记忆工具（如 Supermemory）赋予 agent 跨会话的持久**记忆**。
> - **PolyHarness 赋予 agent 持久的自我进化能力**，你可以用可重复运行的方式持续调整它们的工作方式。

## PolyHarness 是什么

PolyHarness 是一个通过迭代评估与搜索来探索 agent harness 变体的开源引擎。

它继承了 Meta-Harness 论文及其中 TBench2 结果所体现的核心思路，但这个仓库关注的是优化流程本身如何落地，也就是 harness 变体怎样在一轮轮评估、诊断和修改中被系统性迭代。

如果说 [ForgeCode](https://github.com/antinomyhq/forgecode) 这类工具是在直接帮你写代码，那么 PolyHarness 更像是帮助你在自己的任务上持续试验 prompt、工具使用和 harness 逻辑配置的搜索层。

---

## 使用场景

<table>
<tr>
<td width="50%" valign="top">

### 我在使用 AI 编程 agent

你有 Claude Code、Codex 或其他 agent。
你希望把它调得更适合你的特定任务，而不是手动来回调 prompt。

```bash
pip install polyharness
ph init --agent claude-code --template text-classification
ph run
ph apply
```

你现在就有了一个可重复运行的优化 workspace，可以在确认评估结果后再应用最佳候选。

**[→ 跳转到快速开始](#快速开始)**

</td>
<td width="50%" valign="top">

### 我在构建 agent 框架

你正在开发 AI agent 或工具，希望把自动优化能力直接集成进去。

PolyHarness 提供可插拔的适配器 API。
只要实现 3 个方法，你的 agent 就能接入同样的搜索循环。

```python
class MyAgentAdapter(CLIAdapter):
    def build_command(self, prompt, cwd):
        return ["my-agent", "--prompt", prompt]

    def parse_output(self, stdout, stderr, code):
        return CLIResult(...)
```

**[→ 跳转到工作原理](#工作原理)**

</td>
</tr>
</table>

---

## 快速开始

### 1. 安装

```bash
pip install polyharness         # Python >= 3.12
# 或
npm install -g polyharness      # Node.js 包装器，自动安装 Python 包
```

### 2. 检查环境

```bash
ph doctor
```

自动检测已安装的 agent 后端（Claude Code、Codex 等）并显示状态。

### 3. 初始化 workspace

`ph init` 设置两件事：

1. **谁来优化**（`--agent`）—— 由哪个 AI 来思考：CLI 工具如 `claude-code`，或 API 如 `api` / `openai`。
2. **优化什么**（`--template` 或 `--base-harness` + `--task-dir`）—— 你的 harness 代码、测试数据和评估脚本。`ph run` 运行时三者缺一不可。

#### 方式 A：用内置模板一键初始化（推荐首次使用）

PolyHarness 自带多个可直接运行的模板，一条命令搞定所有初始化：

```bash
ph init --agent api --template text-classification
```

这会自动将完整的 harness + tasks + evaluate 三件套复制到 workspace 中：

```
.ph_workspace/
├── base_harness/
│   └── harness.py          # 待优化的起始代码
├── tasks/
│   └── test_cases.json     # 测试输入 + 期望输出
├── evaluate.py             # 评分脚本
└── config.yaml             # 自动生成
```

就这样——直接跳到[第 4 步](#4-运行优化循环)。

> 可用模板：`text-classification`、`math-word-problems`、`code-generation`、`rag-qa`、`api-calling`。

#### 方式 B：使用自己的项目

你需要三个文件：`harness.py`（要优化的代码）、`tasks/test_cases.json`（测试数据）、`evaluate.py`（评分脚本）。一条命令全部生成：

```bash
ph new my-project
```

生成结构：

```
my-project/
├── base_harness/
│   └── harness.py          # ← 编辑：你的起始逻辑
├── tasks/
│   └── test_cases.json     # ← 编辑：测试输入 + 期望输出
└── evaluate.py             # ← 按需编辑：评分逻辑
```

根据你的任务编辑生成的文件。例如，如果你在做文本分类：

```python
# my-project/base_harness/harness.py
def solve(input_data: str) -> str:
    # 一个简单的起点——agent 会来改进它
    if "good" in input_data.lower():
        return "positive"
    return "negative"
```

```json
// my-project/tasks/test_cases.json
[
  {"input": "这个产品很棒", "expected": "positive"},
  {"input": "糟糕的体验",  "expected": "negative"},
  {"input": "会议下午三点开始", "expected": "neutral"}
]
```

> `evaluate.py` 开箱即用——它会调用 `harness.solve(case["input"])`，与 `case["expected"]` 对比，报告准确率。只有当你的评分逻辑需要自定义时才需要修改它。

然后初始化：

```bash
ph init \
  --agent claude-code \
  --base-harness ./my-project/base_harness \
  --task-dir ./my-project
```

| 参数 | 含义 | 必需？ |
|------|-----|:------:|
| `--agent` | 谁来优化：`claude-code`、`codex`、`api`、`openai` 等 | 是（默认 `api`） |
| `--base-harness` | 包含起始 harness 代码的目录（至少需要 `harness.py`） | 是* |
| `--task-dir` | 包含 `tasks/test_cases.json` 和可选 `evaluate.py` 的目录 | 是* |
| `--eval-script` | `evaluate.py` 路径（如果不在 `--task-dir` 内） | 仅当 task-dir 中没有时 |
| `--workspace` | workspace 创建位置（默认 `.ph_workspace`） | 否 |

\* 技术上在 `init` 时可省略，但 `ph run` 运行时若缺少 harness 代码或测试数据会报错。

`ph init` 会将所有内容复制到一个隔离的 **优化 Workspace** 中——你的原始代码不会被修改。

**配置你的 Agent**

PolyHarness 会通过沙盒编排将你的 Agent 的工作目录（CWD）限制在该 workspace 内部，确保它能在不破坏原工程的前提下，安全地读取历史评估信息，并就地修改代码副本。

| 使用场景 | 配置方法 |
|----------|------------------|
| **受原生支持的 CLI Agent 工具** | 使用 `ph init --agent <name>`。系统会自动注入其专属提示词指令（如 `CLAUDE.md`）。<br>*(支持: claude-code, claw-code, codex, hermes, opencode)* |
| **Anthropic API 直连** | 使用 `ph init --agent api`。在 `ph run` 前设置 `export ANTHROPIC_API_KEY="sk-ant-..."`。 |
| **OpenAI / 本地模型** | 使用 `ph init --agent openai`。然后配置 endpoint——参见下方 [本地模型配置](#本地模型配置) 章节。 |
| **CLI 命令被自定义 / 路径未响应** | 如果你的 CLI Agent 使用了非标命令（或未设置全局 PATH），请在初始化后手动修改 workspace 根目录下的 `config.yaml`：<br>`proposer: { cli_path: "npx @anthropic-ai/claude-code" }` |

### 4. 运行优化循环

```bash
ph run
```

编排器会执行这样一个循环：复制你的 harness → 让 Proposer agent 提出候选修改 → 评估结果 → 存储一切 → 重复。

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│    你                             PolyHarness                │
│    │                              │                          │
│    ├── ph init ──────────────────→│ 创建 workspace           │
│    │   (harness + tasks + eval)   │ 复制文件                  │
│    │                              │ 注入 CLAUDE.md           │
│    │                              │                          │
│    ├── ph run ───────────────────→│ 启动搜索循环：             │
│    │                              │                          │
│    │   ┌──────────────────────────┤                          │
│    │   │  步骤 1: 选择父候选        │ 最优或 Tournament         │
│    │   │  步骤 2: 复制 harness     │ 从父候选 → 新候选           │
│    │   │  步骤 3: 提议改进          │ Agent 读取全部历史         │
│    │   │  步骤 4: 评估             │ 运行任务，计算分数          │
│    │   │  步骤 5: 存储结果          │ 代码 + 分数 + 轨迹         │
│    │   │  步骤 6: 检查停止条件       │ 有改进？还有耐心？          │
│    │   └──────────┬───────────────┤                          │
│    │              └── 循环 ───────┘                           │
│    │                              │                          │
│    ├── ph log ───────────────────→│ 展示搜索树                 │
│    ├── ph compare 0 5  ──────────→│ 分数差异 + 代码 diff       │
│    └── ph apply ─────────────────→│ 回写最优结果               │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 5. 查看和应用

```bash
ph status                      # 进度表格 + 耗时 + 改进率
ph log                         # 搜索树带增量（Δ）列
ph best                        # 最佳候选详情
ph leaderboard                 # 候选排名表（--tasks 展开每题分数）
ph compare 0 5                 # 对比两个迭代（分数 + 代码 diff）
ph diff 5                      # compare 0 5 的快捷方式
ph trace 3                     # 查看 iter_3 的 stdout/stderr/metrics
ph report                      # 生成完整 markdown 报告

ph apply                       # 将最优 harness 回写到 base_harness/
ph export ./my-optimized       # 或导出到任意目录
ph clean --keep-best           # 清理候选目录释放磁盘空间
```

### 6. 自动进化

步骤 1–5 运行的是**批量**优化循环。但你也可以让 PolyHarness 从你**日常使用 agent 的过程**中收集数据，并自动触发进化。

只需在 agent 命令前加上 `ph wrap --auto-evolve`（选择你正在使用的那一种）：

```bash
# CLI agent 后端 —— 直接包裹你已经在用的 agent
ph wrap --auto-evolve claude -p "把 auth 模块重构为 JWT 方案"      # Claude Code
ph wrap --auto-evolve claw -p "给支付服务写集成测试"            # Claw Code
ph wrap --auto-evolve codex "给 API 客户端加上重试逻辑"              # Codex
ph wrap --auto-evolve hermes chat -q "重构数据库连接池"              # Hermes Agent
ph wrap --auto-evolve opencode -p "修复不稳定的 parser 测试"       # OpenCode

# 本地模型 —— 直接包裹 CLI 命令
ph wrap --auto-evolve ollama run gemma3 "总结这篇文档"                # Ollama
```

> **注意：** API 后端（DeepSeek、OpenAI 等）请使用步骤 1–5 的批量工作流：`ph init --agent openai`。

这会发生什么：
1. Agent 输出**原样透传**，你的工作流不会改变。
2. 每次调用记录一条 **trace**（agent、命令、退出码、耗时、输出）到 `~/.polyharness/traces/`。
3. 当 trace 数量达到阈值（默认 50，可配置）时，**PolyHarness 自动触发一轮轻量进化循环**，无需手动干预。

阈值未达到时，你会看到一行安静的进度提示：
```
PolyHarness: trace recorded (20260408_143012_a1b2c3d4)
PolyHarness: 7/50 traces until next evolution
```

当阈值触发时：
```
PolyHarness: 50 traces collected — triggering auto-evolution...
───────── PolyHarness Online Evolution ─────────
...
Auto-evolution complete: best score 0.8700 at iter_2
Run ph apply to use the improved harness.
```

#### 配置

在 workspace 的 `config.yaml` 中调整触发阈值：

```yaml
evolution:
  trigger:
    strategy: accumulate
    accumulate_count: 10    # 每 10 条 trace 触发一次（默认：50）
  max_iterations: 3         # 每轮进化的迭代次数
  auto_apply: false         # 设为 true 自动应用（谨慎使用）
```

#### 手动控制

你也可以随时手动管理 traces 并触发进化：

```bash
ph traces list                 # 最近 traces 表格
ph traces stats                # 汇总：总数、已评分、各 agent 分布
ph traces show <trace-id>      # 完整详情 + 捕获的输出
ph traces clear --keep 100     # 清理旧 traces
ph evolve                      # 手动触发进化
```

> **提示：** 如果不想保存 stdout/stderr（例如敏感输出），使用 `--no-record-output`。元数据始终会记录。

#### 零配置自动包裹：`ph shell-hook`

不想每次都输入 `ph wrap --auto-evolve`？安装 shell 钩子即可自动拦截 agent 命令：

```bash
ph shell-hook install          # 一次性设置，写入 ~/.zshrc
```

之后正常使用 agent 即可：

```bash
claude -p "把 auth 重构为 JWT"            # 自动变为：ph wrap --auto-evolve claude -p ...
claw -p "写支付测试"                  # 同理——自动包裹
codex "加重试逻辑"                     # 同理
hermes chat -q "重构连接池"            # 同理
opencode -p "修复不稳定测试"            # 同理
```

原理：shell 的 `preexec` 钩子检测到 `claude`/`claw`/`codex`/`hermes`/`opencode` 命令后，透明地通过 `ph wrap --auto-evolve` 转发。你的输出不会变。

```bash
ph shell-hook status           # 查看是否已安装
ph shell-hook uninstall        # 干净移除（恢复原始 rc 文件）
```

#### 自动进化流程

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   你                             PolyHarness                 │
│   │                              │                           │
│   ├── ph shell-hook install ────→│ 注入 preexec 钩子          │
│   │   （一次性设置）                │ 到 ~/.zshrc               │
│   │                              │                           │
│   ├── claude -p "修复 bug" ────→  │ Shell 钩子拦截             │
│   │   （正常使用）                 │                           │
│   │                              ├── 运行 agent               │
│   │   ┌─ 输出原样透传 ─────────────┤                           │
│   │   │                          ├── 记录 trace               │
│   │   │                          │   (~/.polyharness/        │
│   │   │                          │    traces/)               │
│   │   │                          │                           │
│   │   │                          ├── 检查阈值                 │
│   │   │                          │   traces < 50?            │
│   │   │                          │   ├─ 是: "7/50 traces"    │
│   │   │                          │   └─ 否: 触发 ─────┐       │
│   │   │                          │                   │       │
│   │   │                          │   ┌───────────────┘       │
│   │   │                          │   │ 进化循环               │
│   │   │                          │   │（等同 ph run）         │
│   │   │                          │   │ 提议 → 评估            │
│   │   │                          │   │ → 存储 → 重复          │
│   │   │                          │   └──────────────────     │
│   │   │                          │                           │
│   └───┘                          │                           │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

核心区别：**你不需要手动执行 `ph run`。**像往常一样使用 agent；PolyHarness 静默收集数据，当积累足够信号时自动触发进化。

### 立即体验（无需 API key）

```bash
ph init --agent local --template math-word-problems
ph run --max-iterations 5
ph log

# Search Tree
# └── iter_0  0.3500
#     └── iter_1  0.5000
#         └── iter_2  0.6500
#             └── iter_3  0.9000 ★
```

上面的分数轨迹来自本仓库内置 `math-word-problems` 示例在当前 `local` 后端下的实测结果，按展示需要做了四舍五入。它不是论文分数，也不是外部项目的 benchmark 结果。`local` 后端使用确定性规则；这里不对 Claude Code、Codex 等真实 agent 后端给出固定分数提升承诺。

---

## 工作原理

PolyHarness 运行的是一个 **Meta-Harness 风格的搜索循环**，即让 AI agent 逐轮提出、评估并记录 harness 变更的迭代过程。详细流程图见上方 [步骤 4](#4-运行优化循环) 和 [步骤 6](#6-自动进化)。

### 为什么有效：非马尔可夫搜索

传统方式是：运行 agent → 查看分数 → 重试。每次尝试彼此独立。

**PolyHarness 不一样。** 每轮迭代都会保存：
- 完整的候选源代码
- 逐任务分数，而不只是总分
- 完整执行轨迹（stdout、stderr、退出码）
- 元数据（父候选、proposer 模型、变更摘要）

Proposer 在生成下一个候选之前会读取**所有这些信息**。它能够看到之前为什么失败、哪些具体任务发生了退步，以及哪些代码变更导致了问题。这也是为什么 Meta-Harness 论文发现，全量上下文搜索相比只看分数的搜索方式，能高出 15 个百分点以上。

---

## 支持的 Agent 后端

| 后端 | 命令 | 适用场景 |
|------|------|----------|
| `api` | — | 默认。Anthropic API 直连，只需 `ANTHROPIC_API_KEY` |
| `openai` | — | 兼容 OpenAI 格式的本地/云端模型直连 (Ollama, vLLM, LM Studio 等)，需配置 `OPENAI_API_KEY` |
| `claude-code` | `claude -p` | 官方 Claude Code CLI（Pro/Teams 订阅） |
| `claw-code` | `claw -p` | 开源 Claw Code CLI |
| `codex` | `codex --quiet` | OpenAI Codex CLI |
| `hermes` | `hermes chat -q` | Nous Research [Hermes Agent](https://github.com/NousResearch/hermes-agent) CLI |
| `opencode` | `opencode -p` | OpenCode CLI |
| `local` | — | 离线规则引擎，用于开发和测试 |

`ph doctor` 会自动检测所有可用后端并显示状态。

当你运行 `ph init --agent claude-code` 时，PolyHarness 会在 workspace 中自动生成 `CLAUDE.md` 指令文件，告诉 agent 如何作为优化 Proposer 工作。`CLAW.md`、`CODEX.md`、`AGENTS.md`（Hermes）、`OPENCODE.md` 也是同样的机制，每个 agent 都使用它自己的原生指令格式。

### 本地模型配置

如果你在本地运行模型（Ollama、vLLM、LM Studio 或任何 OpenAI 兼容服务），使用 `openai` 后端：

```bash
# 1. 初始化（用模板，或用 --base-harness + --task-dir 指向自己的项目）
ph init --agent openai --template text-classification

# 2. 配置本地 endpoint
ph config set proposer.model llama3.3
ph config set proposer.base_url http://localhost:11434/v1
ph config set proposer.api_key sk-dummy

# 3. 运行
ph run
```

或者直接编辑 `.ph_workspace/config.yaml`：

```yaml
proposer:
  backend: openai
  model: llama3.3                          # 你的本地模型名称
  base_url: http://localhost:11434/v1      # Ollama 默认端口
  api_key: sk-dummy                        # 本地模型不需要真实 key
  max_tokens: 16384
  temperature: 0.7
```

常见本地服务端点：

| 工具 | `base_url` |
|------|-----------|
| Ollama | `http://localhost:11434/v1` |
| vLLM | `http://localhost:8000/v1` |
| LM Studio | `http://localhost:1234/v1` |
| LocalAI | `http://localhost:8080/v1` |

---

## 配置参考

`ph init` 之后，workspace 中会生成一份 `config.yaml`，包含以下字段：

```yaml
search:
  max_iterations: 20          # 最大搜索迭代次数
  early_stop_patience: 5      # 连续 N 轮无改进后停止
  parent_selection: best       # 父候选选择策略: best | tournament | all

proposer:
  backend: api                 # api | openai | claude-code | claw-code | codex | hermes | opencode | local
  model: claude-sonnet-4-20250514  # 模型名称（api/openai 后端使用）
  base_url: null               # 自定义 API 端点（openai 后端使用）
  api_key: null                # API 密钥覆盖（null = 使用环境变量）
  max_tokens: 16384            # 每轮 proposer 最大输出 token 数
  temperature: 0.7             # 采样温度（0.0 – 2.0）
  cli_path: null               # 自定义 CLI 可执行文件路径（null = 自动检测）

evaluator:
  type: python                 # python | docker | custom
  entry: evaluate.py           # 评估脚本入口
  timeout: 300                 # 每个任务的超时时间（秒）

harness:
  language: python             # Harness 代码语言
  entry: harness.py            # Harness 入口文件
  editable_files:              # Proposer 可修改的文件列表
    - harness.py
    - prompt_template.txt

evolution:
  mode: batch                  # batch | online
  trigger:
    strategy: accumulate        # degradation | accumulate | cron | manual
    accumulate_count: 50        # 每积累 N 条新 trace 触发进化（默认：50）
    min_samples: 5              # 进化前最少 trace 数
    window_size: 20             # 分数分析滑动窗口大小
    threshold: -0.05            # 触发 degradation 策略的分数下降阈值
  auto_apply: false             # 自动应用改进后的 harness
  max_iterations: 3             # 每轮进化的迭代次数
  record_output: true           # 在 trace 中捕获 stdout/stderr
```

也可通过 CLI 修改配置：`ph config set search.max_iterations 30`

---

## 安装

### pip（推荐）

```bash
pip install polyharness      # 需要 Python >= 3.12
ph --version
```

### npm / npx

```bash
npm install -g polyharness   # postinstall 自动安装 Python 包
npx polyharness doctor       # 或无需全局安装直接运行
```

npm 包是一个轻量 Node.js 包装器（`bin/ph.mjs`），它会查找并调用 Python CLI。检查顺序是：PATH 上的 `ph` → `python -m polyharness` → 自动发现父目录中的 `.venv`。

### 从源码安装

```bash
git clone https://github.com/weijt606/polyharness.git
cd polyharness

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# 或: pip install anthropic click pydantic pyyaml rich && export PYTHONPATH="$PWD/src"

python -m polyharness --version
```

---

## CLI 参考

| 命令 | 说明 |
|------|------|
| `ph doctor` | 检测已安装的 agent 和环境状态 |
| `ph new [目录]` | 生成 harness 项目脚手架（harness.py + tasks + evaluate.py） |
| `ph init` | 初始化 workspace，自动复制 harness、任务、评估脚本 |
| `ph run` | 启动优化搜索循环 |
| `ph status` | 进度表格，包含耗时、改进率和增量 |
| `ph log` | 搜索树带增量（Δ）列，或用 `--flat` 查看表格视图 |
| `ph best` | 展示最佳候选：分数、逐任务明细、变更摘要 |
| `ph compare A B` | 对比两个迭代：分数差异 + 统一代码 diff |
| `ph diff <N>` | `compare 0 <N>` 的快捷方式 |
| `ph leaderboard` | 候选排名表（`--top N`、`--tasks` 展开每题分数） |
| `ph trace <N>` | 查看某次迭代的 stdout、stderr、metrics、退出码 |
| `ph report` | 生成完整 markdown 报告，包含分数趋势和逐任务表格 |
| `ph apply` | 将最优 harness 回写到 `base_harness/`，或通过 `--target` 指定目录 |
| `ph export <dir>` | 导出候选到任意目录，可选 `--include-meta` |
| `ph clean` | 清理候选目录释放磁盘空间（`--keep-best`、`-y`） |
| `ph config show` | 显示当前 workspace 配置 |
| `ph config set K V` | 用 dot-notation 修改配置值，并进行校验 |
| `ph wrap <cmd> [args]` | 透明转发命令，记录执行 trace（耗时、退出码、输出） |
| `ph traces list` | 以表格列出已收集的 traces（`-n` 限制数量） |
| `ph traces show <id>` | 展示 trace 完整详情，包括捕获的输出 |
| `ph traces stats` | 汇总统计：总 traces 数、已评分数、各 agent 分布 |
| `ph traces clear` | 清除已收集的 traces（`--keep N` 保留最新、`-y` 跳过确认） |
| `ph evolve` | 基于已收集的 traces 触发一轮在线进化循环 |
| `ph shell-hook install` | 安装 shell 钩子，自动包裹 agent 命令（claude、claw、codex、opencode） |
| `ph shell-hook uninstall` | 从 rc 文件中移除 shell 钩子 |
| `ph shell-hook status` | 检查 shell 钩子是否已安装 |
| `ph upgrade` | 升级 PolyHarness 到最新版本 |
| `ph uninstall` | 卸载 PolyHarness（`-y` 跳过确认） |

### 全局标志

```
-v, --verbose        显示详细输出
-q, --quiet          抑制非必要输出
```

### `ph init` 选项

```
--agent <name>       后端: claude-code | claw-code | codex | opencode | api | local
--workspace <dir>    Workspace 目录（默认：当前目录）
--base-harness <dir> 将起始 harness 代码复制到 workspace
--task-dir <dir>     将 tasks/ 文件夹和 evaluate.py 复制到 workspace
--eval-script <path> 将指定的 evaluate.py 复制到 workspace
```

### `ph run` 选项

```
--max-iterations N   覆盖最大迭代数
--dry-run            仅评估基线 harness，跳过搜索
--resume             从上次中断处继续搜索
--backend <name>     覆盖 proposer 后端，无需修改配置
--strategy <name>    覆盖父候选选择策略: best | tournament | all
```

### `ph wrap` 选项

```
--workspace PATH     将 trace 关联到指定 workspace
--store PATH         自定义 trace 存储目录
--no-record-output   不捕获 stdout/stderr（仅记录元数据）
--auto-evolve        traces 积累足够时自动触发进化
```

### `ph evolve` 选项

```
--workspace PATH          待进化的 workspace（默认 .ph_workspace）
--store PATH              自定义 trace 存储目录
--max-iterations INTEGER  覆盖本轮进化的最大迭代数
```

---

## 示例

以下分数轨迹来自本仓库内置示例在当前 `local` 后端下的实测结果，数值按展示需要做了四舍五入。它们不是 Meta-Harness 论文结果，也不是外部 benchmark 分数。

### 文本分类（情感分析）

```bash
ph init --agent local --template text-classification
ph run --max-iterations 3

# iter_0: 0.65 → iter_1: 1.00 ★ （简单词表 → 扩展词库）
```

### 数学应用题（数值推理）

```bash
ph init --agent local --template math-word-problems
ph run --max-iterations 5

# iter_0: 0.35 → iter_1: 0.50 → iter_2: 0.65 → iter_3: 0.90 ★
# （简单乘法 → 运算检测 → 均值/百分比 → 多步推理）
```

### 代码生成（函数合成）

```bash
ph init --agent local --template code-generation
ph run --max-iterations 5

# iter_0: 0.27 → iter_1: 0.50 → iter_2: 0.68 → iter_3: 0.95 ★
# （5 个关键词 → 10 种模式 → 复合逻辑 → 全面覆盖）
```

### API 调用（端点路由 + 参数提取）

```bash
ph init --agent local --template api-calling
ph run --max-iterations 5

# iter_0: 0.19 → iter_1: 0.55 → iter_2: 0.77 → iter_3: 0.87 ★
# （关键词匹配 → 宽泛路由 → 参数辅助 → 完整正则提取）
```

### RAG 问答（检索 + 答案抽取）

```bash
ph init --agent local --template rag-qa
ph run --max-iterations 5

# iter_0: 0.51 → iter_1: 0.79 ★
# （词重叠 → 停用词过滤检索 + 句子评分）
```

---

## 项目结构

```
polyharness/
├── src/polyharness/
│   ├── cli.py                   # Click CLI —— 25 个命令/子命令
│   ├── config.py                # Pydantic 配置模型（+ EvolutionConfig）
│   ├── collector.py             # 在线进化 trace 收集器
│   ├── orchestrator.py          # Meta-Harness 搜索循环 + 进度条 + 错误恢复
│   ├── workspace.py             # 文件系统 workspace + agent 指令注入
│   ├── search_log.py            # JSONL 追加式搜索日志
│   ├── doctor.py                # 所有后端的环境检测
│   ├── evaluator/
│   │   └── evaluator.py         # PythonEvaluator（子进程）
│   ├── proposer/
│   │   ├── api_proposer.py      # Anthropic API 直连 + tool-use 循环
│   │   ├── openai_proposer.py   # OpenAI 兼容 API（Ollama、vLLM 等）
│   │   ├── cli_proposer.py      # CLIProposer —— 统一子进程管理
│   │   ├── local_proposer.py    # 离线规则引擎（5 种任务类型）
│   │   └── adapters/            # 逐 agent CLI 适配器
│   │       ├── claude_code.py   # claude -p
│   │       ├── claw_code.py     # claw -p
│   │       ├── codex.py         # codex --quiet --auto-edit
│   │       ├── hermes.py        # hermes chat -q
│   │       └── opencode.py      # opencode -p
│   └── templates/               # 5 个内置任务模板
│       ├── text-classification/
│       ├── math-word-problems/
│       ├── code-generation/
│       ├── rag-qa/
│       └── api-calling/
├── tests/                       # 173 个测试（pytest）
├── bin/                         # npm 包装器（ph.mjs、postinstall.mjs）
├── docs/
│   ├── development/             # 产品路线图 & 技术架构
│   └── research/references/     # Meta-Harness 论文
├── pyproject.toml               # Python 包配置
└── package.json                 # npm 包配置
```

## 本地开发

```bash
git clone https://github.com/weijt606/polyharness.git && cd polyharness
python -m venv .venv && source .venv/bin/activate
pip install anthropic click pydantic pyyaml rich pytest pytest-cov ruff
export PYTHONPATH="$PWD/src"

python -m pytest tests/      # 运行测试
ruff check src/ tests/       # lint
```

## 文档

- [产品开发](docs/development/product-development.md) —— 路线图、用户场景、成功指标
- [技术架构](docs/development/technical-architecture.md) —— 系统设计与数据流
- [Meta-Harness 论文](docs/research/references/meta-harness-paper.md) —— 理论基础与论文报告的参考结果

---

<p align="center"><strong>给你的 agent 自我进化能力。是时候了。</strong></p>

## 许可

MIT