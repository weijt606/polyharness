# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.1] - 2026-04-09

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
