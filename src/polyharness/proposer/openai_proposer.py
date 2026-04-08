"""OpenAI Proposer — uses OpenAI-compatible API (e.g. Ollama, vLLM, LM Studio) to generate candidates."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from polyharness.proposer.base import BaseProposer

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Read a file from the workspace. Returns its content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the workspace root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Write content to a file in the current candidate directory.",
            "parameters": {
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
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories at the given workspace path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from the workspace root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a read-only shell command (ls, cat, grep, diff, wc, find) "
                "in the workspace."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute.",
                    }
                },
                "required": ["command"],
            },
        },
    },
]

ALLOWED_BASH_PREFIXES = ("ls", "cat", "grep", "diff", "wc", "find", "head", "tail", "echo")

def _build_system_prompt(workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> str:
    """Build the system prompt for the OpenAI compatible Proposer agent."""
    return f"""\
You are PolyHarness Proposer — an expert AI agent that optimizes harness code.

## Your Goal
Analyze the optimization workspace history and write an improved harness candidate.

## Workspace Layout
- workspace root: {workspace_root}
- candidates/iter_0/, ... — previous candidates
- base_harness/ — the starting harness
- search_log.jsonl — summary of scores

## Current Task
- Iteration: {iteration}
- Parent candidate: {"iter_" + str(parent) if parent is not None else "base_harness (first iteration)"}
- Your candidate directory: {candidate_dir.relative_to(workspace_root)}

## Rules
- ONLY write files inside your candidate directory.
- Describe changes made in your final response without calling tools.
"""

class OpenAIProposer(BaseProposer):
    """Proposer that uses OpenAI-compatible API with tool loop."""

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key or "sk-dummy"
        self.max_tokens = max_tokens
        self.temperature = temperature

    def propose(
        self,
        workspace_root: Path,
        candidate_dir: Path,
        iteration: int,
        parent: int | None,
    ) -> dict:
        import openai

        client = openai.OpenAI(base_url=self.base_url, api_key=self.api_key)
        system = _build_system_prompt(workspace_root, candidate_dir, iteration, parent)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Please analyze the workspace and produce an improved harness candidate."},
        ]

        changes_summary = ""
        tool_calls_count = 0
        max_tool_rounds = 50

        while tool_calls_count < max_tool_rounds:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
                "tools": TOOL_DEFINITIONS,
            }
            if self.max_tokens:
                kwargs["max_tokens"] = self.max_tokens

            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            if message.content:
                changes_summary += "\n" + message.content

            if not message.tool_calls:
                break

            messages.append(message.model_dump(exclude_unset=True))

            for tool_call in message.tool_calls:
                tool_calls_count += 1
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                result = self._execute_tool(
                    tool_call.function.name, args, workspace_root, candidate_dir
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

        return {
            "changes_summary": changes_summary.strip(),
            "proposer_model": self.model,
            "tool_calls": tool_calls_count,
        }

    def _execute_tool(
        self, name: str, tool_input: dict, workspace_root: Path, candidate_dir: Path
    ) -> str:
        try:
            if name == "file_read":
                return self._tool_read(workspace_root, tool_input.get("path", ""))
            elif name == "file_write":
                path = tool_input.get("path", "")
                content = tool_input.get("content", "")
                return self._tool_write(candidate_dir, workspace_root, path, content)
            elif name == "list_dir":
                return self._tool_list(workspace_root, tool_input.get("path", ""))
            elif name == "bash":
                return self._tool_bash(workspace_root, tool_input.get("command", ""))
            else:
                return f"Error: unknown tool '{name}'"
        except Exception as e:
            return f"Error: {e}"

    def _tool_read(self, workspace_root: Path, rel_path: str) -> str:
        target = (workspace_root / rel_path).resolve()
        if not str(target).startswith(str(workspace_root)):
            return "Error: path outside workspace"
        if not target.exists():
            return f"Error: not found: {rel_path}"
        if target.is_dir():
            return "Error: path is a directory, use list_dir instead"
        content = target.read_text(errors="replace")
        return content[:100_000] + "\n... (truncated)" if len(content) > 100_000 else content

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
            return "Error: not found"
        if not target.is_dir():
            return "Error: not a directory"
        lines = [f"{e.name}{'/' if e.is_dir() else ''}" for e in sorted(target.iterdir())[:200]]
        return "\n".join(lines) if lines else "(empty directory)"

    def _tool_bash(self, workspace_root: Path, command: str) -> str:
        cmd_start = command.strip().split()[0] if command.strip() else ""
        if cmd_start not in ALLOWED_BASH_PREFIXES:
            return f"Error: allowed read-only commands: {', '.join(ALLOWED_BASH_PREFIXES)}"
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=30, cwd=str(workspace_root)
            )
            output = proc.stdout + ("\nSTDERR:\n" + proc.stderr if proc.stderr else "")
            return output[:50_000] + "\n... (truncated)" if len(output) > 50_000 else (output or "(no output)")
        except subprocess.TimeoutExpired:
            return "Error: command timed out"
