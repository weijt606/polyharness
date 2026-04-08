# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
