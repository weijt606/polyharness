"""Claw Code CLI adapter.

Invokes the open-source `claw` CLI in print mode (-p).
Claw Code is API-compatible with Claude Code.
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class ClawCodeAdapter(CLIAdapter):
    """Adapter for the Claw Code CLI (`claw`)."""

    @property
    def name(self) -> str:
        return "claw-code"

    @property
    def default_binary(self) -> str:
        return "claw"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "-p",                # print mode (non-interactive)
            prompt,
            "--output-format", "text",
            "--verbose",
        ]
