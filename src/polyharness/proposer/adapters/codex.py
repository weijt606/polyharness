"""Codex CLI adapter.

Invokes OpenAI's `codex` CLI agent in quiet/non-interactive mode.
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class CodexAdapter(CLIAdapter):
    """Adapter for the OpenAI Codex CLI (`codex`)."""

    @property
    def name(self) -> str:
        return "codex"

    @property
    def default_binary(self) -> str:
        return "codex"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "--quiet",
            "--auto-edit",       # allow file edits without confirmation
            prompt,
        ]
