"""Codex CLI adapter.

Invokes OpenAI's `codex` CLI agent in headless/non-interactive mode via
`codex exec` (the old `--quiet`/`--auto-edit` flags were removed upstream).
See: developers.openai.com/codex/noninteractive
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
            "exec",                          # headless, non-interactive mode
            "--skip-git-repo-check",         # the workspace is not a git repo
            "--sandbox", "workspace-write",  # allow edits within the workspace cwd
            prompt,
        ]
