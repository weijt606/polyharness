---
title: "Meta-Harness TBench2 Artifact 代码分析"
date: 2026-04-02
status: final
sources:
  - https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact
---

# Meta-Harness TBench2 Artifact 代码分析

对论文官方参考实现仓库 [stanford-iris-lab/meta-harness-tbench2-artifact](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact) 的逐文件深度分析。

## 1. 仓库结构总览

```
meta-harness-tbench2-artifact/
├── agent.py                          # 核心：Agent 主体（~600行）
├── anthropic_caching.py              # 工具：Anthropic API 缓存优化
├── prompt-templates/
│   └── terminus-kira.txt             # 系统提示词模板
└── pyproject.toml                    # 项目配置与依赖
```

仓库极其精简——4 个文件，核心逻辑集中在 `agent.py`。

## 2. 逐文件分析

### 2.1 `agent.py` — Agent 主体

定义了 `AgentHarness` 类，**继承自 Terminus-KIRA（KRAFTON AI），Terminus-KIRA 又继承自 Harbor 的 Terminus2**。

#### 类继承与定位

```python
class AgentHarness(Terminus2):  # 实际继承自 Terminus-KIRA 的分支
```

Agent 名称为 `terminus-kira-env-bootstrap`，版本 `1.1.0`——明确标注这是在 Terminus-KIRA 基础上加了**环境引导（env bootstrap）**。

#### 核心组件

| 组件 | 功能 | 代码位置 |
|------|------|---------|
| **3 个工具定义** | `execute_commands`、`task_complete`、`image_read` | 顶部常量 `TOOLS` |
| **环境引导** | `_gather_env_snapshot()` | 在 agent 循环启动前收集沙箱信息 |
| **标记轮询** | `_execute_commands()` | 用 echo marker 检测命令完成 |
| **原生工具调用** | `_call_llm_with_tools()` | 直接用 Anthropic tools API，不做 JSON/XML 解析 |
| **Agent 主循环** | `_run_agent_loop()` | 逐步：调用 LLM → 解析工具调用 → 执行命令 → 取输出 → 循环 |
| **上下文溢出处理** | `_handle_llm_interaction()` 中的 except 分支 | 摘要回退机制 |
| **图片分析** | `_execute_image_read()` | 从容器读 base64 图片，发给 LLM 做视觉分析 |

#### `execute_commands` 工具 — 最关键的设计

```python
{
    "name": "execute_commands",
    "parameters": {
        "analysis": "分析当前状态：看到了什么？完成了什么？还要做什么？",
        "plan":     "描述下一步计划：要运行什么命令？为什么？",
        "commands": [{"keystrokes": "...", "duration": 1.0}]
    }
}
```

**强制结构化推理**：LLM 在执行任何命令前，必须先输出 `analysis`（分析）和 `plan`（计划）。这不是装饰——它迫使模型在行动前进行显式的状态评估和规划，类似 ReAct 模式但更结构化。

#### `_gather_env_snapshot()` — Meta-Harness 的关键发现

```python
bootstrap_cmd = (
    "echo '@@PWD@@' && pwd && "
    "echo '@@LS@@' && ls -la /app/ && "
    "echo '@@LANG@@' && (python3 --version ...) && (gcc --version ...) && ... "
    "echo '@@PKG@@' && (pip3 --version ...) && (apt-get --version ...) && "
    "echo '@@MEM@@' && free -h"
)
```

**一条复合命令**收集 5 类信息：

| 收集项 | 标记 | 内容 |
|--------|------|------|
| 工作目录 | `@@PWD@@` | `pwd` |
| 文件列表 | `@@LS@@` | `ls -la /app/`（超过 25 条截断显示前 20 条） |
| 可用语言 | `@@LANG@@` | python3, gcc, g++, node, java, rustc, go 版本检测 |
| 包管理器 | `@@PKG@@` | pip3, pip, apt-get 可用性 |
| 内存状态 | `@@MEM@@` | `free -h` |

解析为结构化文本后注入初始 prompt。**这是 Meta-Harness 搜索过程自动发现的优化**——原来 agent 要花 2-5 轮 `ls`、`which python3` 等探索命令，现在 0 轮。

#### 标记轮询机制（Marker-based Polling）

```python
marker = f"__CMDEND__{self._marker_seq}__"
await session.send_keys(command.keystrokes, block=False)
await session.send_keys(f"echo '{marker}'\n", block=False)
# 轮询直到 marker 出现或超时
while time.monotonic() - start < command.duration_sec:
    pane_content = await session.capture_pane()
    if marker in pane_content:
        break
    await asyncio.sleep(0.5)
```

每个命令后自动追加一个唯一 echo 标记。如果标记在超时前出现，**立即继续**而非傻等。最后输出中的 marker 行被过滤掉，LLM 看到的是干净输出。

#### 双重完成确认

```python
if is_task_complete:
    if self._pending_completion:
        # 第二次调用 → 真正完成
        return episode + 1
    else:
        # 第一次调用 → 展示 checklist
        self._pending_completion = True
        observation = self._get_completion_confirmation_message(terminal_output)
```

Checklist 包含三个视角审查：
1. 测试工程师视角
2. QA 工程师视角
3. 任务请求者视角

防止模型过早宣称完成。

#### 错误处理

| 错误类型 | 处理策略 |
|----------|---------|
| `ContextLengthExceededError` | 触发摘要机制，截断历史消息，用摘要 prompt 重试 |
| `OutputLengthExceededError` | 要求模型提供更短的响应，重试 |
| `BlockError` | 10 分钟超时保护，防止 API 卡死 |
| 一般异常 | 5 次指数退避重试（0.5s → 4s） |
| `BadRequestError` / `AuthenticationError` | 不重试，直接抛出 |

### 2.2 `anthropic_caching.py` — Prompt Caching 优化

```python
def add_anthropic_caching(messages, model_name):
    # 仅对 Anthropic/Claude 模型生效
    # 对最近 3 条消息添加 cache_control: {"type": "ephemeral"}
```

利用 Anthropic 的 [prompt caching](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching) 功能。将最近 3 条消息标记为 `ephemeral`，让 API 缓存前面不变的系统提示和历史对话，**只对新增部分计费**。对于 harness 这种长对话（几十轮），能显著降低 token 成本和延迟。

关键实现细节：
- 深拷贝消息列表，避免修改原始数据
- 支持 dict 和 Message 对象两种格式
- 自动将字符串 content 转为列表格式（Anthropic API 要求）

### 2.3 `prompt-templates/terminus-kira.txt` — 系统提示词

```
You are an AI assistant tasked with solving command-line tasks
in a Linux environment.
...
Your plan MUST account that you as an AI agent must complete
the entire task without any human intervention...
...
Before calling task_complete, verify minimal state changes:
Re-read the task instructions carefully and identify the
absolute minimum set of files that must be created or modified...
```

**三个关键指令**：
1. **完全自主**：不期待人类干预
2. **工具使用**：对多媒体文件必须使用程序化/AI 工具（因为 agent 没有"眼睛和耳朵"）
3. **最小状态变更**：完成前验证只改了必要的文件，不留任何副产物

模板变量：
- `{instruction}` — 运行时替换为任务描述
- `{terminal_state}` — 运行时替换为当前终端输出

### 2.4 `pyproject.toml` — 依赖

```toml
dependencies = [
    "anthropic",          # Anthropic SDK（直接 API 调用）
    "harbor>=0.1.44",     # Harbor 框架（Terminus2 基类、TmuxSession、评估基础设施）
    "litellm<1.82.7",     # LLM API 统一层（支持多模型切换）
    "tenacity",           # 重试库（指数退避重试）
]
```

## 3. 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│                    AgentHarness                          │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐                   │
│  │ System Prompt │    │ Env Bootstrap│ ← 自动发现的优化  │
│  │ (terminus-    │    │ pwd/ls/lang/ │                   │
│  │  kira.txt)   │    │ pkg/mem      │                   │
│  └──────┬───────┘    └──────┬───────┘                   │
│         │                   │                           │
│         ▼                   ▼                           │
│  ┌─────────────────────────────────┐                    │
│  │        Initial Prompt           │                    │
│  │  = system prompt + task         │                    │
│  │    + env snapshot               │                    │
│  └──────────────┬──────────────────┘                    │
│                 │                                       │
│                 ▼                                       │
│  ┌─────────────────────────────────┐                    │
│  │      Agent Loop (max N eps)     │◄──────────┐       │
│  │                                 │           │       │
│  │  1. _call_llm_with_tools()      │           │       │
│  │     ↓ (native tool calling)     │           │       │
│  │  2. _parse_tool_calls()         │           │       │
│  │     ↓                           │           │       │
│  │  3a. execute_commands →         │           │       │
│  │      _execute_commands()        │           │       │
│  │      (marker polling)           │──→ output ┘       │
│  │                                 │                    │
│  │  3b. image_read →               │                    │
│  │      _execute_image_read()      │                    │
│  │      (base64 → LLM vision)     │──→ output ┘       │
│  │                                 │                    │
│  │  3c. task_complete →            │                    │
│  │      double confirmation        │                    │
│  │      (checklist → final)        │──→ return          │
│  └─────────────────────────────────┘                    │
│                                                         │
│  ┌─────────────────────────────────┐                    │
│  │    Anthropic Caching Layer      │                    │
│  │  (最近3条消息 ephemeral cache)   │                    │
│  └─────────────────────────────────┘                    │
│                                                         │
│  ┌─────────────────────────────────┐                    │
│  │    Error Handling               │                    │
│  │  • ContextLengthExceeded → 摘要  │                    │
│  │  • OutputLengthExceeded → 重试   │                    │
│  │  • BlockError (10min timeout)   │                    │
│  │  • 5次指数退避重试              │                    │
│  └─────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

## 4. 核心发现

### 4.1 Meta-Harness 的"发现"极其精简

整个 artifact 只比 Terminus-KIRA 多了一个 `_gather_env_snapshot()` 方法（约 60 行代码）。这说明 harness 优化的关键不在于大改架构，而在于**找到高杠杆的小改动**。

### 4.2 搜索发现的是工程洞察，不是算法创新

环境引导是一个"显而易见但没人做"的优化。人类工程师可能想到也可能想不到，但自动化搜索通过分析执行轨迹（"agent 前几轮总在 ls 和 which"）精确定位了这个瓶颈。

### 4.3 代码质量很高

错误处理完善（5 次指数退避、上下文溢出回退、输出截断重试、10 分钟阻塞超时），说明 harness 工程不仅是 prompt，还包括大量的鲁棒性代码。

### 4.4 真正的工作在 Harbor 框架里

这个仓库是最顶层的薄壳。Terminus2 基类（agent 循环、摘要、轨迹记录）和 TmuxSession（终端交互）等核心能力都在 `harbor>=0.1.44` 中。

### 4.5 对研究的启示

- **高杠杆优化往往很小**：60 行代码带来 1.7% 的绝对提升（74.7% → 76.4%）
- **执行轨迹是诊断金矿**：Meta-Harness 搜索之所以能发现这个优化，是因为它能看到 agent 前几轮的重复探索模式
- **工程细节决定上限**：标记轮询、双重确认、缓存优化等"非核心"代码对最终性能有显著影响
