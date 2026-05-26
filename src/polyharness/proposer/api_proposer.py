"""API Proposer — uses Anthropic API with a tool loop to generate candidates."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import anthropic

from polyharness.proposer.base import PROPOSER_PRINCIPLES, BaseProposer

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "file_read",
        "description": "Read a file from the workspace. Returns its content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the workspace root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "file_write",
        "description": "Write content to a file in the current candidate directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within the candidate directory.",
                },
                "content": {
                    "type": "string",
                    "description": "Full content to write.",
                },
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_dir",
        "description": "List files and directories at the given workspace path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path from the workspace root.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "bash",
        "description": (
            "Run a read-only shell command (ls, cat, grep, diff, wc, find) "
            "in the workspace. Writes are not allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute.",
                },
            },
            "required": ["command"],
        },
    },
]

# Only allow these read-only commands in bash tool
ALLOWED_BASH_PREFIXES = ("ls", "cat", "grep", "diff", "wc", "find", "head", "tail", "echo")


def _build_system_prompt(workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> str:
    """Build the system prompt for the Proposer agent."""
    return f"""\
You are PolyHarness Proposer — an expert AI agent that optimizes harness code.

## Your Goal
Analyze the optimization workspace history and write an improved harness candidate.

## Workspace Layout
- workspace root: {workspace_root}
- candidates/iter_0/, iter_1/, ... — previous candidates, each with:
  - harness code files (the code you can improve)
  - score.json — evaluation results
  - traces/ — execution traces (stdout, stderr, metrics)
- base_harness/ — the starting harness code
- search_log.jsonl — summary of all iterations and scores
- config.yaml — search configuration

## Current Task
- Iteration: {iteration}
- Parent candidate: {"iter_" + str(parent) if parent is not None else "base_harness (first iteration)"}
- Your candidate directory: {candidate_dir.relative_to(workspace_root)}

## Instructions
1. Use file_read / list_dir / bash to explore the workspace history.
2. Read previous candidates' score.json and traces to understand what worked and what failed.
3. Identify specific improvement opportunities.
4. Use file_write to modify harness code files in your candidate directory.
5. Focus on concrete, testable improvements. Change ONE thing at a time when possible.
6. When done, respond with a summary of your changes.

## Rules
- Only write files inside your candidate directory ({candidate_dir.relative_to(workspace_root)}/).
- You can read any file in the workspace.
- Make targeted improvements based on evidence from traces.

{PROPOSER_PRINCIPLES}"""


class APIProposer(BaseProposer):
    """Proposer that uses Anthropic API with tool loop."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 16384,
        temperature: float = 0.7,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def propose(
        self,
        workspace_root: Path,
        candidate_dir: Path,
        iteration: int,
        parent: int | None,
    ) -> dict:
        client = anthropic.Anthropic()

        system = _build_system_prompt(workspace_root, candidate_dir, iteration, parent)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "Please analyze the workspace and produce an improved harness candidate."},
        ]

        changes_summary = ""
        tool_calls_count = 0
        max_tool_rounds = 50

        while tool_calls_count < max_tool_rounds:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=system,
                # The Anthropic SDK typing for tools/messages is stricter than
                # our dynamic tool loop payloads; runtime structure is valid.
                tools=TOOL_DEFINITIONS,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            )

            # Collect text blocks for final summary
            for block in response.content:
                if block.type == "text":
                    changes_summary = block.text

            if response.stop_reason != "tool_use":
                break

            # Process tool calls
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_calls_count += 1
                    result = self._execute_tool(
                        block.name, block.input, workspace_root, candidate_dir
                    )
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})

        return {
            "changes_summary": changes_summary,
            "proposer_model": self.model,
            "tool_calls": tool_calls_count,
        }

    def _execute_tool(
        self,
        name: str,
        tool_input: dict,
        workspace_root: Path,
        candidate_dir: Path,
    ) -> str:
        try:
            if name == "file_read":
                return self._tool_read(workspace_root, tool_input["path"])
            elif name == "file_write":
                return self._tool_write(candidate_dir, workspace_root, tool_input["path"], tool_input["content"])
            elif name == "list_dir":
                return self._tool_list(workspace_root, tool_input["path"])
            elif name == "bash":
                return self._tool_bash(workspace_root, tool_input["command"])
            else:
                return f"Error: unknown tool '{name}'"
        except Exception as e:
            return f"Error: {e}"

    def _tool_read(self, workspace_root: Path, rel_path: str) -> str:
        target = (workspace_root / rel_path).resolve()
        if not str(target).startswith(str(workspace_root)):
            return "Error: path outside workspace"
        if not target.exists():
            return f"Error: file not found: {rel_path}"
        if target.is_dir():
            return "Error: path is a directory, use list_dir instead"
        content = target.read_text(errors="replace")
        if len(content) > 100_000:
            return content[:100_000] + "\n... (truncated)"
        return content

    def _tool_write(self, candidate_dir: Path, workspace_root: Path, rel_path: str, content: str) -> str:
        target = (candidate_dir / rel_path).resolve()
        if not str(target).startswith(str(candidate_dir)):
            return "Error: can only write inside candidate directory"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Wrote {len(content)} bytes to {rel_path}"

    def _tool_list(self, workspace_root: Path, rel_path: str) -> str:
        target = (workspace_root / rel_path).resolve()
        if not str(target).startswith(str(workspace_root)):
            return "Error: path outside workspace"
        if not target.exists():
            return f"Error: path not found: {rel_path}"
        if not target.is_dir():
            return "Error: not a directory"
        entries = sorted(target.iterdir())
        lines = []
        for e in entries[:200]:
            suffix = "/" if e.is_dir() else ""
            lines.append(f"{e.name}{suffix}")
        return "\n".join(lines) if lines else "(empty directory)"

    def _tool_bash(self, workspace_root: Path, command: str) -> str:
        cmd_start = command.strip().split()[0] if command.strip() else ""
        if cmd_start not in ALLOWED_BASH_PREFIXES:
            allowed = ', '.join(ALLOWED_BASH_PREFIXES)
            return f"Error: command '{cmd_start}' not allowed. Only read-only commands: {allowed}"
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(workspace_root),
            )
            output = proc.stdout
            if proc.stderr:
                output += "\nSTDERR:\n" + proc.stderr
            if len(output) > 50_000:
                output = output[:50_000] + "\n... (truncated)"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return "Error: command timed out (30s limit)"

