# Math Word Problems Example / 数学应用题示例

A harness-optimization example where an AI agent searches for better variants of a naive math word-problem solver.

一个 harness 优化示例，AI Agent 会围绕一个简单的数学应用题求解器搜索更高分的候选版本。

## Structure / 结构

```
math-word-problems/
├── base_harness/
│   └── harness.py          # Naive solver (starting point)
├── tasks/
│   └── test_cases.json      # 20 test cases
├── evaluate.py              # Scoring script
└── README.md
```

## How It Works / 工作原理

**Base harness** (`base_harness/harness.py`):
- Exports a `solve(question: str) -> float` function
- The naive version extracts numbers via regex and returns their product
- Currently scores 35% on the bundled test set (7/20 correct; mostly simple multiplication-style cases)

**Evaluator** (`evaluate.py`):
- Dynamically loads `harness.py` from a candidate directory
- Runs all 20 test cases, compares answers with floating-point tolerance
- Outputs JSON such as: `{"overall_score": 0.35, "task_scores": {...}, "correct": 7, "total": 20}`

**Test cases** (`tasks/test_cases.json`):
- 20 math word problems covering: arithmetic, percentages, averages, area, rates, negative numbers
- Each case has `question` (string) and `answer` (number)

## Quick Start / 快速开始

```bash
# Verify base harness score
python evaluate.py base_harness/

# Initialize a PolyHarness workspace
ph init --task-dir . --eval-script evaluate.py

# Run optimization (requires a configured proposer backend)
ph run --iterations 10
```

## What the Proposer Should Optimize / Proposer 优化方向

The naive solver only multiplies the first two numbers. A good optimization might:

1. **Parse operations** — detect keywords like "total", "left", "average", "per" to choose +, -, ×, ÷
2. **Multi-step reasoning** — handle problems requiring 2+ operations
3. **Edge cases** — negative numbers, percentages, ceiling division

PolyHarness can search over these directions automatically; whether a candidate is actually better depends on the evaluator score.

---

初始求解器只做两个数字的乘法。优化方向包括：

1. **识别运算** — 通过关键词（"总共"、"剩余"、"平均"、"每"）选择加减乘除
2. **多步推理** — 处理需要 2 步以上运算的问题
3. **边界情况** — 负数、百分比、向上取整

PolyHarness 可以围绕这些方向自动搜索候选修改；候选是否真的更好，仍以评估器分数为准。
