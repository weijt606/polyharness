---
title: "Meta-Harness: End-to-End Optimization of Model Harnesses"
date: 2026-04-02
status: final
---

# Meta-Harness Paper Reference

## Citation

```bibtex
@inproceedings{lee2026metaharness,
  title={Meta-Harness: End-to-End Optimization of Model Harnesses},
  author={Lee, Yoonho and Nair, Roshen and Zhang, Qizheng and Lee, Kangwook and Khattab, Omar and Finn, Chelsea},
  booktitle={Preprint},
  year={2026}
}
```

## Links

| Resource | URL |
|----------|-----|
| arXiv | https://arxiv.org/abs/2603.28052 |
| Project Page / Demo | https://yoonholee.com/meta-harness/ |
| Reference Code (TBench2) | https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact |
| Local PDF | `paper/Meta-Harness End-to-End Optimization of Model Harnesses.pdf` |

## Authors & Affiliation

Stanford IRIS Lab — Yoonho Lee, Roshen Nair, Qizheng Zhang, Kangwook Lee, Omar Khattab, Chelsea Finn

## Core Idea

A **model harness** is the scaffolding code that wraps an LLM: system prompts, tool definitions, completion-checking logic, context management, etc. Meta-Harness optimizes these harnesses end-to-end via an automated search loop.

### Search Loop

1. A coding agent (Claude Code) reads a filesystem containing **all prior candidates'** source code, execution traces, and scores
2. The agent performs counterfactual diagnosis — tracing failures back to specific harness decisions
3. It proposes a new harness with targeted fixes
4. The harness is evaluated on held-out tasks
5. Logs are stored in the filesystem; loop repeats

### Key Differentiator — Full Diagnostic Context

| Method | Context Type | ~Mtok/iter |
|--------|-------------|------------|
| Self-Refine | Last output + critique | 0.001 |
| OPRO | Window of (solution, score) pairs | 0.002 |
| TextGrad | LLM textual gradient | 0.015 |
| AlphaEvolve | Program database + scores | 0.022 |
| **Meta-Harness** | **Full filesystem: all logs + scores** | **10.0** |

## Results Summary

### Text Classification
- 48.6% vs ACE's 40.9% (+7.7 points), using 4× fewer context tokens
- GPT-OSS-120B on LawBench (215 classes), Symptom2Disease, USPTO-50k

### Math Reasoning (IMO-level)
- +4.7 points average across 5 held-out models (34.1% → 38.8%)
- Single retrieval harness transfers across unseen models

### Agentic Coding — TerminalBench-2 (89 tasks)

The figures below are reported by the Meta-Harness paper and are included here as research references. They are not benchmark results produced by this PolyHarness repository.

- **Claude Opus 4.6**: 76.4% pass rate (#2 overall)
- **Claude Haiku 4.5**: 37.6% pass rate (#1 among all Haiku agents)
- Built on top of Terminus-KIRA (KRAFTON AI)

## Reference Code Structure

The TBench2 artifact repo contains:
- `agent.py` — Main agent harness
- `anthropic_caching.py` — Caching utilities
- `prompt-templates/` — System prompt templates
- Built on Harbor framework + Terminus-KIRA base
