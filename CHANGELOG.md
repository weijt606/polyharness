# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.5] - 2026-06-04

### Added
- **Pi agent backend** (`pi`) — adapter for the minimal open-source
  [Pi coding agent](https://github.com/earendil-works/pi) (earendil-works).
  Invoked in print mode (`pi -p "<prompt>"`): a single-shot, non-interactive
  run that edits files in the workspace and exits. By design Pi has no
  permission popups or sandbox/approval flags, so none are passed. Pi
  auto-reads `AGENTS.md`, which PolyHarness already injects for this backend.
  Wired through the adapter registry, `ph init --agent pi`, the `--backend`
  override, ensemble selection, `ph doctor` detection, and the shell-hook
  auto-wrap (`pi -p ...`).

## [0.2.4] - 2026-05-26

### Added
- **Held-out test split** (`evaluator.eval_split`, `val_tasks`, `test_tasks`) —
  evolve the harness against `val_tasks` (selection, Pareto, and early-stop all
  use the validation set), then score only the best candidate **once** on the
  held-out `test_tasks` at the end. The test score never drives selection — it's
  an honest, post-hoc number that exposes harness overfitting to the eval set
  (borrowed from the Stanford Meta-Harness reference's val/test methodology).
  Per-task mode only; off by default. Result shown in the run summary and
  `ph best`, and persisted to `summary/holdout_test.json`.
- **Proposer improvement principles** — every Proposer prompt/instruction
  (API, CLI, and the injected `CLAUDE.md`/`AGENTS.md` etc.) now carries shared
  directives distilled from the official Stanford Meta-Harness reference Skill
  (MIT, re-authored not copied): change a real mechanism rather than tuning
  constants, stay general / don't overfit the eval set, ground changes in trace
  evidence, and state a falsifiable hypothesis. Pushes proposers toward
  higher-value, generalizable candidates (complements the post-hoc novelty filter).

### Changed
- Backstory in README / README_CN corrected: the Stanford Meta-Harness framework
  is now open-sourced (MIT); reframed PolyHarness's positioning accordingly and
  linked the official repo.
- Added an **Acknowledgments** section (README / README_CN) crediting the open
  works PolyHarness borrows ideas from and stating that **no third-party code is
  bundled**; CONTRIBUTING documents the attribution policy.
- Updated the `ph shell-hook install` help text to the current agent invocations
  (`codex exec`, `opencode run`) — a leftover from the v0.2.3 adapter refresh.

## [0.2.3] - 2026-05-26

### Fixed
- **Codex adapter** — switched to `codex exec` headless mode; the old
  `codex --quiet --auto-edit` invocation was removed upstream. Also adds
  `--skip-git-repo-check` (the optimization workspace isn't a git repo) and
  `--sandbox workspace-write` (lets the agent edit within the workspace).
- **OpenCode adapter** — switched to the `opencode run` subcommand; the
  top-level `-p` flag is no longer supported upstream.
- **Claude Code adapter** — add `--permission-mode acceptEdits` so the agent can
  actually write candidate files in headless `-p` mode (recent Claude Code blocks
  edits without it); drop `--verbose` (noise in print mode).

### Changed
- **Claude Code adapter** now pins `--model claude-opus-4-7` (Opus 4.7,
  highest-capability) for the Proposer.
- Default proposer model `claude-sonnet-4-20250514` → `claude-sonnet-4-6`
  (affects `api`/`openai` backends; other CLI backends use their own model).
- Verified `claude-code` (`claude -p`) and `hermes` (`hermes chat -q`) are still
  current; `claw-code` mirrors Claude Code (unverified, low usage).
- Docs (README / README_CN / technical-architecture) updated to the current CLI
  invocations.

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
- **Observability** — `ph log` marks Pareto-frontier members (◆); `ph leaderboard`
  adds a Pareto column and a Backend column (shown only when an ensemble was
  used). `SearchLog.pareto_win_counts()` powers both the CLI and the orchestrator.
- `proposer_backend` recorded in each candidate's `metadata.json` (ensemble mode)
- Hermes Agent adapter (`hermes`) — 8th proposer backend (`hermes chat -q`)
- `--strategy pareto` and `--ensemble` options for `ph run`
- `proposer/bandit.py` — UCB1 `BackendBandit`
- 31 new tests (206 total)

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
