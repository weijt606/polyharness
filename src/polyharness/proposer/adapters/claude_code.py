"""Claude Code CLI adapter.

Invokes the official `claude` CLI in print mode (-p).
Requires an active Claude Code subscription.
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class ClaudeCodeAdapter(CLIAdapter):
    """Adapter for the Claude Code CLI (`claude`)."""

    @property
    def name(self) -> str:
        return "claude-code"

    @property
    def default_binary(self) -> str:
        return "claude"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "-p",                # print mode (non-interactive, stdout output)
            prompt,
            "--output-format", "text",
            "--verbose",
        ]
