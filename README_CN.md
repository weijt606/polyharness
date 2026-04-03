# PolyHarness

**让你的 AI Agent 自动进化。**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-80%20passing-brightgreen.svg)]()
[![English](https://img.shields.io/badge/Docs-English-blue.svg)](README.md)

---

你的 AI agent 每次都用同一套 harness 工作 —— 同样的 prompt、同样的工具配置、同样的策略，不管之前失败了多少次。

**PolyHarness 解决这个问题。** 它观察你的 agent 每轮执行结果，从全部历史中学习，然后自动发现更优的配置。你只需运行一条命令 —— 你的 agent 就会变强。

|  |  |
|---|---|
| **自我进化** | 你的 agent 通过迭代搜索自动改进自身 harness，无需手动调参。 |
| **6 种 Agent 后端** | Claude Code · Claw Code · Codex · OpenCode · API 直连 · Local —— 任意 CLI agent 即插即用。 |
| **全量历史** | 每轮迭代的代码、分数和轨迹完整保留。非马尔可夫搜索碾压盲目重试。 |
| **搜索树** | 可视化优化路径，任意两个候选之间可对比逐任务分数差异和代码 diff。 |
| **一条命令搭建** | `ph init --base-harness ... --task-dir ...` —— 自动复制文件、配置 workspace，完事。 |
| **闭环** | init → run → inspect → apply，最优 harness 自动回写到你的项目。 |

---

## 背景故事

Stanford [Meta-Harness 论文](https://arxiv.org/abs/2603.28052)（IRIS Lab, 2026）证明了一个意外的结论：**harness 设计是 agent 性能的第一杠杆** —— 比模型选择、prompt 工程、甚至微调更有效。

核心发现：当你给 AI agent 提供*完整的诊断历史* —— 不仅是最新分数，而是每次尝试的代码、执行轨迹、失败模式 —— 它就能*系统性地进化*自己的 harness 配置。论文把这称为"非马尔可夫搜索"，并证明它远超简单的 best-of-N 采样。

但论文只发布了最终优化好的产物（`agent.py`）。**搜索框架本身没有开源。**

PolyHarness 填补了这个空白。它是让 Meta-Harness 搜索对所有人可用的开源引擎 —— 适用于任何 agent、任何任务、任何评估流水线。

> **打个比方：**
> - Memory 工具（如 Supermemory）给 agent 加上跨对话的**持久记忆**。
> - **PolyHarness 给 agent 加上持久的自我进化能力** —— 让它随时间推移越做越好。

---

## 使用 PolyHarness

<table>
<tr>
<td width="50%" valign="top">

### 我用 AI 编程 agent
你在用 Claude Code、Codex 或其他 agent。
你想让它在你的特定任务上表现更好 —— 但不想手动调 prompt。

```bash
pip install poly-harness
ph init --agent claude-code --task-dir ./my_tasks
ph run
ph apply
```

你的 agent harness 已被优化。搞定。

**[→ 跳到快速开始](#快速开始)**

</td>
<td width="50%" valign="top">

### 我在做 agent 框架

你在开发 AI agent 或工具，想把自动优化集成为一项功能。

PolyHarness 提供可插拔的适配器 API ——
实现 3 个方法，你的 agent 就拥有自我进化能力。

```python
class MyAgentAdapter(CLIAdapter):
    def build_command(self, prompt, cwd):
        return ["my-agent", "--prompt", prompt]
    def parse_output(self, stdout, stderr, code):
        return CLIResult(...)
```

**[→ 跳到架构说明](#工作原理)**

</td>
</tr>
</table>

---

## 快速开始

### 1. 安装

```bash
pip install poly-harness        # Python >= 3.12
# 或者
npm install -g poly-harness     # Node.js 封装，postinstall 自动装 Python 包
```

### 2. 检测环境

```bash
ph doctor
```

自动检测哪些 agent 后端（Claude Code、Codex 等）已安装，并显示状态。

### 3. 初始化 workspace

```bash
ph init --agent claude-code \
        --base-harness ./my_harness/ \
        --task-dir ./my_tasks/ \
        --eval-script ./evaluate.py
```

会将你的 harness 代码、测试用例和评估脚本复制到结构化 workspace 中，并自动配置。无需手动编辑 YAML。

### 4. 运行优化循环

```bash
ph run
```

编排器：复制 harness → 让 Proposer agent 改进它 → 评估结果 → 存储数据 → 重复。

### 5. 查看并应用

```bash
ph log                         # 搜索树可视化
ph status                      # 进度表格
ph best                        # 最佳候选详情
ph compare 0 5                 # 对比两个迭代（分数 + 代码 diff）

ph apply                       # 将最优 harness 回写到 base_harness/
ph export ./my-optimized       # 或导出到任意目录
```

### 立即体验（无需 API key）

```bash
cd examples/math-word-problems

ph init --agent local \
        --base-harness ./base_harness \
        --task-dir . \
        --workspace .ph_workspace

ph run --workspace .ph_workspace --max-iterations 5
ph log --workspace .ph_workspace

# Search Tree
# └── iter_0  0.3500
#     └── iter_1  0.5000
#         └── iter_2  0.6500
#             └── iter_3  0.9000 ★
```

分数从 0.35 跳到 0.90，仅 3 轮迭代。`local` 后端用的是确定性规则 —— 真实的 agent 后端（Claude Code、Codex）能发现更有创造力的优化方案。

---

## 工作原理

PolyHarness 运行 **Meta-Harness 搜索循环** —— 一个 AI agent 迭代优化自身配置的过程：

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   你                            PolyHarness                  │
│    │                              │                          │
│    ├── ph init ──────────────────→│ 创建 workspace           │
│    │   (harness + tasks + eval)   │ 复制文件                 │
│    │                              │ 注入 CLAUDE.md           │
│    │                              │                          │
│    ├── ph run ───────────────────→│ 启动搜索循环：           │
│    │                              │                          │
│    │   ┌──────────────────────────┤                          │
│    │   │  步骤 1: 选择 parent     │ 最优 或 Tournament       │
│    │   │  步骤 2: 复制 harness    │ 从 parent → candidate    │
│    │   │  步骤 3: 提出改进        │ Agent 阅读全部历史       │
│    │   │  步骤 4: 评估            │ 跑测试，获取分数         │
│    │   │  步骤 5: 存储结果        │ 代码 + 分数 + 轨迹       │
│    │   │  步骤 6: 检查停止条件    │ 有改进？还有耐心？       │
│    │   └──────────┬───────────────┤                          │
│    │              └── 循环 ───────┘                          │
│    │                              │                          │
│    ├── ph log ───────────────────→│ 展示搜索树               │
│    ├── ph compare 0 5 ──────────→│ 分数差异 + 代码 diff     │
│    └── ph apply ─────────────────→│ 回写最优结果             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 为什么有效：非马尔可夫搜索

传统做法：运行 agent → 看分数 → 重试。每次尝试互相独立。

**PolyHarness 不一样。** 每轮迭代存储：
- 候选的完整源代码
- 逐任务分数（不只是总分）
- 完整执行轨迹（stdout、stderr、退出码）
- 元数据（父候选、proposer 模型、改动摘要）

Proposer 在生成下一个候选之前会读取**所有这些信息**。它能看到*为什么*之前的尝试失败了、*哪些具体任务*退步了、*什么代码改动*导致了问题。这就是 Meta-Harness 论文发现全上下文搜索比仅看分数的搜索高出 15+ 个百分点的原因。

---

## 支持的 Agent 后端

| 后端 | 命令 | 说明 |
|------|------|------|
| `api` | — | 默认。Anthropic API 直连，只需 `ANTHROPIC_API_KEY` |
| `claude-code` | `claude -p` | 官方 Claude Code CLI（需订阅） |
| `claw-code` | `claw -p` | 开源 Claw Code CLI |
| `codex` | `codex --quiet` | OpenAI Codex CLI |
| `opencode` | `opencode -p` | OpenCode CLI |
| `local` | — | 离线规则引擎（开发/测试用） |

`ph doctor` 自动检测所有可用后端并显示状态。

运行 `ph init --agent claude-code` 时，PolyHarness 会自动在 workspace 中生成 `CLAUDE.md` 指令文件，告诉 agent 如何作为 Proposer 执行优化任务。`CLAW.md`、`CODEX.md`、`OPENCODE.md` 同理 —— 每个 agent 都用原生指令格式。

---

## 安装

### pip（推荐）

```bash
pip install poly-harness     # 需要 Python >= 3.12
ph --version
```

### npm / npx

```bash
npm install -g poly-harness  # postinstall 自动安装 Python 包
npx poly-harness doctor      # 或不全局安装直接运行
```

npm 包是一层薄薄的 Node.js 封装（`bin/ph.mjs`），用于查找并调用 Python CLI。检测顺序：PATH 上的 `ph` → `python -m poly_harness` → 父目录中的 `.venv`。

### 从源码

```bash
git clone https://github.com/weijt606/poly-harness.git
cd poly-harness

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# 或者: pip install anthropic click pydantic pyyaml rich && export PYTHONPATH="$PWD/src"

python -m poly_harness --version
```

---

## CLI 命令参考

| 命令 | 说明 |
|------|------|
| `ph doctor` | 检测已安装的 agent 和环境状态 |
| `ph init` | 初始化 workspace，自动复制 harness、tasks、eval 脚本 |
| `ph run` | 启动优化搜索循环 |
| `ph status` | 查看进度表格（迭代 / 父代 / 分数 / 最优） |
| `ph log` | 搜索树可视化（或 `--flat` 表格视图） |
| `ph best` | 查看最佳候选：分数、逐任务明细、改动摘要 |
| `ph compare A B` | 对比两个迭代：分数差异 + 统一代码 diff |
| `ph apply` | 将最优 harness 回写到 `base_harness/`（或 `--target` 目录） |
| `ph export <dir>` | 导出候选到任意目录（可选 `--include-meta`） |

### `ph init` 选项

```
--agent <name>       后端: claude-code | claw-code | codex | opencode | api | local
--workspace <dir>    Workspace 目录（默认：当前目录）
--base-harness <dir> 复制起始 harness 代码到 workspace
--task-dir <dir>     复制 tasks/ 文件夹和 evaluate.py 到 workspace
--eval-script <path> 复制指定的 evaluate.py 到 workspace
```

---

## 示例

### 文本分类（情感分析）

```bash
cd examples/text-classification
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 3

# iter_0: 0.65 → iter_1: 1.00 ★  (朴素词表 → 扩展词典)
```

### 数学文字题（数值推理）

```bash
cd examples/math-word-problems
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.35 → iter_1: 0.50 → iter_2: 0.65 → iter_3: 0.90 ★
# (朴素乘法 → 运算检测 → 均值/百分比 → 多步推理)
```

### 代码生成（函数合成）

```bash
cd examples/code-generation
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.27 → iter_1: 0.50 → iter_2: 0.68 → iter_3: 0.95 ★
# （5 个关键词 → 10 种模式 → 复合逻辑 → 全面覆盖）
```

### API 调用（端点路由 + 参数提取）

```bash
cd examples/api-calling
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.19 → iter_1: 0.55 → iter_2: 0.77 → iter_3: 0.87 ★
# （关键词匹配 → 宽泛路由 → 参数辅助 → 完整正则提取）
```

### RAG 问答（检索 + 答案抽取）

```bash
cd examples/rag-qa
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.51 → iter_1: 0.79 ★
# （词重叠 → 停用词过滤检索 + 句子评分）
```

---

## 项目结构

```
src/poly_harness/
├── cli.py                   # Click CLI — 9 个命令
├── config.py                # Pydantic 配置模型
├── orchestrator.py          # Meta-Harness 搜索循环 + tournament 选择
├── workspace.py             # 文件系统 workspace + agent 指令注入
├── search_log.py            # JSONL 追加式搜索日志
├── doctor.py                # 环境检测
├── evaluator/
│   └── evaluator.py         # PythonEvaluator（子进程）
├── proposer/
│   ├── api_proposer.py      # Anthropic API 直连 + tool-use 循环
│   ├── cli_proposer.py      # CLIProposer — 统一子进程管理
│   ├── local_proposer.py    # 离线规则引擎（5 种任务类型）
│   └── adapters/            # 逐 agent CLI 适配器
│       ├── claude_code.py   # claude -p
│       ├── claw_code.py     # claw -p
│       ├── codex.py         # codex --quiet --auto-edit
│       └── opencode.py      # opencode -p

bin/
├── ph.mjs                   # npm 封装
└── postinstall.mjs          # npm postinstall

examples/
├── text-classification/     # 20 个测试用例
├── math-word-problems/      # 20 个测试用例
├── code-generation/         # 20 个任务 × 3 组输入
├── api-calling/             # 20 个测试用例
└── rag-qa/                  # 20 个 QA 对 + 10 篇知识库文档

tests/                       # 86 个测试 (pytest)
```

## 本地开发

```bash
git clone https://github.com/weijt606/poly-harness.git && cd poly-harness
python -m venv .venv && source .venv/bin/activate
pip install anthropic click pydantic pyyaml rich pytest pytest-cov ruff
export PYTHONPATH="$PWD/src"

python -m pytest tests/      # 跑测试
ruff check src/ tests/       # 检查代码风格
```

## 文档

- [产品开发](docs/development/product-development.md) — 路线图、用户场景、成功指标
- [技术架构](docs/development/technical-architecture.md) — 系统设计与数据流
- [Meta-Harness 论文](docs/research/references/meta-harness-paper.md) — 理论基础
- [信息瓶颈假说](docs/research/information-bottleneck-hypothesis.md) — 为什么全量上下文至关重要
- [TBench2 产物分析](docs/research/tbench2-artifact-code-analysis.md)

---

<p align="center"><strong>给你的 agent 加上自我进化能力。是时候了。</strong></p>

## 许可

MIT
