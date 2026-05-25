"""Claude Code CLI adapter.

Invokes the official `claude` CLI in print mode (-p).
Requires an active Claude Code subscription.

Verified against Claude Code (May 2026):
- `-p` headless mode and `--output-format text` are current.
- `--permission-mode acceptEdits` is REQUIRED for the agent to write files
  non-interactively (auto-approves Read/Edit/Write); without it, headless edits
  are blocked. `acceptEdits` still gates arbitrary Bash/network (least-privilege,
  appropriate for the isolated workspace).
- `--model claude-opus-4-7` pins to Opus 4.7 (full name for reproducibility).
"""

from __future__ import annotations

from polyharness.proposer.adapters.base import CLIAdapter

# Pinned Proposer model for the Claude Code backend (highest-capability).
CLAUDE_CODE_MODEL = "claude-opus-4-7"


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
            "-p",                                # print mode (non-interactive)
            prompt,
            "--model", CLAUDE_CODE_MODEL,        # pin to Opus 4.7
            "--permission-mode", "acceptEdits",  # auto-approve file edits (headless)
            "--output-format", "text",
        ]
