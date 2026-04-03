---
title: "信息瓶颈假说验证：全量上下文 vs 压缩摘要的效能分析"
date: 2026-04-02
status: draft
sources:
  - "Meta-Harness: arXiv:2603.28052 (Lee et al., 2026) — Table 1, Table 3, Table 4, Appendix A, Appendix E"
  - "MIPRO: arXiv:2406.11695 (Opsahl-Ong et al., EMNLP 2024)"
  - "GEPA: arXiv:2507.19457 (Agrawal et al., ICLR 2026 Oral)"
  - "OPRO: arXiv:2309.03409 (Yang et al., ICLR 2024)"
  - "TextGrad: arXiv:2406.07496 (Yuksekgonul et al., Nature 2025)"
  - "AlphaEvolve: arXiv:2506.13131 (Novikov et al., 2025)"
---

# 信息瓶颈假说验证：全量上下文 vs 压缩摘要的效能分析

## 1. 核心假说

Meta-Harness 论文的核心主张可以凝练为一个**信息瓶颈假说**：

> **在 LLM 系统优化中，优化器能访问的诊断上下文越完整（信息带宽越大），优化结果越好。信息压缩不可避免地丢失因果诊断线索，导致优化器只能从统计相关性猜测，而非从因果关系定位。**

论文原文表述：

> "These methods are poorly matched to harness engineering because they typically operate with short-horizon or heavily compressed feedback... Compressed feedback often removes the information needed to trace downstream failures to earlier harness decisions."

> "This is a pragmatic scalability choice, not evidence that longer-range dependencies are uninformative."

本文系统性整理各框架在信息保留谱上的定位，汇总支持和限制该假说的经验证据。

## 2. 信息保留谱：七种框架的定位

### 2.1 定量对比（基于 Meta-Harness Table 1）

Meta-Harness 论文直接提供了各方法的信息带宽估计。以下整合论文数据与各原始论文的技术细节：

| 框架 | 历史策略 | 优化器看到的内容 | 估计带宽 (Mtok/iter) | 带宽倍数 (vs OPRO) |
|------|----------|-----------------|---------------------|-------------------|
| **OPRO** | 滑动窗口 | 最近 (solution, score) 对 | ~0.002 | 1× |
| **DSPy/MIPRO** | 摘要 | 数据摘要 + 程序摘要 + 分数历史 | ~0.003-0.005 | 1.5-2.5× |
| **GEPA** | 摘要 | 执行轨迹的反思性摘要 | ~0.002-0.008 | 1-4× |
| **TextGrad** | 仅当前轮 | 当前制品的文本梯度反馈 | ~0.015 | 7.5× |
| **Feedback Desc.** | 摘要 | 对比式文本反馈 | ~0.012 | 6× |
| **AlphaEvolve** | 滑动窗口 | 程序数据库 + 评估分数 | ~0.022 | 11× |
| **TTT-Discover** | 滑动窗口 | 上一轮解决方案片段 | ~0.026 | 13× |
| **Meta-Harness** | **全量保留** | 所有候选源码 + 分数 + 执行 trace | **~10.0** | **5,000×** |

> 数据来源：Meta-Harness Table 1 (arXiv:2603.28052)。Mtok/iter 是论文对每次评估后产生的完整上下文的估计，按各方法在其**最大实验设置**中的情况计算。

### 2.2 信息保留策略的分类学

各框架的信息策略可以分为四类：

```
┌──────────────────────────────────────────────────────────────────┐
│                    信息保留策略谱                                  │
│                                                                  │
│  无记忆          滑动窗口          摘要压缩          全量保留       │
│  ────────       ──────────       ──────────       ──────────     │
│  Self-Refine    OPRO             MIPRO            Meta-Harness   │
│  TextGrad       AlphaEvolve      GEPA                            │
│                 TTT-Discover     Feedback Desc.                   │
│                                                                  │
│  ← 信息最少                               信息最多 →              │
│  ← 实现最简                               实现最复杂 →            │
│  ← 成本最低                               成本最高 →              │
└──────────────────────────────────────────────────────────────────┘
```

**无记忆（Memoryless）**：每次只看当前候选的反馈，不保留历史。
- Self-Refine: 只看自己上一轮输出 + 自我批评
- TextGrad: 只看当前制品的 "文本梯度"

**滑动窗口（Window）**：保留最近 N 轮的历史。
- OPRO: 保留最近若干 (solution, score) 对
- AlphaEvolve: 程序数据库 + 锦标赛选出的父代
- TTT-Discover: 上一轮解决方案的片段 + PUCT 选择规则

**摘要压缩（Summary）**：对历史信息进行 LLM 或统计压缩。
- MIPRO: 数据集摘要 + 程序控制流摘要 + TPE 贝叶斯模型
- GEPA: 执行轨迹 → LLM 反思 → 自然语言诊断
- Feedback Descent: 候选对比 → LLM 文本反馈

**全量保留（Full）**：保留所有历史，按需检索。
- Meta-Harness: 文件系统存储所有代码/分数/trace，Proposer 通过 grep/cat 选择性读取

### 2.3 每种策略丢失什么

| 策略 | 保留的信息 | 丢失的信息 |
|------|-----------|-----------|
| **无记忆** | 当前轮的完整反馈 | 所有历史候选、趋势、失败模式的积累 |
| **滑动窗口** | 最近几轮的 (解, 分数) | 早期候选的细节；跨候选的对比；执行轨迹 |
| **摘要** | 经 LLM 压缩的 "要点" | 具体的代码行号、精确的错误信息、罕见的边缘情况、因果推理所需的详细 trace |
| **全量** | 一切 | 无（但需要 Agent 自主决定读什么）|

## 3. 关键经验证据

### 3.1 Meta-Harness 的消融实验（最直接的证据）

Meta-Harness 论文 Table 3 提供了信息瓶颈假说**最直接的实验验证**：

**实验设置**：在线文本分类任务，3 种信息条件，其他条件（Proposer 模型、预算、种子）完全相同。

| 条件 | 接口 | 中位数准确率 | 最佳准确率 | 超过 Zero-shot 的 runs |
|------|------|-------------|-----------|----------------------|
| **Scores Only** | 代码 ✓, 分数 ✓, 摘要 ×, trace × | 34.6 | 41.3 | 26/39 |
| **Scores + Summary** | 代码 ✓, 分数 ✓, 摘要 ✓, trace × | 34.9 | 38.7 | 23/39 |
| **Meta-Harness (Full)** | 代码 ✓, 分数 ✓, 摘要 -, trace ✓ | **50.0** | **56.7** | **39/39** |

关键发现：

1. **全量 trace >> Scores Only**: 中位数从 34.6 → 50.0（+15.4pp），最佳从 41.3 → 56.7（+15.4pp）
2. **摘要无助甚至有害**: Scores + Summary 的最佳（38.7）**低于** Scores Only 的最佳（41.3），说明 LLM 生成的摘要可能压缩掉诊断关键细节，甚至引入噪声
3. **全量的中位数 > 压缩的最佳**: Meta-Harness 的中位数候选（50.0）优于两种消融条件的最佳候选（41.3 和 38.7），说明全量信息的优势不是运气，而是系统性的

论文解读：

> "We interpret this as evidence that full access to execution traces is the most important component of the interface: summaries do not recover the missing signal, and may even hurt by compressing away diagnostically useful details."

### 3.2 Meta-Harness vs 其他文本优化器（相同预算对比）

Meta-Harness Table 4 在相同 Proposer (Opus-4.6) 和相同评估预算下对比：

| 方法 | 信息策略 | 中位数准确率 | 最佳准确率 |
|------|---------|-------------|-----------|
| GEPA | 摘要（轨迹反思） | 32.6 | 40.2 |
| Best-of-N | 无搜索结构 | 34.0 | 44.2 |
| OpenEvolve | 窗口（程序数据库） | 39.1 | 43.3 |
| TTT-Discover | 窗口（PUCT 选择） | 34.1 | 45.6 |
| **Meta-Harness** | **全量（文件系统）** | **50.0** | **56.7** |

Meta-Harness 的中位数（50.0）超过所有其他方法的最佳值。差距最大的是与 GEPA 的对比：+17.4pp 中位数差距。

更关键的是收敛速度（Figure 1 & 4 的描述）：

> "Meta-Harness matches the best prior text optimizers (OpenEvolve, TTT-Discover) in 0.1× the evaluations, and its final accuracy surpasses theirs by more than 10 points."

即：Meta-Harness 用 **1/10 的评估次数**即达到其他方法的最终性能，然后继续提升超过 10 个点。

### 3.3 Proposer 的实际信息使用模式

Meta-Harness Appendix A (Table 8) 提供了 Proposer 实际如何使用文件系统的统计：

| 指标 | 数值 |
|------|------|
| 每轮读取文件数（中位数） | **82 文件** |
| 每轮读取文件数（范围） | 69-99 文件 |
| Harness 源代码 | 41% |
| 执行轨迹 | 40% |
| 分数/摘要文件 | 6% |
| 其他文件 | 13% |

关键观察：

1. **非马尔可夫使用模式**: Proposer "routinely inspects the majority of available history rather than conditioning only on the most recent parent"——不只看最近的父代，而是**检查大部分历史**
2. **源码和轨迹并重**: 41% 源码 + 40% 轨迹 = 81%，分数只占 6%。这直接证明了 Proposer 需要的不是分数，而是**代码和执行细节**
3. **分数的信息量极低**: 仅 6% 的读取用于分数文件——优化器发现标量分数几乎没有诊断价值

### 3.4 因果推理的定性证据

Appendix A.2 的 TerminalBench-2 搜索轨迹提供了最具说服力的定性证据。完整的 10 步叙事弧展示了 Proposer 如何利用全量上下文进行因果推理：

**Iteration 1-2**: 将结构修复和 prompt 修改捆绑在一起 → 两次都回退

**Iteration 3（关键因果推理步骤）**:
> "Root cause of regressions: Prompt template changes (cleanup directives) caused the agent to delete necessary state before task completion. The structural bugfixes were confounded with harmful prompt changes."

Proposer 通过对比两个失败候选，识别出**混淆变量**（prompt 修改），而非表面上的结构修复。这种推理需要：
- 读取两个候选的完整源代码
- 对比它们的差异
- 关联差异与性能变化

**Iteration 7（基于因果分析的策略转向）**:
> "All 6 prior iterations regressed from the 64.4% baseline because they modified the completion flow, prompt template, or observation processing. evo_env_bootstrap takes a different approach — purely additive."

经过 6 次失败后，Proposer 归纳出经验规律（修改控制流/prompt = 高风险），并主动选择**纯添加式修改**（环境引导）。这个获胜候选不是随机产生的，而是因果分析的直接结果。

**关键论点**: 这种 "识别混淆变量 → 隔离因果效应 → 策略转向" 的推理链，在任何信息压缩条件下都不可能实现：
- Scores Only: 只知道 "这个差"，不知道 "差在哪里"
- Scores + Summary: 摘要可能提到 "prompt 修改了" 但不会保留两个候选间的精确 diff
- 滑动窗口: 只看最近候选，无法跨 6 个候选积累因果证据

### 3.5 MIPRO 的间接证据：信息越丰富提议越好

MIPRO 论文的实验间接支持信息瓶颈假说。其 Grounding 策略对比：

| 条件 | 提议器输入 | 效果 |
|------|-----------|------|
| **无 Grounding（OPRO 式）** | 仅历史(指令, 分数)对 | 基线 |
| **+ 数据集摘要** | + 对训练数据模式的观察 | HotPotQA/HoVer 提升，ScoNe 下降 |
| **+ 程序摘要** | + pipeline 控制流描述 | 整体有帮助 |
| **+ Bootstrapped 示例** | + 成功执行的完整轨迹 | **最一致的提升** |
| **MIPRO++（学习最优组合）** | 自动选择最优信息组合 | 进一步提升 |

Lesson 4 总结："Grounding is helpful for instruction proposal overall, but the best proposal strategy varies by task."

**关键证据**: Bootstrapped 示例（即成功执行的**完整轨迹**）是最一致有效的信息源。这与 Meta-Harness 的发现一致——轨迹 > 摘要 > 分数。

但 MIPRO 也揭示了一个重要nuance：**更多信息不总是更好**。数据集摘要在 ScoNe 上反而有害。这暗示信息瓶颈假说可能需要一个修正条件：

> 更多信息有益的前提是优化器有能力**选择性使用**相关信息，而非被无关信息淹没。

### 3.6 GEPA 的证据：反思 > 标量奖励

GEPA 的核心实验对比了两种反馈模式：
- **RL/GRPO**: 标量奖励信号 → 策略梯度更新
- **GEPA 反思**: 执行轨迹 → 自然语言诊断 → 定向修改

结果：GEPA 平均 +6%（最高 +20%），且仅需 1/35 的 rollout。

这是信息瓶颈假说的另一个数据点：同样是从执行结果学习，用**自然语言**（高信息密度）传递反馈远胜于用**标量**（极低信息密度）。

但有趣的是，Meta-Harness Table 4 显示 GEPA 在 harness 优化设置下表现最差（32.6 中位数），甚至不如无搜索结构的 Best-of-N（34.0）。Meta-Harness Appendix E 的解释：

> "GEPA operates on one candidate at a time (2–8K tokens per step), with a fixed critique format that must anticipate what information is relevant. Meta-Harness gives the proposer access to all prior candidates simultaneously and lets the agent decide what to examine."

**GEPA 的反思架构假设诊断信息可以被预定义的反思模板捕获**。在短反馈回路任务（数学题、指令遵循）上这个假设成立，但在 harness 工程中不成立——harness 的失败模式太多样、太复杂，无法用固定格式的反思覆盖。

### 3.7 OPRO 的反面证据：极低带宽下的局限

OPRO 是这个谱上信息最少的方法之一（~2K tokens/step）。MIPRO 论文 §4.5 讨论了 Program-Level OPRO（给提议器看完整的多步轨迹历史）与 Module-Level OPRO（只看模块级指令+分数对）的对比：

> "In our experiments, we opt for using Module-level OPRO because Program-Level OPRO is more complex and did not appear to provide additional performance gains."

这看似与信息瓶颈假说矛盾——更多信息没带来更好结果？但 MIPRO 作者给出了关键caveat：

> "Information contained in histories is likely to be lost as history length grows (Liu et al., 2023)."

即：在 OPRO 框架内，更多信息被塞入**单一 prompt** 中，受限于 LLM 的长上下文能力。信息虽然存在，但 LLM 无法有效利用。这不是信息量的问题，而是**信息访问方式**的问题——恰恰是 Meta-Harness 通过文件系统+选择性检索解决的。

## 4. 信息瓶颈假说的边界条件

基于以上证据，信息瓶颈假说需要若干修正和边界条件：

### 4.1 假说成立的条件

| 条件 | 说明 | 证据 |
|------|------|------|
| **任务复杂度高** | 失败模式多样、因果链长、需要跨候选对比 | Table 3 消融实验：harness 优化中全量 >> 摘要 |
| **优化器有选择性检索能力** | 能 grep/cat 而非必须全部塞入 prompt | Appendix A：Proposer 每轮读 82 文件，自主选择 |
| **搜索空间是代码/程序** | 小的代码变化可能级联影响后续行为 | Appendix A.2：prompt 修改的混淆效应 |
| **存在长程依赖** | 一个设计决策影响多步之后的行为 | 环境引导消除 2-5 轮探索的发现 |

### 4.2 假说可能不成立的条件

| 条件 | 说明 | 证据 |
|------|------|------|
| **任务简单、反馈回路短** | 单步 prompt → response → score | GEPA 在数学/指令遵循上表现优异 |
| **优化器无法选择性读取** | 所有信息必须塞入单一 prompt | OPRO 中 Program-Level 不优于 Module-Level |
| **无关信息多于有用信息** | 噪声淹没信号 | MIPRO 中数据集摘要在 ScoNe 上有害 |
| **评估预算极低** | 历史太少，全量也没什么诊断可用 | 无直接数据，但逻辑推断 |

### 4.3 修正版假说

综合证据，原始假说可以修正为：

> **在 LLM 系统优化中，优化器的有效信息量（而非原始信息量）是性能的关键驱动因素。有效信息量 = f(可用诊断上下文, 选择性检索能力, 任务复杂度)。当任务足够复杂、且优化器具备选择性检索能力时，保留全量诊断上下文系统性优于压缩摘要。**

## 5. 量化分析：信息带宽 vs 优化效能

### 5.1 在线文本分类上的统一对比

这是唯一提供所有方法在同一任务、同一设置下直接对比的数据（Meta-Harness Table 4）：

```
信息带宽 (Mtok/iter)  →  优化效能 (中位数准确率)

  GEPA       (~0.008)  →  32.6
  Best-of-N  (   0  )  →  34.0
  TTT-Disc.  (~0.026)  →  34.1
  OpenEvolve (~0.022)  →  39.1
  Meta-Harness (~10.0) →  50.0
                            ↑
                        +10.9pp vs 第二名
                        +17.4pp vs GEPA
```

带宽与效能的关系不是线性的：
- GEPA (0.008) < TTT-Discover (0.026) < OpenEvolve (0.022)，但 OpenEvolve > TTT-Discover > GEPA，大致正相关但不严格
- Meta-Harness (10.0) 的带宽是 OpenEvolve 的 ~450×，性能提升是 +10.9pp

这暗示存在一个**相变点**：从窗口/摘要策略到全量策略时，性能出现质的飞跃，而不仅仅是量的线性增长。

### 5.2 收敛效率：信息量 vs 所需评估次数

Meta-Harness 的另一个关键主张是全量信息提高了**样本效率**：

> "Meta-Harness matches the best prior text optimizers (OpenEvolve, TTT-Discover) with 10× fewer full evaluations."

即：
- OpenEvolve/TTT-Discover 需要 ~40 次评估达到其最终性能
- Meta-Harness 仅需 ~4 次评估即达到相同水平

**解释**: 全量上下文使 Proposer 每次提议都是高度知情的，减少了盲目探索。这也意味着信息带宽的收益不仅体现在最终性能上，还体现在搜索效率上。

### 5.3 跨任务表现与信息需求的关系

| 任务域 | 典型反馈回路 | 最优方法的信息层级 | Meta-Harness 优势 |
|--------|------------|------------------|-------------------|
| **单步 prompt 优化** (数学、QA) | 短：1 prompt → 1 answer | 摘要（GEPA 已足够） | 有限 |
| **在线文本分类** (harness 设计) | 中：context → memory → prompt → answer | 全量（Meta-Harness） | 显著 (+10pp) |
| **Agentic coding** (TerminalBench-2) | 长：多步工具调用、代码编写、环境交互 | 全量（Meta-Harness） | 显著 (#1 Haiku) |
| **检索增强推理** (数学竞赛题) | 中：query → retrieve → prompt → solve | 全量（Meta-Harness） | 适中 (+4.7pp) |

**规律**: 反馈回路越长、因果链越复杂的任务，全量上下文的优势越大。

## 6. 成本-效能权衡

全量信息带来更好的优化效果，但代价不可忽略：

### 6.1 每次优化迭代的成本估计

| 方法 | 估计 tokens/iter | 模型 | 近似成本/iter |
|------|-----------------|------|-------------|
| OPRO | ~2K prompt | GPT-3.5/4 | ~$0.01-0.1 |
| MIPRO | ~5K proposal | GPT-3.5 proposer + task LM | ~$0.05-0.5 |
| GEPA | ~8K reflection | GPT-5 reflector | ~$0.1-1.0 |
| TextGrad | ~15K gradient | GPT-4 backprop | ~$0.1-0.5 |
| Meta-Harness | ~10M filesystem (Proposer 读 ~82 文件) | Claude Opus 4.6 Code | ~$5-50 |

Meta-Harness 每次迭代的成本约为 OPRO 的 100-500 倍。但由于它需要的**迭代次数少得多**（4 次 vs 40 次达到同等性能），总搜索成本可能相当：

```
总成本 ≈ 每次迭代成本 × 迭代次数

OPRO:          ~$0.05 × 50  = ~$2.5
MIPRO:         ~$0.25 × 50  = ~$12.5
GEPA:          ~$0.5  × 150 = ~$75
OpenEvolve:    ~$1.0  × 40  = ~$40
Meta-Harness:  ~$25   × 20  = ~$500
```

> 注：以上为粗略估计，实际成本高度依赖于任务、模型定价、评估成本等。

### 6.2 信息-成本 Pareto 前沿

```
性能          ┐
(优化效能)    │           ★ Meta-Harness
              │
              │                    ← "全量信息溢价"区间
              │     ○ OpenEvolve
              │   ○ TTT-Disc
              │  ○ GEPA
              │ ○ OPRO
              └────────────────────── →
              $1    $10   $100  $500
                    总搜索成本
```

**结论**: Meta-Harness 占据了 Pareto 前沿的高成本-高性能端。对于**高价值任务**（如竞争性 benchmark、生产级 agent 优化），这个成本完全合理。对于低成本场景，GEPA/MIPRO 仍然是更经济的选择。

## 7. 理论解释：为什么全量信息有效？

### 7.1 信息论视角

从信息论角度，优化过程可以建模为一个信道：

$$\text{Source}(\text{任务需求}) \xrightarrow{\text{评估}} \text{反馈信号} \xrightarrow{\text{诊断}} \text{优化决策}$$

每种信息策略对应不同的信道容量：
- **Scores Only**: $I(\text{feedback}; \text{failure cause}) \approx H(\text{score})$，非常低（一个标量只有几 bits）
- **Summary**: $I(\text{feedback}; \text{failure cause}) \leq H(\text{summary})$，受限于摘要的信息容量
- **Full traces**: $I(\text{feedback}; \text{failure cause}) \leq H(\text{all traces})$，上限高得多

数据处理不等式（Data Processing Inequality）保证：

$$I(\text{score}; \text{cause}) \leq I(\text{summary}; \text{cause}) \leq I(\text{full traces}; \text{cause})$$

因为 score 是从 summary 导出的，summary 是从 full traces 导出的。**信息只能丢失，不能凭空产生。**

### 7.2 因果推理视角

Meta-Harness 的核心优势不仅是信息量大，而是支持**因果推理**：

| 推理类型 | 所需信息 | Scores Only | Summary | Full |
|---------|---------|-------------|---------|------|
| 关联推理 | "X 和高分相关" | ✓ | ✓ | ✓ |
| 反事实推理 | "如果不改这行代码会怎样" | × | △ | ✓ |
| 混淆变量识别 | "性能下降是因为 A 还是 B" | × | × | ✓ |
| 因果归因 | "第 47 行的超时设置导致 test-3 失败" | × | × | ✓ |

完整的执行轨迹使 Proposer 能够进行：
1. **跨候选对比**（diff 两个版本的代码和结果）
2. **混淆变量隔离**（Appendix A.2 的核心推理）
3. **精确归因**（从错误日志追溯到代码行）

这些推理在压缩信息下**理论上不可能**，因为所需的精确细节已被压缩丢弃。

### 7.3 选择性注意力视角

Meta-Harness 的文件系统方案巧妙解决了一个两难困境：

- **全部塞入 prompt**: 10M tokens 远超任何模型的上下文窗口，且会触发 "lost in the middle" 问题
- **预先压缩**: 不知道哪些信息在未来诊断中是关键的

解决方案: **延迟绑定（late binding）**——存储一切，让 Agent 按需检索。这等价于将 "什么信息重要" 的决策从系统设计时推迟到诊断时。

```
传统方法: 设计时决定压缩规则 → 编译时绑定
Meta-Harness: 运行时 Agent 自主检索 → 运行时绑定
```

这解释了为什么 MIPRO 的数据集摘要有时有害（ScoNe 上）——设计时无法预知哪些信息对哪些任务有用。

## 8. 开放问题

### 8.1 信息边际递减存在吗？

Meta-Harness 证明 10M >> 8K，但以下问题未被回答：
- 是否存在一个从 "压缩摘要" 到 "全量保留" 之间的最优折中点？
- 如果历史积累到 100M tokens，Agent 还能有效利用吗？
- 更长的上下文窗口模型（如 1M+ tokens）能否减少对文件系统的需求？

### 8.2 信息质量 vs 信息数量

目前的证据主要来自**信息数量**（保留多少）。但信息质量（执行轨迹的结构化程度、日志格式、命名约定）可能同等重要。Meta-Harness Appendix D 建议 "Log everything in a format that is easy to navigate"——这是一个信息质量的优化。

### 8.3 通用性边界

所有直接对比数据来自 Meta-Harness 的三个任务域。以下场景的有效性未知：
- 创意生成（评估信号模糊）
- 实时在线优化（延迟敏感）
- 多 Agent 系统（搜索空间爆炸）
- 极低评估预算（<10 次评估）

## 9. 总结

### 9.1 信息瓶颈假说的证据等级

| 证据类型 | 描述 | 强度 |
|---------|------|------|
| **消融实验** (Table 3) | Full >> Scores+Summary >> Scores Only，同一任务、同一模型 | ★★★★★ 最强 |
| **跨方法对比** (Table 4) | Meta-Harness >> OpenEvolve >> TTT-Discover >> GEPA | ★★★★ 强 |
| **文件访问统计** (Table 8) | Proposer 主动选择读 41% 代码 + 40% trace，仅 6% 分数 | ★★★★ 强 |
| **定性因果推理** (Appendix A.2) | 混淆变量识别、策略转向的完整叙事 | ★★★ 中强 |
| **MIPRO Grounding 对比** | Bootstrapped traces 是最一致有效的信息源 | ★★★ 中强 |
| **GEPA vs RL** | 自然语言反思 >> 标量奖励 | ★★★ 中强（不同设置） |
| **收敛效率** (Figure 1, 4) | 10× 更少评估 + 10pp 更高最终性能 | ★★★ 中强 |

### 9.2 核心结论

1. **假说基本成立**: 在 harness 优化等复杂任务上，全量诊断上下文系统性优于压缩摘要。消融实验提供了最直接、最有力的证据。

2. **关键条件**: 需要选择性检索能力（文件系统 + 编程 Agent），否则更多信息可能反而有害（OPRO 的 Program-Level 失败、MIPRO 摘要在 ScoNe 上有害）。

3. **不是量的简单叠加**: 信息的有效性取决于 (可用信息, 检索能力, 任务复杂度) 三者的匹配。Meta-Harness 的成功不仅因为信息多，更因为 Coding Agent 的选择性检索能力与全量信息形成了有效匹配。

4. **存在相变而非线性**: 从 ~0.002-0.026 Mtok/iter 到 ~10 Mtok/iter 的跳跃带来了质的变化——从统计相关性推断到因果诊断推理。这不是 "多一点点更好"，而是 "足够多了才能做本质不同的事"。

---

## 参考文献

1. Lee, Y., Nair, K., Zhang, Z., Lee, K., Khattab, O., Finn, C. (2026). "Meta-Harness: End-to-End Optimization of Model Harnesses." arXiv:2603.28052
2. Opsahl-Ong, K., Ryan, M.J., et al. (2024). "Optimizing Instructions and Demonstrations for Multi-Stage Language Model Programs." EMNLP 2024. arXiv:2406.11695
3. Agrawal, L.A., Tan, S., et al. (2025). "GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning." ICLR 2026 Oral. arXiv:2507.19457
4. Yang, C., Wang, X., et al. (2023). "Large Language Models as Optimizers." ICLR 2024. arXiv:2309.03409
5. Yuksekgonul, M., et al. (2024). "TextGrad: Automatic 'Differentiation' via Text." Nature 2025. arXiv:2406.07496
6. Novikov, A., et al. (2025). "AlphaEvolve: A Coding Agent for Scientific and Algorithmic Discovery." arXiv:2506.13131
7. Lee, Y., Boen, J., Finn, C. (2025). "Feedback Descent: Open-Ended Text Optimization via Pairwise Comparison." arXiv:2511.07919
8. Yuksekgonul, M., Koceja, D., et al. (2026). "Learning to Discover at Test Time." arXiv:2601.16175
9. Sharma, A. (2025). "OpenEvolve: An Open-Source Evolutionary Coding Agent." GitHub.
