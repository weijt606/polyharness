"""CLI Proposer — invokes a CLI coding agent via an adapter to generate candidates.

Supports Claude Code, Claw Code, Codex, OpenCode, and any future CLI agent
that can be wrapped with a CLIAdapter.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from poly_harness.proposer.adapters import CLIAdapter, get_adapter
from poly_harness.proposer.base import BaseProposer


def _build_prompt(
    workspace_root: Path,
    candidate_dir: Path,
    iteration: int,
    parent: int | None,
) -> str:
    """Build the optimization prompt sent to the CLI agent."""
    parent_label = f"iter_{parent}" if parent is not None else "base_harness (first iteration)"
    cand_rel = candidate_dir.relative_to(workspace_root)

    # Gather leaderboard context if available
    leaderboard_section = ""
    lb_path = workspace_root / "summary" / "leaderboard.json"
    if lb_path.exists():
        lb_text = lb_path.read_text()
        if len(lb_text) > 5000:
            lb_text = lb_text[:5000] + "\n... (truncated)"
        leaderboard_section = f"""
## Current Leaderboard
```json
{lb_text}
```
"""

    return f"""\
You are PolyHarness Proposer — an expert AI agent that optimizes harness code
through iterative search.

## Workspace
The current working directory is the optimization workspace root.

Directory layout:
- base_harness/          — the starting harness code (search origin)
- candidates/iter_0/ ... — previous candidates, each containing:
  - harness code files (the code you can improve)
  - score.json — evaluation results (overall_score + per-task scores)
  - metadata.json — iteration metadata
  - traces/ — execution traces
- search_log.jsonl       — chronological log of all iterations and scores
- config.yaml            — search configuration
- summary/               — leaderboard and best candidate info
{leaderboard_section}
## Your Task
- Iteration: {iteration}
- Parent candidate: {parent_label}
- Your candidate directory: {cand_rel}/

## Instructions
1. Read the workspace to understand evaluation history. Start with search_log.jsonl
   and the parent candidate's score.json and traces/.
2. Identify concrete improvement opportunities from failure patterns.
3. Modify ONLY files inside your candidate directory ({cand_rel}/).
4. Focus on a single targeted improvement per iteration.
5. After making changes, briefly summarize what you changed and why.

## Rules
- Do NOT modify files outside {cand_rel}/.
- Do NOT delete or overwrite score.json or metadata.json (the evaluator writes those).
- Aim for improvements that are testable and measurable.
"""


class CLIProposer(BaseProposer):
    """Proposer that delegates to a CLI coding agent via an adapter.

    Works with any agent that has a CLIAdapter registered in the adapter registry.
    """

    def __init__(
        self,
        backend: str,
        cli_path: str | None = None,
        timeout: int = 600,
        adapter: CLIAdapter | None = None,
    ):
        self.backend = backend
        self.cli_path = cli_path
        self.timeout = timeout
        self._adapter = adapter or get_adapter(backend)

    def propose(
        self,
        workspace_root: Path,
        candidate_dir: Path,
        iteration: int,
        parent: int | None,
    ) -> dict:
        prompt = _build_prompt(workspace_root, candidate_dir, iteration, parent)
        cmd = self._adapter.build_command(prompt, cli_path=self.cli_path)

        env = {**os.environ, **self._adapter.env_vars()}

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=str(workspace_root),
                env=env,
            )
        except FileNotFoundError:
            binary = self.cli_path or self._adapter.default_binary
            raise RuntimeError(
                f"CLI agent '{binary}' not found. "
                f"Install it or set proposer.cli_path in config.yaml."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"CLI agent timed out after {self.timeout}s. "
                "Increase timeout or simplify the task."
            )

        result = self._adapter.parse_output(proc.stdout, proc.stderr, proc.returncode)

        if result.returncode != 0 and not result.changes_summary:
            raise RuntimeError(
                f"CLI agent '{self._adapter.name}' exited with code {result.returncode}.\n"
                f"stderr: {result.stderr[:1000]}"
            )

        return {
            "changes_summary": result.changes_summary or "(no output from agent)",
            "proposer_model": f"cli:{self._adapter.name}",
            "cli_returncode": result.returncode,
            **result.extra,
        }
