# PolyHarness

```text
  _____      _        _    _                                   
 |  __ \    | |      | |  | |                                  
 | |__) |__ | |_   _ | |__| | __ _ _ __ _ __   ___  ___ ___    
 |  ___/ _ \| | | | ||  __  |/ _` | '__| '_ \ / _ \/ __/ __|   
 | |  | (_) | | |_| || |  | | (_| | |  | | | |  __/\__ \__ \   
 |_|   \___/|_|\__, ||_|  |_|\__,_|_|  |_| |_|\___||___/___/   
                __/ |                                          
               |___/                                           
```

**Make your AI Agent evolve automatically.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-121%20passing-brightgreen.svg)]()
[![中文文档](https://img.shields.io/badge/文档-中文版-red.svg)](README_CN.md)

---

Your AI agent runs the same harness every time. Same prompts, same tool config, same strategy — no matter how many times it fails.

**PolyHarness addresses that.** It records each iteration, evaluates candidate harness changes, and uses the accumulated history to search for better-scoring configurations. You run one command to start the loop.

| | |
|---|---|
| **Self-Evolution** | Iteratively searches over harness changes and keeps the full evaluation history in one workspace. |
| **6 Agent Backends** | Claude Code · Claw Code · Codex · OpenCode · API direct · Local — plug in any CLI agent. |
| **Full History** | Every iteration's code, scores, and traces preserved. The Meta-Harness paper reports that non-Markovian search outperforms blind retries. |
| **Search Tree** | Visualize the optimization path. Compare any two candidates with per-task diffs. |
| **One-Command Setup** | `ph init --base-harness ... --task-dir ...` — copies files, configures workspace, done. |
| **Closed Loop** | init → run → inspect → apply. You choose when to write the best-scoring candidate back to your project. |

---

## Backstory

Stanford's [Meta-Harness paper](https://arxiv.org/abs/2603.28052) (IRIS Lab, 2026) proved a surprising result: **harness design is the #1 lever for agent performance** — more impactful than model choice, prompt engineering, or fine-tuning.

The key insight? When you give an AI agent access to *full diagnostic history* — not just the latest score, but every past attempt's code, traces, and failure modes — it can *systematically evolve* its own harness configuration. The paper called this "non-Markovian search" and showed it outperforms simple best-of-N sampling by a wide margin.

But the paper only released the final optimized artifact (`agent.py`). **The search framework itself was never open-sourced.**

PolyHarness fills that gap. It's the open-source engine that makes Meta-Harness search available to everyone — for any agent, any task, any evaluation pipeline.

> **Think of it this way:**
> - Memory tools (like Supermemory) give agents persistent **memory** across conversations.
> - **PolyHarness gives agents persistent self-evolution** — you get a repeatable way to refine how they work over time.

## What PolyHarness Is

PolyHarness is the open-source engine for iteratively searching over an agent's harness.

It builds on ideas from the Meta-Harness paper and the TBench2 results reported there, while focusing this repository on the optimization workflow itself — how harness variants are proposed, evaluated, and revised over repeated runs.

If tools like ForgeCode help you code, PolyHarness helps you search for task-specific harness improvements by iterating on prompts, tool use, and harness logic.

---

## Use PolyHarness

<table>
<tr>
<td width="50%" valign="top">

### I use AI coding agents

You have Claude Code, Codex, or another agent.
You want to tune it for your specific tasks — without manually tweaking prompts.

```bash
pip install polyharness
ph init --agent claude-code --task-dir ./my_tasks
ph run
ph apply
```

You now have a repeatable optimization workspace. Inspect the results, then apply the best-scoring candidate if it improves your evaluation.

**[→ Jump to Quick Start](#quick-start)**

</td>
<td width="50%" valign="top">

### I'm building agent frameworks

You're developing an AI agent or tool and want
to integrate automated optimization as a feature.

PolyHarness provides a pluggable adapter API —
implement 3 methods and your agent can participate in the same search loop.

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
pip install polyharness         # Python >= 3.12
# or
npm install -g polyharness      # Node.js wrapper, auto-installs Python package
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

The orchestrator: copies your harness → asks the Proposer agent for a candidate change → evaluates the result → stores everything → repeats.

### 5. Inspect and apply

```bash
ph status                      # progress table + elapsed + improvement rate
ph log                         # search tree with delta (Δ) column
ph best                        # best candidate details
ph leaderboard                 # ranked table of all candidates (--tasks for drilldown)
ph compare 0 5                 # diff two iterations (scores + code)
ph diff 5                      # shorthand for: compare 0 5
ph trace 3                     # view stdout/stderr/metrics for iter_3
ph report                      # generate a full markdown report

ph apply                       # write best harness back to base_harness/
ph export ./my-optimized       # or export to any directory
ph clean --keep-best           # remove candidates to free disk space
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

The score path above is the current measured result of the bundled `math-word-problems` example with the repository's `local` backend, rounded for readability. It is not a paper benchmark or an external project result. The `local` backend is deterministic; no fixed score uplift is claimed here for Claude Code, Codex, or other real agent backends.

---

## How It Works

PolyHarness runs a **Meta-Harness-style search loop** — an iterative process where an AI agent proposes, evaluates, and stores harness changes:

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
│    ├── ph compare 0 5  ──────────→│ Score deltas + code diff │
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
pip install polyharness      # Requires Python >= 3.12
ph --version
```

### npm / npx

```bash
npm install -g polyharness   # postinstall auto-installs Python package
npx polyharness doctor       # or run without global install
```

The npm package is a thin Node.js wrapper (`bin/ph.mjs`) that finds and invokes the Python CLI. It checks: `ph` on PATH → `python -m poly_harness` → auto-discovers `.venv` in parent directories.

### From source

```bash
git clone https://github.com/weijt606/polyharness.git
cd polyharness

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
| `ph status` | Progress table with elapsed time, improvement rate, and delta |
| `ph log` | Search tree with delta (Δ) column (or `--flat` for table) |
| `ph best` | Show best candidate: score, per-task breakdown, changes summary |
| `ph compare A B` | Compare two iterations: score deltas + unified code diff |
| `ph diff <N>` | Shorthand for `compare 0 <N>` |
| `ph leaderboard` | Ranked table of all candidates (`--top N`, `--tasks` drilldown) |
| `ph trace <N>` | View stdout, stderr, metrics, exit code for an iteration |
| `ph report` | Generate a full markdown report with score trends and per-task table |
| `ph apply` | Copy best harness back to `base_harness/` (or `--target` dir) |
| `ph export <dir>` | Export candidate to any directory (with optional `--include-meta`) |
| `ph clean` | Remove candidate dirs to free disk space (`--keep-best`, `-y`) |
| `ph config show` | Display the current workspace configuration |
| `ph config set K V` | Modify a config value via dot-notation (with validation) |

### Global flags

```
-v, --verbose        Show detailed output
-q, --quiet          Suppress non-essential output
```

### `ph init` options

```
--agent <name>       Backend: claude-code | claw-code | codex | opencode | api | local
--workspace <dir>    Workspace directory (default: current dir)
--base-harness <dir> Copy starting harness code into workspace
--task-dir <dir>     Copy tasks/ folder and evaluate.py into workspace
--eval-script <path> Copy a specific evaluate.py into workspace
```

### `ph run` options

```
--max-iterations N   Override max iterations
--dry-run            Only evaluate the base harness, skip search
--resume             Continue an interrupted search from where it left off
--backend <name>     Override proposer backend without editing config
--strategy <name>    Override parent selection: best | tournament | all
```

---

## Examples

The score trajectories below are measured from the bundled examples using the current `local` backend and are rounded for readability. They are not borrowed from the Meta-Harness paper or from external benchmarks.

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

### Code Generation (function synthesis)

```bash
cd examples/code-generation
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.27 → iter_1: 0.50 → iter_2: 0.68 → iter_3: 0.95 ★
# (5 keywords → 10 patterns → composite logic → comprehensive coverage)
```

### API Calling (endpoint routing + parameter extraction)

```bash
cd examples/api-calling
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.19 → iter_1: 0.55 → iter_2: 0.77 → iter_3: 0.87 ★
# (keyword matching → broad routing → param helpers → full regex extraction)
```

### RAG Question Answering (retrieval + answer extraction)

```bash
cd examples/rag-qa
ph init --agent local --base-harness ./base_harness --task-dir . --workspace .ws
ph run --workspace .ws --max-iterations 5

# iter_0: 0.51 → iter_1: 0.79 ★
# (word overlap → stopword-filtered retrieval + sentence scoring)
```

---

## Project Structure

```
src/poly_harness/
├── cli.py                   # Click CLI — 16 commands/subcommands
├── config.py                # Pydantic config models
├── orchestrator.py          # Meta-Harness search loop + progress bar + error recovery
├── workspace.py             # Filesystem workspace + agent instruction injection
├── search_log.py            # JSONL append-only search log
├── doctor.py                # Environment detection for all backends
├── evaluator/
│   └── evaluator.py         # PythonEvaluator (subprocess)
├── proposer/
│   ├── api_proposer.py      # Anthropic API direct + tool-use loop
│   ├── cli_proposer.py      # CLIProposer — unified subprocess management
│   ├── local_proposer.py    # Offline rule-based (5 task types)
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
├── math-word-problems/      # 20 test cases
├── code-generation/         # 20 tasks × 3 inputs
├── api-calling/             # 20 test cases
└── rag-qa/                  # 20 QA pairs + 10-doc knowledge base

tests/                       # 121 tests (pytest)
```

## Local Development

```bash
git clone https://github.com/weijt606/polyharness.git && cd polyharness
python -m venv .venv && source .venv/bin/activate
pip install anthropic click pydantic pyyaml rich pytest pytest-cov ruff
export PYTHONPATH="$PWD/src"

python -m pytest tests/      # run tests
ruff check src/ tests/       # lint
```

## Documentation

- [Product Development](docs/development/product-development.md) — roadmap, user scenarios, success metrics
- [Technical Architecture](docs/development/technical-architecture.md) — system design & data flow
- [Meta-Harness Paper](docs/research/references/meta-harness-paper.md) — theoretical foundation and paper-reported reference results

---

<p align="center"><strong>Give your agent self-evolution. It's about time.</strong></p>

## License

MIT
