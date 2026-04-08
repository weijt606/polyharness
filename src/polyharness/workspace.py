"""Workspace manager — manages the filesystem layout for optimization runs."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from polyharness.config import PolyHarnessConfig
from polyharness.search_log import SearchLog


class Workspace:
    """Manages a PolyHarness optimization workspace on the filesystem."""

    REQUIRED_DIRS = ["base_harness", "candidates", "summary"]
    CONFIG_FILE = "config.yaml"
    SEARCH_LOG = "search_log.jsonl"

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    @classmethod
    def init(
        cls,
        root: str | Path,
        agent_backend: str = "api",
        *,
        task_dir: str | Path | None = None,
        eval_script: str | Path | None = None,
        base_harness: str | Path | None = None,
    ) -> Workspace:
        """Initialize a new workspace with default structure.

        Parameters
        ----------
        root : workspace directory
        agent_backend : proposer backend name
        task_dir : directory containing tasks/ and optionally evaluate.py.
            When given, copies ``tasks/`` into the workspace and sets the
            evaluator entry path in config.
        eval_script : path to a custom evaluate.py script.
            Copied into the workspace root if outside it.
        base_harness : directory containing the starting harness code.
            Files are copied into ``base_harness/``.
        """
        ws = cls(root)
        ws.root.mkdir(parents=True, exist_ok=True)

        for d in cls.REQUIRED_DIRS:
            (ws.root / d).mkdir(exist_ok=True)

        # Create empty search log
        log_path = ws.root / cls.SEARCH_LOG
        if not log_path.exists():
            log_path.touch()

        # ----------------------------------------------------------
        # Copy base harness
        # ----------------------------------------------------------
        if base_harness is not None:
            src = Path(base_harness).resolve()
            if src.is_dir():
                for item in sorted(src.rglob("*")):
                    if item.name == "__pycache__" or "__pycache__" in item.parts:
                        continue
                    rel = item.relative_to(src)
                    dest = ws.base_harness_dir / rel
                    if item.is_dir():
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, dest)

        # ----------------------------------------------------------
        # Copy tasks
        # ----------------------------------------------------------
        eval_entry = "evaluate.py"  # default

        if task_dir is not None:
            td = Path(task_dir).resolve()
            tasks_src = td / "tasks"
            if tasks_src.is_dir():
                tasks_dst = ws.root / "tasks"
                if tasks_dst.exists():
                    shutil.rmtree(tasks_dst)
                shutil.copytree(tasks_src, tasks_dst)

            # If task_dir contains evaluate.py and no explicit eval_script
            td_eval = td / "evaluate.py"
            if eval_script is None and td_eval.is_file():
                eval_script = td_eval

        # ----------------------------------------------------------
        # Copy evaluate script
        # ----------------------------------------------------------
        if eval_script is not None:
            es = Path(eval_script).resolve()
            if es.is_file():
                dest = ws.root / "evaluate.py"
                if not dest.exists() or dest.resolve() != es:
                    shutil.copy2(es, dest)
                eval_entry = "evaluate.py"

        # ----------------------------------------------------------
        # Write default config
        # ----------------------------------------------------------
        config_path = ws.root / cls.CONFIG_FILE
        if not config_path.exists():
            config = PolyHarnessConfig()
            config.proposer.backend = agent_backend  # type: ignore[assignment]
            config.evaluator.entry = eval_entry
            config.to_yaml(config_path)

        # Inject agent-native instruction file for CLI backends
        ws._inject_agent_instructions(agent_backend)

        # Warn if no evaluate script was copied
        if not (ws.root / eval_entry).exists():
            import warnings

            warnings.warn(
                f"No evaluate script found in workspace ({eval_entry}). "
                "You will need to provide one before running 'ph run'. "
                "Use --eval-script or --task-dir (with evaluate.py inside) during init.",
                stacklevel=2,
            )

        return ws

    def load_config(self) -> PolyHarnessConfig:
        """Load workspace config."""
        return PolyHarnessConfig.from_yaml(self.root / self.CONFIG_FILE)

    def search_log(self) -> SearchLog:
        """Get the search log for this workspace."""
        return SearchLog(self.search_log_path)

    @property
    def candidates_dir(self) -> Path:
        return self.root / "candidates"

    @property
    def base_harness_dir(self) -> Path:
        return self.root / "base_harness"

    @property
    def summary_dir(self) -> Path:
        return self.root / "summary"

    @property
    def search_log_path(self) -> Path:
        return self.root / self.SEARCH_LOG

    def candidate_path(self, iteration: int) -> Path:
        return self.candidates_dir / f"iter_{iteration}"

    def is_initialized(self) -> bool:
        """Check if workspace has required structure."""
        return (
            (self.root / self.CONFIG_FILE).exists()
            and self.candidates_dir.is_dir()
            and self.base_harness_dir.is_dir()
        )

    def store_iteration(
        self,
        iteration: int,
        score: float,
        task_scores: dict[str, float],
        parent: int | None = None,
        metadata: dict | None = None,
    ) -> Path:
        """Store evaluation results for an iteration.

        Creates score.json and metadata.json in the candidate directory.
        Also updates summary/leaderboard.json and summary/best_candidate.txt.
        """
        cand_dir = self.candidate_path(iteration)
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "traces").mkdir(exist_ok=True)

        # score.json
        score_data = {
            "iteration": iteration,
            "parent": f"iter_{parent}" if parent is not None else None,
            "overall_score": score,
            "task_scores": task_scores,
        }
        (cand_dir / "score.json").write_text(
            json.dumps(score_data, indent=2, ensure_ascii=False) + "\n"
        )

        # metadata.json
        meta = {
            "iteration": iteration,
            "parent": f"iter_{parent}" if parent is not None else None,
            **(metadata or {}),
        }
        (cand_dir / "metadata.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n"
        )

        # Update leaderboard
        self._update_leaderboard()

        return cand_dir

    def prepare_candidate(self, iteration: int, parent: int | None = None) -> Path:
        """Create a candidate dir by copying from parent (or base_harness)."""
        cand_dir = self.candidate_path(iteration)
        if cand_dir.exists():
            shutil.rmtree(cand_dir)

        if parent is not None:
            src = self.candidate_path(parent)
        else:
            src = self.base_harness_dir

        shutil.copytree(src, cand_dir, dirs_exist_ok=True)
        # Ensure traces dir exists
        (cand_dir / "traces").mkdir(exist_ok=True)
        return cand_dir

    def _update_leaderboard(self) -> None:
        """Rebuild summary/leaderboard.json from score.json files."""
        entries = []
        for cand in sorted(self.candidates_dir.iterdir()):
            score_file = cand / "score.json"
            if score_file.exists():
                data = json.loads(score_file.read_text())
                entries.append(data)

        entries.sort(key=lambda e: e.get("overall_score", 0), reverse=True)

        self.summary_dir.mkdir(exist_ok=True)
        (self.summary_dir / "leaderboard.json").write_text(
            json.dumps(entries, indent=2, ensure_ascii=False) + "\n"
        )

        if entries:
            best = entries[0]
            (self.summary_dir / "best_candidate.txt").write_text(
                f"iter_{best['iteration']}\n"
            )

    # ------------------------------------------------------------------
    # Agent instruction injection
    # ------------------------------------------------------------------

    # Mapping: backend name → instruction filename written into workspace root
    AGENT_INSTRUCTION_FILES: dict[str, str] = {
        "claude-code": "CLAUDE.md",
        "claw-code": "CLAW.md",
        "codex": "CODEX.md",
        "opencode": "OPENCODE.md",
    }

    def _inject_agent_instructions(self, backend: str) -> None:
        """Write an agent-native instruction file into the workspace.

        Claude Code reads CLAUDE.md, Claw Code reads CLAW.md, etc. These files
        tell the agent how to behave as a PolyHarness Proposer.
        """
        filename = self.AGENT_INSTRUCTION_FILES.get(backend)
        if filename is None:
            return  # api / local backends don't use instruction files

        target = self.root / filename
        if target.exists():
            return  # don't overwrite user customizations

        target.write_text(_agent_instruction_content(backend, filename))

    # ------------------------------------------------------------------
    # Apply best harness
    # ------------------------------------------------------------------

    def apply_best(self, target: Path) -> tuple[int, int]:
        """Copy best candidate's harness files to *target* directory.

        Returns (best_iteration, files_copied).
        """
        log = self.search_log()
        if not log.entries:
            raise RuntimeError("No candidates to apply. Run 'ph run' first.")

        best_i = log.best_iteration
        src = self.candidate_path(best_i)
        if not src.exists():
            raise RuntimeError(f"Best candidate directory not found: {src}")

        skip_names = {"score.json", "metadata.json", "traces", "__pycache__"}
        target.mkdir(parents=True, exist_ok=True)

        copied = 0
        for item in sorted(src.rglob("*")):
            rel = item.relative_to(src)
            if any(part in skip_names for part in rel.parts):
                continue
            dest = target / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, dest)
                copied += 1

        return best_i, copied


def _agent_instruction_content(backend: str, filename: str) -> str:
    """Generate the content for an agent instruction file."""
    return f"""\
# PolyHarness Proposer Instructions

> This file was auto-generated by `ph init --agent {backend}`.
> It tells {backend} how to act as a PolyHarness Proposer.
> You can customize it — PolyHarness will not overwrite your changes.

## Role

You are a **PolyHarness Proposer** — your job is to optimize harness code
through iterative search. Each time you are invoked, you will:

1. Read the optimization workspace to understand what has been tried.
2. Analyze previous candidates' scores and execution traces.
3. Make targeted improvements to the harness code.

## Workspace Layout

```
./                           ← you are here (workspace root)
├── {filename}               ← this file (your instructions)
├── config.yaml              ← search configuration
├── base_harness/            ← starting harness code
├── candidates/              ← all search candidates
│   ├── iter_0/              ← first candidate (= base_harness evaluated)
│   │   ├── harness.py
│   │   ├── score.json       ← evaluation results
│   │   └── traces/          ← execution traces
│   ├── iter_1/
│   └── ...
├── search_log.jsonl         ← chronological search log
└── summary/
    └── leaderboard.json     ← ranked candidates
```

## Rules

1. **Read before writing.** Start with `search_log.jsonl` and the parent
   candidate's `score.json` and `traces/` directory.
2. **Only modify files in your assigned candidate directory**
   (`candidates/iter_N/`). Do NOT touch other candidates or base_harness.
3. **One improvement per iteration.** Focus on a single, testable change.
4. **Evidence-based changes.** Ground improvements in patterns observed
   in traces (failures, edge cases, score regressions).
5. **Do NOT modify** `score.json` or `metadata.json` — those are written
   by the evaluator.

## Strategy Tips

- Check `summary/leaderboard.json` for the current ranking.
- Compare the best candidate's traces with worse ones to spot patterns.
- If a previous approach regressed, explain why and try a different angle.
- Small, targeted edits beat large rewrites.
"""
