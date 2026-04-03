# Text Classification — Toy Example

This example demonstrates PolyHarness optimizing a simple text classification harness.

## Task
Classify short text snippets into categories: `positive`, `negative`, `neutral`.

## Setup

```bash
cd examples/text-classification
ph init --agent api
ph run --max-iterations 5
ph status
ph best
```

## Structure

- `base_harness/harness.py` — the initial (naive) classifier
- `evaluate.py` — scoring function that checks harness accuracy
- `tasks/` — test cases
