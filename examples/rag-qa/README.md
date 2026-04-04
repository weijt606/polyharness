# Example: RAG Question Answering

A harness that retrieves relevant documents from a knowledge base and extracts answers.

## Task

Given a question and 10 knowledge-base documents, the harness must:
1. **Retrieve** the correct source document
2. **Extract** the answer from that document

**20 test cases** covering: Python history, solar system, photosynthesis, HTTP, machine learning, DNA, Git, water cycle, REST APIs, Roman Empire.

## Scoring

- Correct source document retrieved: 0.4 points
- Expected answer found in harness output: 0.6 points

## Base Harness

The naive `harness.py` uses simple word-overlap counting for retrieval and returns the first sentence of the matched document as the answer.

**Base score: ~0.51** (retrieval is often correct enough to earn partial credit, but answer extraction remains crude)

## Run

```bash
cd examples/rag-qa
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5
ph log --workspace .ws
```
