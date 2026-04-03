# PolyHarness

**Make your AI Agent evolve automatically.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-80%20passing-brightgreen.svg)]()
[![中文文档](https://img.shields.io/badge/文档-中文版-red.svg)](README_CN.md)

---

Your AI agent runs the same harness every time. Same prompts, same tool config, same strategy — no matter how many times it fails.

**PolyHarness fixes that.** It watches your agent work, learns from every iteration, and automatically discovers better configurations. You run one command — your agent gets smarter.

| | |
|---|---|
| **Self-Evolution** | Your agent automatically improves its own harness through iterative search. No manual tuning. |
| **6 Agent Backends** | Claude Code · Claw Code · Codex · OpenCode · API direct · Local — plug in any CLI agent. |
| **Full History** | Every iteration's code, scores, and traces preserved. Non-Markovian search beats blind retries. |
| **Search Tree** | Visualize the optimization path. Compare any two candidates with per-task diffs. |
| **One-Command Setup** | `ph init --base-harness ... --task-dir ...` — copies files, configures workspace, done. |
| **Closed Loop** | init → run → inspect → apply. Best harness writes back to your project automatically. |

---

## Backstory

Stanford's [Meta-Harness paper](https://arxiv.org/abs/2603.28052) (IRIS Lab, 2026) proved a surprising result: **harness design is the #1 lever for agent performance** — more impactful than model choice, prompt engineering, or fine-tuning.

The key insight? When you give an AI agent access to *full diagnostic history* — not just the latest score, but every past attempt's code, traces, and failure modes — it can *systematically evolve* its own harness configuration. The paper called this "non-Markovian search" and showed it outperforms simple best-of-N sampling by a wide margin.

But the paper only released the final optimized artifact (`agent.py`). **The search framework itself was never open-sourced.**

PolyHarness fills that gap. It's the open-source engine that makes Meta-Harness search available to everyone — for any agent, any task, any evaluation pipeline.

> **Think of it this way:**
> - Memory tools (like Supermemory) give agents persistent **memory** across conversations.
> - **PolyHarness gives agents persistent self-evolution** — they get better at their job over time.

---

## Use PolyHarness

<table>
<tr>
<td width="50%" valign="top">

### I use AI coding agents

You have Claude Code, Codex, or another agent.
You want it to perform better on your specific tasks — without manually tweaking prompts.

```bash
pip install poly-harness
ph init --agent claude-code --task-dir ./my_tasks
ph run
ph apply
```

Your agent's harness is now optimized. Done.

**[→ Jump to Quick Start](#quick-start)**

</td>
<td width="50%" valign="top">

### I'm building agent frameworks

You're developing an AI agent or tool and want
to integrate automated optimization as a feature.

PolyHarness provides a pluggable adapter API —
implement 3 methods and your agent gets self-evolution.

```python
class MyAgentAdapter(CLIAdapter):
    def build_command(self, prompt, cwd):
        return ["my-agent", "--prompt", prompt]
    def parse_output(self, stdout, stderr, code):
        return CLIResult(...)
```

**[→ Jump to Architecture](#how-it-works)**

</td>
</tr>
</table>

---

## Quick Start

### 1. Install

```bash
pip install poly-harness        # Python >= 3.12
# or
npm install -g poly-harness     # Node.js wrapper, auto-installs Python package
```

### 2. Check your environment

```bash
ph doctor
```

This auto-detects which agent backends (Claude Code, Codex, etc.) are installed and shows their status.

### 3. Initialize a workspace

```bash
ph init --agent claude-code \
        --base-harness ./my_harness/ \
        --task-dir ./my_tasks/ \
        --eval-script ./evaluate.py
```

This copies your harness code, test cases, and evaluation script into a structured workspace — and auto-configures everything. No manual YAML editing.

### 4. Run the optimization loop

```bash
ph run
```

The orchestrator: copies your harness → asks the Proposer agent to improve it → evaluates the result → stores everything → repeats.

### 5. Inspect and apply

```bash
ph log                         # search tree visualization
ph status                      # progress table
ph best                        # best candidate details
ph compare 0 5                 # diff two iterations (scores + code)

ph apply                       # write best harness back to base_harness/
ph export ./my-optimized       # or export to any directory
```

### Try it now (no API key needed)

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

Score jumps from 0.35 → 0.90 in 3 iterations. The `local` backend uses deterministic rules — real agent backends (Claude Code, Codex) can discover even more creative optimizations.

---

## How It Works

PolyHarness runs a **Meta-Harness search loop** — an iterative process where an AI agent optimizes its own configuration:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   You                          PolyHarness                   │
│    │                              │                          │
│    ├── ph init ──────────────────→│ Creates workspace        │
│    │   (harness + tasks + eval)   │ Copies files             │
│    │                              │ Injects CLAUDE.md        │
│    │                              │                          │
│    ├── ph run ───────────────────→│ Starts search loop:      │
│    │                              │                          │
│    │   ┌──────────────────────────┤                          │
│    │   │  Step 1: SELECT parent   │ Best or Tournament       │
│    │   │  Step 2: COPY harness    │ From parent → candidate  │
│    │   │  Step 3: PROPOSE changes │ Agent reads all history  │
│    │   │  Step 4: EVALUATE        │ Run tasks, get scores    │
│    │   │  Step 5: STORE results   │ Code + scores + traces   │
│    │   │  Step 6: CHECK stopping  │ Improved? Patience left? │
│    │   └──────────┬───────────────┤                          │
│    │              └── loop ───────┘                          │
│    │                              │                          │
│    ├── ph log ───────────────────→│ Shows search tree        │
│    ├── ph compare 0 5 ──────────→│ Score deltas + code diff │
│    └── ph apply ─────────────────→│ Writes best back         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### Why it works: non-Markovian search

Traditional approaches: run the agent → check the score → retry. Each attempt is independent.

**PolyHarness is different.** Every iteration stores:
- The complete candidate source code
- Per-task scores (not just the overall number)
- Full execution traces (stdout, stderr, exit codes)
- Metadata (parent candidate, proposer model, changes summary)

The Proposer reads **all of this** before generating the next candidate. It can see *why* a previous attempt failed, *which specific tasks* regressed, and *what code changes* caused it. This is why the Meta-Harness paper found that full-context search outperforms scores-only search by 15+ percentage points.

---

## Supported Agent Backends

| Backend | Command | Use case |
|---------|---------|----------|
| `api` | — | Default. Anthropic API direct, just needs `ANTHROPIC_API_KEY` |
| `claude-code` | `claude -p` | Official Claude Code CLI (Pro/Teams subscription) |
| `claw-code` | `claw -p` | Open-source Claw Code CLI |
| `codex` | `codex --quiet` | OpenAI Codex CLI |
| `opencode` | `opencode -p` | OpenCode CLI |
| `local` | — | Offline rule-based engine for development & testing |

`ph doctor` auto-detects all available backends and shows their status.

When you run `ph init --agent claude-code`, PolyHarness automatically generates a `CLAUDE.md` instruction file in the workspace, telling the agent how to behave as an optimization Proposer. Same for `CLAW.md`, `CODEX.md`, `OPENCODE.md` — each agent's native instruction format.

---

## Installation

### pip (recommended)

```bash
pip install poly-harness     # Requires Python >= 3.12
ph --version
```

### npm / npx

```bash
npm install -g poly-harness  # postinstall auto-installs Python package
npx poly-harness doctor      # or run without global install
```

The npm package is a thin Node.js wrapper (`bin/ph.mjs`) that finds and invokes the Python CLI. It checks: `ph` on PATH → `python -m poly_harness` → auto-discovers `.venv` in parent directories.

### From source

```bash
git clone https://github.com/weijt606/poly-harness.git
cd poly-harness

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
# or: pip install anthropic click pydantic pyyaml rich && export PYTHONPATH="$PWD/src"

python -m poly_harness --version
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `ph doctor` | Detect installed agents and environment status |
| `ph init` | Initialize workspace with auto-copy of harness, tasks, eval script |
| `ph run` | Start the optimization search loop |
| `ph status` | Show progress table (iteration / parent / score / best) |
| `ph log` | Search tree visualization (or `--flat` for table) |
| `ph best` | Show best candidate: score, per-task breakdown, changes summary |
| `ph compare A B` | Compare two iterations: score deltas + unified code diff |
| `ph apply` | Copy best harness back to `base_harness/` (or `--target` dir) |
| `ph export <dir>` | Export candidate to any directory (with optional `--include-meta`) |

### `ph init` options

```
--agent <name>       Backend: claude-code | claw-code | codex | opencode | api | local
--workspace <dir>    Workspace directory (default: current dir)
--base-harness <dir> Copy starting harness code into workspace
--task-dir <dir>     Copy tasks/ folder and evaluate.py into workspace
--eval-script <path> Copy a specific evaluate.py into workspace
```

---

## Examples

### Text Classification (sentiment analysis)

```bash
cd examples/text-classification
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 3

# iter_0: 0.65 → iter_1: 1.00 ★  (naive word list → expanded lexicon)
```

### Math Word Problems (numerical reasoning)

```bash
cd examples/math-word-problems
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.35 → iter_1: 0.50 → iter_2: 0.65 → iter_3: 0.90 ★
# (naive multiply → operation detection → averages/% → multi-step reasoning)
```

---

## Project Structure

```
src/poly_harness/
├── cli.py                   # Click CLI — 9 commands
├── config.py                # Pydantic config models
├── orchestrator.py          # Meta-Harness search loop + tournament selection
├── workspace.py             # Filesystem workspace + agent instruction injection
├── search_log.py            # JSONL append-only search log
├── doctor.py                # Environment detection for all backends
├── evaluator/
│   └── evaluator.py         # PythonEvaluator (subprocess)
├── proposer/
│   ├── api_proposer.py      # Anthropic API direct + tool-use loop
│   ├── cli_proposer.py      # CLIProposer — unified subprocess management
│   ├── local_proposer.py    # Offline rule-based (text + math)
│   └── adapters/            # Per-agent CLI adapters
│       ├── claude_code.py   # claude -p
│       ├── claw_code.py     # claw -p
│       ├── codex.py         # codex --quiet --auto-edit
│       └── opencode.py      # opencode -p

bin/
├── ph.mjs                   # npm wrapper
└── postinstall.mjs          # npm postinstall

examples/
├── text-classification/     # 20 test cases
└── math-word-problems/      # 20 test cases

tests/                       # 80 tests (pytest)
```

## Local Development

```bash
git clone https://github.com/weijt606/poly-harness.git && cd poly-harness
python -m venv .venv && source .venv/bin/activate
pip install anthropic click pydantic pyyaml rich pytest pytest-cov ruff
export PYTHONPATH="$PWD/src"

python -m pytest tests/      # run tests
ruff check src/ tests/       # lint
```

## Documentation

- [Product Development](docs/development/product-development.md) — roadmap, user scenarios, success metrics
- [Technical Architecture](docs/development/technical-architecture.md) — system design & data flow
- [Meta-Harness Paper](docs/research/references/meta-harness-paper.md) — theoretical foundation
- [Information Bottleneck Hypothesis](docs/research/information-bottleneck-hypothesis.md) — why full context matters
- [TBench2 Artifact Analysis](docs/research/tbench2-artifact-code-analysis.md)

---

<p align="center"><strong>Give your agent self-evolution. It's about time.</strong></p>

## License

MIT
