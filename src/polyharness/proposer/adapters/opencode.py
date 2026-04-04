"""OpenCode CLI adapter.

Invokes the open-source `opencode` CLI agent.
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter


class OpenCodeAdapter(CLIAdapter):
    """Adapter for the OpenCode CLI (`opencode`)."""

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def default_binary(self) -> str:
        return "opencode"

    def build_command(self, prompt: str, *, cli_path: str | None = None) -> list[str]:
        binary = cli_path or self.default_binary
        return [
            binary,
            "-p",                # prompt mode
            prompt,
        ]
