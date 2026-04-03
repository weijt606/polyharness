# Example: Code Generation

A harness that generates Python function bodies from natural-language descriptions.

## Task

Given a description like "Return the sum of all numbers in the list", generate the Python code that implements it. The generated code receives an `args` parameter and must `return` the correct result.

**20 test cases** covering: sum, max, min, reverse, sort, filter, flatten, palindrome, Fibonacci, etc.

## Base Harness

The naive `harness.py` pattern-matches a few keywords (`sum`, `max`, `reverse`, `sort`, `len`) and emits one-liner boilerplate. Falls back to `return args` for anything it doesn't recognize.

**Base score: ~0.40** (handles ~8 of 20 tasks correctly)

## Run

```bash
cd examples/code-generation
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5
ph log --workspace .ws
```
