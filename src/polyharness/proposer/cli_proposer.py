"""CLI Proposer — invokes a CLI coding agent via an adapter to generate candidates.

Supports Claude Code, Claw Code, Codex, OpenCode, and any future CLI agent
that can be wrapped with a CLIAdapter.
"""

from __future__ import annotations

import os
from pathlib import Path

from polyharness.proposer.adapters import CLIAdapter, get_adapter
from polyharness.proposer.base import BaseProposer, build_proposer_context
from polyharness.utils.proc import run_process_group


def _build_prompt(
    workspace_root: Path,
    candidate_dir: Path,
    iteration: int,
    parent: int | None,
) -> str:
    """Build the optimization prompt sent to the CLI agent."""
    context = build_proposer_context(workspace_root, candidate_dir, iteration, parent)
    return (
        "You are PolyHarness Proposer — an expert AI agent that optimizes "
        "harness code through iterative search.\n\n"
        "The current working directory is the optimization workspace root.\n\n"
        f"{context}"
    )


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
            # run_process_group kills the whole process group on timeout —
            # agent CLIs fork node/tool grandchildren that a plain
            # subprocess.run kill would orphan (still writing, still billing).
            proc = run_process_group(
                cmd,
                timeout=self.timeout,
                cwd=str(workspace_root),
                env=env,
            )
        except FileNotFoundError as exc:
            binary = self.cli_path or self._adapter.default_binary
            raise RuntimeError(
                f"CLI agent '{binary}' not found. "
                f"Install it or set proposer.cli_path in config.yaml."
            ) from exc
        except PermissionError as exc:
            binary = self.cli_path or self._adapter.default_binary
            raise RuntimeError(
                f"CLI agent '{binary}' is not executable (permission denied). "
                f"Check the file mode or set proposer.cli_path in config.yaml."
            ) from exc

        if proc.timed_out:
            raise RuntimeError(
                f"CLI agent timed out after {self.timeout}s (process group killed). "
                "Increase proposer.timeout or simplify the task.\n"
                f"partial stdout: {proc.stdout[-500:]}"
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
