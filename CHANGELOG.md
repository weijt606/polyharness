# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.2] - 2026-05-24

### Added
- **Pareto-frontier parent selection** (`parent_selection: pareto`) — samples
  parents from the set of per-task winners instead of always branching from the
  single overall-best candidate, keeping specialists alive as stepping stones to
  avoid premature convergence. Inspired by GEPA (arXiv:2507.19457). Reuses the
  per-task scores already stored in the search log — no new data collected.
- **Code novelty rejection** (`novelty_filter`, `novelty_threshold`,
  `novelty_max_retries`) — detects near-duplicate candidates via stdlib
  `difflib` text similarity (no new dependencies) and skips their evaluation to
  save API/compute budget. Inspired by ShinkaEvolve (arXiv:2509.19349). Off by
  default.
- **Adaptive backend ensemble** (`proposer.ensemble`, `proposer.bandit_c`,
  `ph run --ensemble b1,b2,...`) — when several backends are listed, a UCB1
  bandit picks one per iteration and shifts picks toward backends that produce
  *improving* candidates. Fully deterministic (no RNG) and adds no new
  dependencies. Run summary shows a per-backend picks/improve-rate table.
  Inspired by ShinkaEvolve's adaptive LLM-ensemble selection.
- **Cascade evaluation** (`evaluator.cascade`, `cascade_threshold`,
  `cascade_stage1`) — scores a cheap first subset of tasks and only runs the
  rest if it clears the gate, saving budget on weak candidates (AlphaEvolve/
  OpenEvolve-style). Per-task mode only; the base harness is always scored in
  full. Off by default.
- **Reproducible runs** (`search.seed`) — seeds the RNG so tournament/pareto/
  novelty regeneration are repeatable across runs.
- `proposer_backend` recorded in each candidate's `metadata.json` (ensemble mode)
- Hermes Agent adapter (`hermes`) — 8th proposer backend (`hermes chat -q`)
- `--strategy pareto` and `--ensemble` options for `ph run`
- `proposer/bandit.py` — UCB1 `BackendBandit`
- 24 new tests (199 total)

### Changed
- Agent backends: 7 → 8 (added Hermes Agent)

### Removed
- Stray byte-identical duplicate files (`collector 2.py`, `test_collector 2.py`,
  `test_evolution 2.py`) that inflated the test count and tripped ruff N999



### Added
- `ph shell-hook install/uninstall/status` — zero-config auto-wrap for agent commands via shell preexec hook
- Harness existence guard in orchestrator — clearer error when Proposer fails to generate `harness.py`
- 8 new tests (173 total)

### Changed
- README flow diagrams moved to their corresponding modules (Step 4 and Step 6) for better readability
- CLI commands: 22 → 25

## [0.2.0] - 2026-04-08

### Added
- **Online Evolution**: `ph wrap`, `ph traces`, `ph evolve` — collect traces from daily agent usage and auto-trigger evolution
- `ph wrap <cmd>` — transparent command wrapper that records execution traces (agent, exit code, duration, output)
- `--auto-evolve` flag for `ph wrap` — automatically triggers evolution when trace count reaches threshold
- `--no-record-output` flag for `ph wrap` — skip stdout/stderr capture for sensitive output
- `ph traces list` / `show` / `stats` / `clear` — manage collected traces
- `ph evolve` — manually trigger an evolution cycle using collected traces
- `collector.py` — trace collector engine (`~/.polyharness/traces/`)
- `EvolutionConfig`, `EvolutionTriggerConfig`, `EvolutionNotifyConfig` in config models
- `openai_proposer.py` — OpenAI-compatible API backend (Ollama, vLLM, DeepSeek, etc.)
- 37 new tests (165 total)

### Changed
- Agent backends: 6 → 7 (added OpenAI-compatible)
- CLI commands: 16 → 22
- README rewritten with Auto-Evolution guide (Step 6), accurate project structure, corrected config defaults

### Fixed
- `ws.apply_best()` missing required `target` parameter

## [0.1.3] - 2026-04-08

### Added
- `ph new <dir>` scaffold command — generates starter `harness.py`, `test_cases.json`, and `evaluate.py`
- `--template` option for `ph init` — one-command workspace setup from 5 bundled templates
- `ph upgrade` command — check and upgrade PolyHarness via pip
- `ph uninstall` command — clean removal with confirmation prompt
- 7 new tests for `ph new` and `--template` features (128 total)

### Changed
- Consolidated `examples/` into `src/polyharness/templates/` — single source of truth, shipped with package
- Redesigned README "Initialize Workspace" section: Option A (bundled template) + Option B (`ph new` scaffold)
- Updated CLI Reference tables in both READMEs

### Removed
- `examples/` directory (replaced by bundled templates)

## [0.1.0] - 2026-04-04

### Added
- Core search loop: Orchestrator, Proposer, Evaluator, Workspace, SearchLog
- 6 agent backends: `api`, `local`, `claude-code`, `claw-code`, `codex`, `opencode`
- 16 CLI commands: `doctor`, `init`, `run`, `status`, `log`, `best`, `compare`, `diff`, `leaderboard`, `trace`, `report`, `apply`, `export`, `clean`, `config show`, `config set`
- Global `--verbose` / `--quiet` flags
- `ph run` options: `--dry-run`, `--resume`, `--backend`, `--strategy`
- Rich progress bar during search loop
- Error recovery: failed iterations skip gracefully
- 5 examples: text-classification, math-word-problems, code-generation, api-calling, rag-qa
- npm wrapper (`bin/ph.mjs`) for `npx polyharness` usage
- GitHub Actions CI (lint + test on Python 3.12/3.13)
- 121 tests passing
