# Math Word Problems Example / 数学应用题示例

A harness-optimization example where an AI agent improves a naive math word-problem solver.

一个 harness 优化示例，AI Agent 逐步改进一个简单的数学应用题求解器。

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
- Scores ~25% on the test set (only works for simple multiplication problems)

**Evaluator** (`evaluate.py`):
- Dynamically loads `harness.py` from a candidate directory
- Runs all 20 test cases, compares answers with floating-point tolerance
- Outputs JSON: `{"overall_score": 0.25, "task_scores": {...}, "correct": 5, "total": 20}`

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

PolyHarness will guide the AI agent to discover these improvements automatically.

---

初始求解器只做两个数字的乘法。优化方向包括：

1. **识别运算** — 通过关键词（"总共"、"剩余"、"平均"、"每"）选择加减乘除
2. **多步推理** — 处理需要 2 步以上运算的问题
3. **边界情况** — 负数、百分比、向上取整
