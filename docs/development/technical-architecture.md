---
title: "PolyHarness — 技术架构文档 / Technical Architecture"
date: 2026-04-02
status: draft
version: "0.1.0"
---

# PolyHarness — 技术架构文档 / Technical Architecture

## 1. 系统总览

### 1.1 架构概览

```
┌──────────────────────────────────────────────────────────────┐
│                      PolyHarness 系统                       │
│                                                              │
│  ┌────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │ CLI / API  │→ │  Orchestrator │→ │  Workspace (FS)   │    │
│  └────────────┘  │  (编排器)     │  │                   │    │
│                  │              │  │  candidates/       │    │
│                  │  for i in N: │  │  ├── iter_0/       │    │
│                  │   propose()  │←→│  ├── iter_1/       │    │
│                  │   evaluate() │  │  └── ...           │    │
│                  │   store()    │  │                   │    │
│                  │   apply()    │  │  base_harness/     │    │
│                  └──────┬───────┘  │  config.yaml        │    │
│                         │         │  search_log.jsonl   │    │
│                    ┌────┴────┐    └───────────────────┘    │
│                    │         │                              │
│              ┌─────┴──┐ ┌───┴──────┐                      │
│              │Proposer│ │Evaluator │                      │
│              │(Agent) │ │(Sandbox) │                      │
│              └────────┘ └──────────┘                      │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 核心数据流

```
每一轮迭代 (iteration i):
═══════════════════════════

  ┌─────────────────────────────────────────────────────────┐
  │ Step 1: Propose                                         │
  │                                                         │
  │  Proposer Agent 启动                                    │
  │    → 读取 workspace/ 中所有历史候选、分数、trace          │
  │    → 分析失败模式，识别改进方向                            │
  │    → 在 candidates/iter_{i}/ 写入新 harness 代码          │
  └───────────────────────┬─────────────────────────────────┘
                          │
  ┌───────────────────────▼─────────────────────────────────┐
  │ Step 2: Evaluate                                        │
  │                                                         │
  │  Evaluator 启动（Docker 沙箱或本地进程）                  │
  │    → 加载 candidates/iter_{i}/harness 代码               │
  │    → 在任务集上运行评估                                   │
  │    → 收集 stdout/stderr/exitcode/metrics                │
  └───────────────────────┬─────────────────────────────────┘
                          │
  ┌───────────────────────▼─────────────────────────────────┐
  │ Step 3: Store                                           │
  │                                                         │
  │  编排器写入结果                                           │
  │    → candidates/iter_{i}/score.json                     │
  │    → candidates/iter_{i}/traces/                        │
  │    → search_log.jsonl (追加当轮摘要)                     │
  └─────────────────────────────────────────────────────────┘
```

### 1.3 与论文实现的映射

| 论文组件 | 论文实现 | PolyHarness 实现 |
|---------|---------|------------------|
| **Proposer** | Claude Code (Opus 4.6) 操作文件系统 | Anthropic API + 工具循环 / Claude Code CLI / Claw Code CLI / 任意 agent CLI |
| **文件系统** | 论文未公开具体结构 | 公开定义的 workspace 规范（见 §2） |
| **评估器** | Harbor 框架 + Docker | Python evaluator 接口 + Docker 可选 |
| **搜索循环** | 论文未公开 | `Orchestrator` 类 |
| **Prompt caching** | `anthropic_caching.py` | 复用同一思路 |
| **配置回写** | 无（论文不涉及） | `ph apply` — 将最优 harness 回写到 agent 原生配置 |

### 1.4 架构约束（与产品目标对齐）

为满足产品化、可持续和可复现目标，技术架构必须满足以下约束：

1. **产品可交付约束**
    - 首发形态必须是本地可安装 CLI（`pip install poly-harness` + `ph run`）。
    - 核心路径不依赖复杂基础设施，默认本地运行，容器/云作为可选能力。

2. **可持续演进约束**
    - 核心编排层（Orchestrator/Workspace/Evaluator）不得依赖任何单一 Agent 的私有内部实现。
    - 所有 Agent 集成必须通过适配器边界实现（Adapter Pattern），保证可替换。

3. **复现与探索约束**
    - 必须保留可复现论文关键结论的实验路径（Full / Summary / Scores-Only 消融）。
    - 必须支持新增 Agent 架构实验，不需要修改核心循环。

4. **多后端约束**
    - 主线必须支持多 Proposer 后端（API、Claude Code、Claw Code，预留 Codex/OpenCode）。
    - 单一后端深度定制（如 Claw Code 专项优化）只能以插件/扩展包方式落地，不进入核心依赖。

## 2. Workspace 文件系统规范

### 2.1 目录结构

Workspace 是 Meta-Harness 的核心——Proposer 通过文件系统获取全量诊断上下文。

```
workspace/
├── CLAW.md                          # Proposer 行为指令（等价论文的 proposer prompt）
├── config.yaml                      # 搜索配置
├── task_spec.md                     # 任务描述（给 Proposer 和候选 harness 参考）
│
├── base_harness/                    # 初始 harness（搜索起点）
│   ├── harness.py                   # harness 代码入口
│   ├── prompt_template.txt          # 系统提示词模板
│   └── tools.json                   # 工具定义（可选）
│
├── candidates/                      # 所有搜索候选（核心：Proposer 读取的历史）
│   ├── iter_0/                      # 第 0 轮 = base_harness 的评估
│   │   ├── harness.py               # 候选代码（= base_harness 的副本）
│   │   ├── prompt_template.txt      # 可能被修改的提示词
│   │   ├── diff_from_parent.patch   # 与父候选的 diff
│   │   ├── score.json               # 评估分数
│   │   ├── metadata.json            # 来源、父候选ID、proposer 的推理
│   │   └── traces/                  # 执行轨迹
│   │       ├── task_001.stdout      # 每个任务的标准输出
│   │       ├── task_001.stderr      # 错误输出
│   │       ├── task_001.exitcode    # 退出码
│   │       └── task_001.metrics.json# 细粒度指标
│   │
│   ├── iter_1/
│   │   ├── harness.py
│   │   ├── diff_from_parent.patch   # diff vs iter_0
│   │   ├── score.json
│   │   ├── metadata.json
│   │   └── traces/
│   │       └── ...
│   └── ...
│
├── search_log.jsonl                 # 搜索日志（每行一个 JSON 对象）
│
└── summary/                         # 可选：汇总信息
    ├── leaderboard.json             # 当前排行榜
    └── best_candidate.txt           # 最佳候选 ID
```

### 2.2 关键文件格式

**`config.yaml`**

```yaml
# 搜索配置
search:
  max_iterations: 20           # 最大搜索轮次
  early_stop_patience: 5       # 连续无提升则停止
  parent_selection: "best"     # 父候选选择策略: best | tournament | all

# Proposer 配置
proposer:
  model: "claude-sonnet-4-20250514"     # Proposer 模型
  max_tokens: 16384            # 单次输出上限
  temperature: 0.7             # 生成温度
  backend: "api"               # api | claude-code | claw-code
  # api:         Anthropic API 直连 + 自建工具循环（零外部依赖）
  # claude-code: 官方 Claude Code CLI（claude --print，需订阅）
  # claw-code:   开源 Claw Code CLI（claw --print，需安装）
  cli_path: null               # CLI 后端的可执行文件路径（null = 自动检测）
  tools:                       # Proposer 可用工具（仅 api 后端需要）
    - bash
    - file_read
    - file_write
    - grep

# 评估配置
evaluator:
  type: "python"               # python | docker | custom
  entry: "evaluate.py"         # 评估脚本入口
  timeout: 300                 # 单任务超时（秒）
  tasks:
    - "tasks/task_001.json"
    - "tasks/task_002.json"

# 目标 harness 配置
harness:
  language: "python"           # harness 代码语言
  entry: "harness.py"          # harness 入口文件
  editable_files:              # Proposer 允许修改的文件
    - "harness.py"
    - "prompt_template.txt"
    - "tools.json"
```

**`score.json`**

```json
{
  "iteration": 3,
  "parent": "iter_1",
  "overall_score": 0.723,
  "task_scores": {
    "task_001": 0.85,
    "task_002": 0.60,
    "task_003": 0.72
  },
  "metadata": {
    "eval_duration_sec": 45.2,
    "token_usage": {
      "input": 12500,
      "output": 3400
    }
  }
}
```

**`metadata.json`**

```json
{
  "iteration": 3,
  "parent": "iter_1",
  "proposer_model": "claude-sonnet-4-20250514",
  "proposer_reasoning": "iter_1 在 task_002 上失败因为缺少 retry 逻辑...",
  "changes_summary": "添加了 exponential backoff retry 到 API 调用层",
  "timestamp": "2026-04-02T14:30:00Z"
}
```

**`search_log.jsonl`**（每行一条）

```json
{"iteration": 0, "parent": null, "score": 0.45, "best_so_far": 0.45, "timestamp": "..."}
{"iteration": 1, "parent": "iter_0", "score": 0.52, "best_so_far": 0.52, "timestamp": "..."}
{"iteration": 2, "parent": "iter_1", "score": 0.48, "best_so_far": 0.52, "timestamp": "..."}
{"iteration": 3, "parent": "iter_1", "score": 0.72, "best_so_far": 0.72, "timestamp": "..."}
```

### 2.3 设计原则

| 原则 | 理由 | 来源 |
|------|------|------|
| **一切皆文件** | Proposer 通过文件系统工具（cat/grep/ls）访问全部信息 | 论文核心设计 |
| **全量保留** | 不删除、不压缩历史候选——信息瓶颈假说的核心验证 | 论文 Table 3 消融 |
| **人类可读** | 所有文件使用文本格式（JSON/YAML/TXT/Patch），便于调试 | 工程实践 |
| **diff 优于 snapshot** | 存储候选间的 diff 帮助 Proposer 快速理解变化 | 论文 Appendix A: 41% 源码读取 |
| **trace 与代码并存** | 每个候选的执行轨迹和代码在同一目录下 | 论文: 40% trace 读取 |

## 3. 核心组件设计

### 3.1 Orchestrator（编排器）

编排器是系统的中枢，协调 Proposer 和 Evaluator 的循环。

```python
# 伪代码：orchestrator.py

class Orchestrator:
    """Meta-Harness 搜索循环编排器"""

    def __init__(self, config: SearchConfig, workspace: Workspace):
        self.config = config
        self.workspace = workspace
        self.proposer = create_proposer(config.proposer)
        self.evaluator = create_evaluator(config.evaluator)
        self.search_log = SearchLog(workspace.log_path)

    def run(self, resume: bool = False) -> SearchResult:
        """主搜索循环（支持断点续搜）"""

        # 如果 resume=True 且日志非空，从上次中断处恢复
        if resume and len(self.search_log) > 0:
            entries = self.search_log.entries
            best_score = self.search_log.best_score
            best_iteration = self.search_log.best_iteration
            start_iter = max(e.iteration for e in entries) + 1
            # 从日志尾部重算 patience_counter
            patience_counter = recalc_patience(entries, best_score)
        else:
            # Step 0: 评估初始 harness
            base_score = self.evaluator.evaluate(...)
            best_score = base_score.overall
            best_iteration = 0
            patience_counter = 0
            start_iter = 1

        # Dry-run 模式：max_iterations=0 时只评估 base
        if self.config.max_iterations == 0:
            return SearchResult(best_iteration=0, ...)

        # Rich 进度条：显示当前轮次、进度、当前最优分数
        with Progress(SpinnerColumn(), BarColumn(), ...) as progress:
            for i in range(start_iter, self.config.max_iterations + 1):

                try:
                    # Step 1: 选择父候选
                    parent = self.select_parent(i)

                    # Step 2: Proposer 生成新候选
                    candidate = self.proposer.propose(
                        workspace=self.workspace,
                        parent=parent,
                        iteration=i
                    )

                    # Step 3: 评估新候选
                    score = self.evaluator.evaluate(
                        candidate.harness_path,
                        self.workspace.tasks
                    )
                except Exception as exc:
                    # 错误恢复：跳过失败轮次，递增 patience
                    patience_counter += 1
                    if patience_counter >= self.config.early_stop_patience:
                        break
                    continue

                # Step 4: 存储结果
                self.workspace.store_iteration(i, candidate, score)
                self.search_log.append(iteration=i, parent=parent, score=score)

                # Step 5: 更新最佳 & 检查早停
                if score.overall > best_score:
                    best_score = score.overall
                    best_iteration = i
                    patience_counter = 0
                else:
                    patience_counter += 1

                if patience_counter >= self.config.early_stop_patience:
                    break

        return SearchResult(
            best_iteration=best_iteration,
            best_score=best_score,
            total_iterations=i
        )

    def select_parent(self, iteration: int) -> str:
        """父候选选择策略"""
        strategy = self.config.parent_selection
        if strategy == "best":
            return self.search_log.best_iteration
        elif strategy == "tournament":
            return self.search_log.tournament_select(k=3)
        elif strategy == "all":
            return None  # Proposer 自行决定基于哪个候选
```

**关键设计决策**：

| 决策 | 选择 | 理由 |
|------|------|------|
| 同步 vs 异步循环 | 同步 | 论文是串行的：每轮 1 个候选 |
| 父候选选择 | 可配置（best/tournament/all）| 论文用 "all"（Proposer 看全部历史自行决定），但 "best" 更省 context |
| 早停策略 | patience-based | 简单有效，避免浪费 API 预算 |
| 断点续搜 | `resume` 参数 | 长时间搜索中断后可从上次迭代继续，无需重新开始 |
| 错误恢复 | try/except + patience | 单轮失败不终止全局搜索，递增 patience 计数器 |
| 进度显示 | Rich Progress bar | 实时展示当前轮次、进度条、当前最优分数 |
| Dry-run | `max_iterations=0` | 仅评估 base harness，不启动搜索循环，用于验证配置 |

### 3.2 Proposer（提案者）

Proposer 是搜索的核心智能——一个 Coding Agent，读取 workspace 中的全部历史，写出新的 harness 候选。

#### 3.2.1 API 后端实现

```python
# 伪代码：proposer.py

class APIProposer:
    """通过 Anthropic API + 工具循环实现的 Proposer"""

    TOOLS = [
        {
            "name": "bash",
            "description": "Execute a shell command",
            "input_schema": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"}
                }
            }
        },
        {
            "name": "file_read",
            "description": "Read a file from the workspace",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"}
                }
            }
        },
        {
            "name": "file_write",
            "description": "Write content to a file",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                }
            }
        },
        {
            "name": "grep",
            "description": "Search for pattern in workspace files",
            "input_schema": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string"}
                }
            }
        }
    ]

    def __init__(self, config: ProposerConfig):
        self.client = anthropic.Client()
        self.config = config

    def propose(self, workspace: Workspace, parent: str, iteration: int) -> Candidate:
        """生成新的 harness 候选"""

        system_prompt = self._build_system_prompt(workspace, parent, iteration)

        messages = [{"role": "user", "content": system_prompt}]

        # Agent 工具循环
        while True:
            response = self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                tools=self.TOOLS,
                messages=messages
            )

            if response.stop_reason == "end_turn":
                break

            # 处理工具调用
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._execute_tool(
                        block.name, block.input, workspace
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result
                    })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return Candidate(
            iteration=iteration,
            parent=parent,
            harness_path=workspace.candidate_path(iteration)
        )

    def _execute_tool(self, name: str, input: dict, workspace: Workspace) -> str:
        """工具执行（限制在 workspace 内）"""
        if name == "bash":
            # 安全：只允许只读命令（ls, cat, grep, diff, wc）
            return sandbox_exec(input["command"], cwd=workspace.root)
        elif name == "file_read":
            path = workspace.resolve(input["path"])
            return read_file(path, input.get("start_line"), input.get("end_line"))
        elif name == "file_write":
            # 限制：只能写入 candidates/iter_{current}/ 目录
            path = workspace.resolve_candidate_write(input["path"])
            return write_file(path, input["content"])
        elif name == "grep":
            return grep_in_workspace(input["pattern"], input.get("path"), workspace.root)
```

#### 3.2.2 Proposer System Prompt 设计

这是系统的关键配置，对标论文中 Proposer 看到的指令。

```markdown
# workspace/CLAW.md（Proposer 指令）

## 你的角色

你是一个 Harness 优化专家。你的任务是阅读 workspace 中所有历史候选
harness 的代码、评估分数和执行轨迹，然后设计一个改进版 harness。

## Workspace 结构

- `base_harness/` — 初始 harness 代码
- `candidates/iter_N/` — 第 N 轮候选，包含：
  - `harness.py` — harness 代码
  - `score.json` — 评估分数
  - `traces/` — 执行轨迹（stdout/stderr/exitcode）
  - `metadata.json` — 来源和变更摘要
  - `diff_from_parent.patch` — 与父候选的 diff
- `task_spec.md` — 任务描述
- `search_log.jsonl` — 搜索历史概览

## 你的工作流

1. 先读 `search_log.jsonl` 了解搜索进度
2. 读 `task_spec.md` 理解任务目标
3. 浏览高分和低分候选的代码与 trace，对比差异
4. 识别失败模式（从 trace 中找具体的错误或低效行为）
5. 设计针对性改进（不要盲目修改）
6. 将新 harness 写入 `candidates/iter_{CURRENT}/`

## 关键原则

- **因果推理**：不要只看分数高低，要理解 *为什么* 某个候选好/差
- **最小修改**：每次只改一个方面，避免混淆变量
- **阅读 trace**：执行轨迹是最有价值的诊断信息（论文核心发现）
- **参考 diff**：`diff_from_parent.patch` 帮你快速定位变化
```

#### 3.2.3 CLI 适配器架构（Phase 3 — 参考 Supermemory 多 Agent 对接模式）

设计灵感来自 [Supermemory](https://github.com/supermemoryai/supermemory) 的多 Agent 插件模式：不是简单换命令名，而是**为每个 Agent 利用其原生配置机制做深度适配**。

```python
# 伪代码：proposer/adapters.py

class CLIAdapter(ABC):
    """CLI 适配器抽象基类"""

    @abstractmethod
    def get_command(self, config: ProposerConfig) -> list[str]:
        """返回 CLI 命令列表"""
        ...

    @abstractmethod
    def setup_workspace(self, workspace: Workspace):
        """在 workspace 中注入该 Agent 的原生配置"""
        ...

    @abstractmethod
    def detect(self) -> bool:
        """检测该 Agent CLI 是否可用"""
        ...


class ClaudeCodeAdapter(CLIAdapter):
    """Claude Code 官方 CLI 适配器"""

    def get_command(self, config):
        cmd = config.cli_path or "claude"
        return [cmd, "--print", "--model", config.model]

    def setup_workspace(self, workspace):
        # 利用 CLAUDE.md 原生指令注入
        proposer_instructions = workspace.read("CLAW.md")
        workspace.write("CLAUDE.md", proposer_instructions)

        # 利用 .claude/settings.json 配置权限
        workspace.write(".claude/settings.json", json.dumps({
            "permissions": {
                "allow": ["Read", "Write candidates/*", "Bash(ls,cat,grep,diff,wc)"],
                "deny": ["Write *", "Bash(rm,mv,cp)"]
            }
        }))

    def detect(self) -> bool:
        return shutil.which("claude") is not None


class ClawCodeAdapter(CLIAdapter):
    """Claw Code 开源 CLI 适配器"""

    def get_command(self, config):
        cmd = config.cli_path or "claw"
        return [cmd, "--print", "--model", config.model]

    def setup_workspace(self, workspace):
        # CLAW.md 原生支持，无需转换
        pass  # workspace/CLAW.md 已存在

    def detect(self) -> bool:
        return shutil.which("claw") is not None


class OpenCodeAdapter(CLIAdapter):
    """OpenCode CLI 适配器（未来扩展）"""

    def get_command(self, config):
        cmd = config.cli_path or "opencode"
        return [cmd, "--print", "--model", config.model]

    def setup_workspace(self, workspace):
        # 利用 OpenCode 的配置机制注入指令
        proposer_instructions = workspace.read("CLAW.md")
        workspace.write(".opencode/instructions.md", proposer_instructions)

    def detect(self) -> bool:
        return shutil.which("opencode") is not None


# 适配器注册表
ADAPTERS = {
    "claude-code": ClaudeCodeAdapter,
    "claw-code": ClawCodeAdapter,
    "opencode": OpenCodeAdapter,
}


class CLIProposer(BaseProposer):
    """统一的 CLI Proposer，通过适配器对接不同 Agent"""

    def __init__(self, config: ProposerConfig):
        self.config = config
        adapter_cls = ADAPTERS[config.backend]
        self.adapter = adapter_cls()

    def propose(self, workspace: Workspace, parent: str, iteration: int) -> Candidate:
        # 1. 利用适配器注入原生配置
        self.adapter.setup_workspace(workspace)

        # 2. 构建命令
        prompt = self._build_prompt(workspace, parent, iteration)
        cmd = [*self.adapter.get_command(self.config), "-p", prompt]

        # 3. 执行
        result = subprocess.run(
            cmd, cwd=workspace.root,
            capture_output=True, timeout=600
        )

        return Candidate(
            iteration=iteration, parent=parent,
            harness_path=workspace.candidate_path(iteration)
        )
```

**适配器的核心价值**：每个 Agent 都有自己的原生配置机制，适配器将统一的 Proposer 指令翻译为各 Agent 的原生格式。

| Agent | 指令文件 | 权限配置 | 特殊能力 |
|-------|---------|---------|----------|
| **Claude Code** | `CLAUDE.md`（原生） | `.claude/settings.json` | 25+ 工具、Skill 系统、Agent 编排 |
| **Claw Code** | `CLAW.md`（原生） | CLAW.md 内联规则 | 25+ 工具、完全可修改 |
| **OpenCode** | `.opencode/instructions.md` | 配置文件 | 待确认 |

#### 3.2.4 `ph init` 和 `ph doctor`（零配置体验）

参考 Supermemory 的 `npx install-mcp --client <name>` 自动适配模式，提供一键环境配置：

```python
# ph doctor — 自动检测可用后端
def doctor():
    print("PolyHarness Environment Check")
    print("═" * 40)

    # 检测 API Key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    print(f"{'✅' if api_key else '❌'} Anthropic API Key: {'configured' if api_key else 'not set'}")

    # 检测 CLI 后端
    for name, adapter_cls in ADAPTERS.items():
        adapter = adapter_cls()
        available = adapter.detect()
        if available:
            version = get_cli_version(name)
            print(f"✅ {name}: v{version} found")
        else:
            print(f"❌ {name}: not found")

    # 推荐最佳后端
    print(f"\nRecommended: {recommend_backend()}")


# ph init --agent <name> — 自动配置 workspace
def init(agent: str, workspace: Path):
    adapter = ADAPTERS[agent]()

    if not adapter.detect():
        print(f"Error: {backend} CLI not found. Install it first.")
        return

    # 写入 config.yaml
    config = load_config(workspace)
    config["proposer"]["backend"] = backend
    save_config(workspace, config)

    # 注入原生配置到 workspace
    adapter.setup_workspace(Workspace(workspace))

    print(f"✅ Configured {backend} as Proposer backend")
    print(f"   Run 'ph run' to start searching")
```

```bash
# 用户体验
$ ph doctor
PolyHarness Environment Check
════════════════════════════════════════
✅ Anthropic API Key: configured
✅ claude-code:       v1.2.3 found
✅ claw-code:         v0.9.1 found
❌ opencode:          not found

Recommended: claude-code (highest paper fidelity)

$ ph init --agent claude-code
✅ Configured claude-code as Proposer backend
   Created CLAUDE.md with Proposer instructions
   Created .claude/settings.json with permissions
   Run 'ph run' to start searching
```

**三种后端对比**：

| | API 直连 | Claude Code 官方 | Claw Code 开源 |
|---|---|---|---|
| **依赖** | anthropic SDK | Claude Code 订阅 | Claw Code 安装 (Node.js/Rust) |
| **论文还原度** | 中（自建工具循环） | **最高**（论文 Proposer 就是它） | 高（clean-room 等价） |
| **可控性** | 完全控制工具执行 | 受限于官方 CLI | 可修改源码 |
| **工具数量** | 4 个基础工具 | 25+ 工具族 | 25+ 工具族 |
| **工具安全** | 自行实现沙箱 | Anthropic 权限系统 | Claw 权限系统（可自定义） |
| **上下文管理** | 手动管理 prompt caching | 自动管理 | 自动管理 |
| **指令注入** | 手动注入 system prompt | ✅ CLAUDE.md 原生 | ✅ CLAW.md 原生 |
| **调试能力** | 可看完整 API 交互 | 只看最终输出 | 只看最终输出（可改源码增强） |
| **成本模式** | 按 token 付费 | 订阅制 | 按 token 付费 |
| **推荐阶段** | MVP (Phase 1) | Phase 3 | Phase 3 |
| **扩展性** | 需自建新 Proposer 类 | 适配器注册即可 | 适配器注册即可 |

### 3.3 Evaluator（评估器）

#### 3.3.1 评估器接口

```python
# 伪代码：evaluator.py

class Evaluator(ABC):
    """评估器抽象基类"""

    @abstractmethod
    def evaluate(self, harness_path: Path, tasks: list[Task]) -> EvalResult:
        """运行候选 harness 并返回评估结果"""
        ...

class PythonEvaluator(Evaluator):
    """本地 Python 评估器（MVP）"""

    def __init__(self, eval_script: Path, timeout: int = 300):
        self.eval_script = eval_script
        self.timeout = timeout

    def evaluate(self, harness_path: Path, tasks: list[Task]) -> EvalResult:
        task_scores = {}
        traces = {}

        for task in tasks:
            result = subprocess.run(
                ["python", str(self.eval_script),
                 "--harness", str(harness_path),
                 "--task", str(task.path)],
                capture_output=True,
                timeout=self.timeout,
                text=True
            )

            task_scores[task.id] = parse_score(result.stdout)
            traces[task.id] = TraceRecord(
                stdout=result.stdout,
                stderr=result.stderr,
                exitcode=result.returncode
            )

        return EvalResult(
            overall=mean(task_scores.values()),
            task_scores=task_scores,
            traces=traces
        )

class DockerEvaluator(Evaluator):
    """Docker 沙箱评估器（Phase 2）"""

    def __init__(self, dockerfile: Path, timeout: int = 300):
        self.dockerfile = dockerfile
        self.timeout = timeout

    def evaluate(self, harness_path: Path, tasks: list[Task]) -> EvalResult:
        # 1. 构建包含候选 harness 的 Docker 镜像
        image = self._build_image(harness_path)

        task_scores = {}
        traces = {}

        for task in tasks:
            # 2. 在隔离容器中运行评估
            container = self._run_container(image, task)

            # 3. 收集结果和轨迹
            task_scores[task.id] = container.score
            traces[task.id] = TraceRecord(
                stdout=container.logs(stdout=True),
                stderr=container.logs(stderr=True),
                exitcode=container.wait()["StatusCode"]
            )

            container.remove()

        return EvalResult(
            overall=mean(task_scores.values()),
            task_scores=task_scores,
            traces=traces
        )
```

#### 3.3.2 用户自定义评估脚本规范

```python
# 用户编写的 evaluate.py 接口约定

"""
Usage: python evaluate.py --harness <path> --task <task_json>

输入:
  --harness: 候选 harness 目录路径
  --task:    任务 JSON 文件路径

输出 (stdout):
  最后一行必须是 JSON: {"score": 0.85, "details": {...}}

退出码:
  0: 评估成功
  1: harness 运行时错误（仍记录 trace）
  2: 评估脚本自身错误
"""
```

### 3.4 Workspace 管理器

```python
# 伪代码：workspace.py

class Workspace:
    """管理 Meta-Harness 文件系统 workspace"""

    def __init__(self, root: Path):
        self.root = root

    def init(self, base_harness: Path, config: dict):
        """初始化 workspace"""
        (self.root / "candidates").mkdir()
        (self.root / "summary").mkdir()

        # 复制 base harness
        shutil.copytree(base_harness, self.root / "base_harness")

        # 写入配置
        yaml_dump(config, self.root / "config.yaml")

        # 创建空搜索日志
        (self.root / "search_log.jsonl").touch()

    def store_iteration(self, iteration: int, candidate: Candidate, score: EvalResult):
        """存储一轮迭代的完整结果"""
        iter_dir = self.root / "candidates" / f"iter_{iteration}"
        iter_dir.mkdir(exist_ok=True)

        # 存储分数
        json_dump(score.to_dict(), iter_dir / "score.json")

        # 存储 trace
        traces_dir = iter_dir / "traces"
        traces_dir.mkdir(exist_ok=True)
        for task_id, trace in score.traces.items():
            (traces_dir / f"{task_id}.stdout").write_text(trace.stdout)
            (traces_dir / f"{task_id}.stderr").write_text(trace.stderr)
            (traces_dir / f"{task_id}.exitcode").write_text(str(trace.exitcode))

        # 生成 diff
        if candidate.parent:
            parent_dir = self.root / "candidates" / candidate.parent
            diff = generate_diff(parent_dir, iter_dir)
            (iter_dir / "diff_from_parent.patch").write_text(diff)

        # 存储 metadata
        json_dump(candidate.metadata, iter_dir / "metadata.json")

        # 更新排行榜
        self._update_leaderboard()

    def _update_leaderboard(self):
        """更新 summary/leaderboard.json"""
        scores = []
        for iter_dir in sorted((self.root / "candidates").iterdir()):
            score_file = iter_dir / "score.json"
            if score_file.exists():
                data = json_load(score_file)
                scores.append({
                    "iteration": data["iteration"],
                    "score": data["overall_score"],
                    "parent": data.get("parent")
                })

        scores.sort(key=lambda x: x["score"], reverse=True)
        json_dump(scores, self.root / "summary" / "leaderboard.json")
```

## 4. Proposer 安全模型

Proposer 是一个拥有文件系统读写权限的 Agent，安全边界至关重要。

### 4.1 权限矩阵

| 操作 | Proposer 权限 | 实现方式 |
|------|--------------|---------|
| **读取** workspace 内任意文件 | ✅ 允许 | `file_read` 工具，路径检查 |
| **写入** `candidates/iter_{current}/` | ✅ 允许 | `file_write` 白名单路径 |
| **写入** workspace 其他位置 | ❌ 禁止 | 路径验证拒绝 |
| **读取** workspace 外文件 | ❌ 禁止 | 路径沙箱化 |
| **执行** 只读 shell 命令 (ls/cat/grep/diff/wc) | ✅ 允许 | 命令白名单 |
| **执行** 写入型 shell 命令 (rm/mv/cp) | ❌ 禁止 | 命令白名单 |
| **网络访问** | ❌ 禁止 | 无网络工具 |

### 4.2 路径沙箱化

```python
def resolve_safe_path(path: str, workspace_root: Path, writable_prefix: str = None) -> Path:
    """安全路径解析：防止路径遍历攻击"""
    resolved = (workspace_root / path).resolve()

    # 检查是否在 workspace 内
    if not str(resolved).startswith(str(workspace_root.resolve())):
        raise SecurityError(f"Path escape attempt: {path}")

    # 如果是写操作，检查是否在可写前缀内
    if writable_prefix:
        writable_dir = (workspace_root / writable_prefix).resolve()
        if not str(resolved).startswith(str(writable_dir)):
            raise SecurityError(f"Write outside allowed directory: {path}")

    return resolved
```

### 4.3 命令白名单

```python
ALLOWED_READ_COMMANDS = {
    "ls", "cat", "head", "tail", "grep", "find",
    "wc", "diff", "sort", "uniq", "tree", "file"
}

def sandbox_exec(command: str, cwd: Path) -> str:
    """只允许白名单中的只读命令"""
    # 解析命令的第一个 token
    parts = shlex.split(command)
    executable = parts[0]

    if executable not in ALLOWED_READ_COMMANDS:
        return f"Error: command '{executable}' not allowed. Allowed: {ALLOWED_READ_COMMANDS}"

    # 禁止管道到写入命令
    if "|" in command:
        pipe_targets = [p.strip().split()[0] for p in command.split("|")[1:]]
        for target in pipe_targets:
            if target not in ALLOWED_READ_COMMANDS:
                return f"Error: pipe target '{target}' not allowed"

    result = subprocess.run(
        command, shell=True, capture_output=True,
        text=True, timeout=30, cwd=cwd
    )
    return result.stdout[:50000]  # 截断过长输出
```

## 5. 搜索策略

### 5.1 父候选选择

```python
class ParentSelector:
    """候选选择策略"""

    @staticmethod
    def best(log: SearchLog) -> str:
        """选择当前最优候选作为父代"""
        return log.best_iteration

    @staticmethod
    def tournament(log: SearchLog, k: int = 3) -> str:
        """锦标赛选择：随机选 k 个，取最优"""
        candidates = random.sample(log.all_iterations, min(k, len(log.all_iterations)))
        return max(candidates, key=lambda c: c.score)

    @staticmethod
    def all_available(log: SearchLog) -> None:
        """不指定父代——Proposer 阅读全部历史自行决定"""
        return None

    @staticmethod
    def roulette(log: SearchLog) -> str:
        """轮盘赌选择：按分数概率分布"""
        scores = [c.score for c in log.all_iterations]
        probs = softmax(scores, temperature=0.5)
        return random.choices(log.all_iterations, weights=probs, k=1)[0]
```

### 5.2 论文推荐策略

Meta-Harness 论文使用 **"all"** 策略——Proposer 可以访问所有历史候选，自行决定参考哪些。这与信息瓶颈假说一致：给 Proposer 全量信息，让它自己决定读什么。

但考虑到 API 成本和上下文窗口限制，推荐分阶段：

| 阶段 | 策略 | 理由 |
|------|------|------|
| MVP | `best` | 最简单，减少 Proposer 需要读取的历史量 |
| V1.0 | `all`（默认）+ `best`（低成本模式） | 还原论文设置；同时提供经济选项 |
| 扩展 | `tournament` / `roulette` | 增加搜索多样性 |

## 6. Prompt Caching 策略

论文的 `anthropic_caching.py` 利用 Anthropic API 的 prompt caching 降低成本。我们采用同样的策略：

### 6.1 缓存结构

```
Proposer 的每次 API 调用：
┌─────────────────────────────────────────────────┐
│ System Prompt (CLAW.md 内容)    ←── 缓存（不变）  │
│ + Workspace 概览                ←── 缓存（慢变）  │
│ + 当前任务上下文               ←── 不缓存（每轮变） │
└─────────────────────────────────────────────────┘

Agent 工具循环中的多轮对话：
┌─────────────────────────────────────────────────┐
│ 前 N-3 条消息                    ←── 缓存         │
│ 最近 3 条消息                    ←── ephemeral    │
│ 当前工具调用结果                  ←── 不缓存       │
└─────────────────────────────────────────────────┘
```

### 6.2 成本估算

| 场景 | 无 caching | 有 caching | 节省 |
|------|-----------|-----------|------|
| 单轮 Proposer (10 次工具调用) | ~500K input tokens | ~80K input + 420K cached | ~60% 成本 |
| 20 轮搜索 | ~10M input tokens | ~2M input + 8M cached | ~50% 成本 |

## 7. 项目代码结构

```
poly-harness/
├── pyproject.toml                    # 项目配置 + 依赖
├── README.md
├── LICENSE
│
├── src/
│   └── poly_harness/
│       ├── __init__.py
│       ├── __main__.py               # python -m poly_harness 入口
│       ├── cli.py                    # CLI 入口 (click)，16 个命令/子命令
│       ├── config.py                 # 配置解析 (Pydantic)
│       ├── doctor.py                 # ph doctor 后端检测
│       ├── orchestrator.py           # 搜索循环编排器（进度条 + 断点续搜 + 错误恢复）
│       ├── workspace.py              # Workspace 文件系统管理
│       ├── search_log.py             # 搜索日志读写
│       │
│       ├── proposer/
│       │   ├── __init__.py
│       │   ├── base.py               # Proposer 抽象基类
│       │   ├── api_proposer.py       # Anthropic API + 工具循环
│       │   ├── cli_proposer.py       # 统一 CLI Proposer
│       │   ├── local_proposer.py     # 本地 Proposer（基于规则的变换）
│       │   └── adapters/             # Agent 适配器（参考 Supermemory 模式）
│       │       ├── __init__.py       # 适配器注册表
│       │       ├── base.py           # CLIAdapter 抽象基类
│       │       ├── claude_code.py    # Claude Code 适配器
│       │       ├── claw_code.py      # Claw Code 适配器
│       │       ├── codex.py          # OpenAI Codex 适配器
│       │       └── opencode.py       # OpenCode 适配器
│       │
│       ├── evaluator/
│       │   ├── __init__.py
│       │   └── evaluator.py          # Python 评估器
│       │
│       └── utils/
│           └── __init__.py
│
├── templates/                        # Workspace 模板
│   ├── default/
│   │   ├── CLAW.md                   # 默认 Proposer 指令
│   │   └── config.yaml               # 默认配置
│   └── text-classification/          # 示例：文本分类 harness 优化
│       ├── CLAW.md
│       ├── config.yaml
│       ├── base_harness/
│       │   └── harness.py
│       ├── evaluate.py
│       └── tasks/
│
├── tests/
│   ├── test_smoke.py                # 冒烟测试（导入 + CLI 入口）
│   ├── test_cli_features.py         # CLI 命令功能测试（32 个）
│   ├── test_cli_adapters.py         # Agent 适配器单元测试
│   ├── test_orchestrator.py         # 编排器测试（含 resume、错误恢复）
│   ├── test_evaluator.py
│   ├── test_workspace.py
│   ├── test_config.py               # 配置解析测试
│   ├── test_search_log.py           # 搜索日志测试
│   ├── test_compare.py              # compare/diff 测试
│   ├── test_export.py               # export 测试
│   └── test_log.py                  # log 命令测试
│
└── docs/                             # 已有的研究文档（保留）
    ├── research/
    ├── comparisons/
    ├── notes/
    └── references/
```

## 8. CLI 命令参考

PolyHarness 提供 16 个命令/子命令，通过 `ph` 入口访问：

### 8.1 全局选项

| 选项 | 说明 |
|------|------|
| `-v` / `--verbose` | 显示详细输出 |
| `-q` / `--quiet` | 静默模式，仅输出结果 |
| `--help` | 显示帮助信息 |

### 8.2 命令一览

| 命令 | 说明 |
|------|------|
| `ph doctor` | 检测可用后端和环境配置 |
| `ph init` | 初始化 workspace（支持 `--agent`、`--example`、`--backend`） |
| `ph run` | 启动优化搜索循环 |
| `ph status` | 显示当前搜索状态（已用时间、改进率、Δ） |
| `ph log` | 查看迭代历史（支持 tree/flat 模式，显示 Δ 列） |
| `ph best` | 显示最优候选 |
| `ph compare A B` | 对比两个候选的分数差异 |
| `ph diff N` | `compare 0 N` 的快捷方式 |
| `ph leaderboard` | 排行榜（`--top N`、`--tasks` 任务粒度） |
| `ph trace N` | 查看候选的 stdout/stderr/metrics/exitcode |
| `ph report` | 生成 Markdown 报告（含配置表、迭代日志、ASCII sparkline） |
| `ph apply` | 将最优 harness 应用到 agent |
| `ph export` | 导出搜索结果 |
| `ph clean` | 清理 workspace（`--keep-best`、`-y`） |
| `ph config show` | 显示当前配置 |
| `ph config set KEY VAL` | 修改配置（dot-notation，Pydantic 校验） |

### 8.3 `ph run` 关键选项

| 选项 | 说明 |
|------|------|
| `--dry-run` | 仅评估 base harness，不启动搜索循环 |
| `--resume` | 从上次中断处继续搜索 |
| `--backend NAME` | 运行时覆盖 Proposer 后端 |
| `--strategy NAME` | 运行时覆盖父候选选择策略（best/tournament/all） |

## 9. 依赖

```toml
# pyproject.toml

[project]
name = "poly-harness"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    "anthropic>=0.40.0",       # Anthropic API SDK
    "click>=8.0",              # CLI 框架
    "pydantic>=2.0",           # 配置验证
    "pyyaml>=6.0",             # YAML 解析
    "rich>=13.0",              # 终端美化输出
]

[project.optional-dependencies]
docker = ["docker>=7.0"]       # Docker 评估器
claw = []                      # Claw Code CLI（用户自行安装）
dev = [
    "pytest>=8.0",
    "pytest-asyncio",
    "ruff",
]

[project.scripts]
ph = "poly_harness.cli:main"
```

## 10. 关键技术决策记录

### 10.1 为什么 MVP 用 API 直连而非 CLI 后端

| 因素 | API 直连 | Claude Code CLI | Claw Code CLI |
|------|---------|----------------|---------------|
| 依赖复杂度 | 仅需 `anthropic` SDK | 需 Claude Code 订阅 | 需安装 Claw Code + 其依赖 |
| 调试能力 | 完整控制每一步 | 黑箱 | 黑箱（可改源码） |
| 安全控制 | 自行实现沙箱 | Anthropic 管理 | 需绕过 Claw 权限系统 |
| 部署难度 | pip install 即可 | 需订阅 + CLI 安装 | 需要 Node.js/Rust 环境 |
| **结论** | **MVP 首选** | Phase 3 集成 | Phase 3 集成 |

三种后端共享同一个 `BaseProposer` 接口，通过 `config.yaml` 的 `proposer.backend` 字段一行切换：

```yaml
proposer:
  backend: "api"          # 或 "claude-code" 或 "claw-code"
```

### 10.2 为什么不用 LangChain/LangGraph/CrewAI

Meta-Harness 的核心是**文件系统接口**——Proposer 通过 cat/grep/ls 读取信息。这只需要 4 个工具 + 一个 API 循环，不需要复杂的编排框架。引入 LangChain 等框架会增加不必要的抽象层和调试复杂度。

### 10.3 为什么全量保留 trace 而非压缩

信息瓶颈假说（A2 文档验证）的核心结论：压缩 trace 为摘要导致 15+ pp 的性能下降。本实现忠实还原论文设置，保留全部 trace。用户可以在 `config.yaml` 中配置 `trace_retention: full | summary | scores_only` 进行消融实验。

### 10.4 Proposer 工具集的最小化设计

论文中 Claude Code 有 25+ 工具族，但 Proposer 只需要 4 个：

| 工具 | 用途 | 对应论文行为 |
|------|------|------------|
| `file_read` | 读取候选代码/分数/trace | Proposer 的主要操作 (82 文件/轮) |
| `file_write` | 写入新候选 | Proposer 的输出 |
| `bash` (只读) | ls/grep/diff/wc | 导航和搜索 workspace |
| `grep` | 模式搜索 | 快速定位相关 trace |

不需要 BashTool 的写入能力、MCP、Agent 编排等——这些是 Claude Code 作为通用工具的功能，Proposer 不需要。

## 10. 扩展点

### 10.1 消融实验模式

```yaml
# config.yaml 中的消融配置
ablation:
  mode: "full"             # full | scores_summary | scores_only
  # full: Proposer 看到全部（代码+分数+trace）= 论文默认
  # scores_summary: 只看分数+LLM摘要（论文 Table 3 条件 2）
  # scores_only: 只看分数（论文 Table 3 条件 1）
```

这直接复现论文 Table 3 的三个消融条件，让用户在自己的任务上验证信息瓶颈假说。

### 10.2 Proposer 模型切换

```yaml
proposer:
  model: "claude-haiku-4-20250414"    # 低成本模式
  # model: "claude-sonnet-4-20250514"  # 平衡模式
  # model: "claude-opus-4-20250514"    # 最强模式（论文设置）
```

### 10.3 自定义搜索策略插件

```python
class CustomParentSelector(ParentSelector):
    """用户可以注册自定义的父候选选择策略"""

    def select(self, log: SearchLog) -> str:
        # 用户自定义逻辑
        ...
```
