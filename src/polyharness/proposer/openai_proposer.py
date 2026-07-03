"""OpenAI Proposer — uses OpenAI-compatible API (e.g. Ollama, vLLM, LM Studio) to generate candidates."""

from __future__ import annotations

import json
from pathlib import Path

from polyharness.proposer.base import PROPOSER_PRINCIPLES, BaseProposer
from polyharness.proposer.toolkit import WorkspaceToolkit, openai_tool_definitions

TOOL_DEFINITIONS = openai_tool_definitions()


def _build_system_prompt(workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> str:
    """Build the system prompt for the OpenAI compatible Proposer agent."""
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
1. Use file_read / list_dir / file_search to explore the workspace history.
2. Read previous candidates' score.json and traces to understand what worked and what failed.
3. Use file_write to modify harness code files in your candidate directory.
4. Focus on one concrete, testable improvement.

## Rules
- ONLY write files inside your candidate directory ({candidate_dir.relative_to(workspace_root)}/).
- Describe changes made in your final response without calling tools.

{PROPOSER_PRINCIPLES}"""


class OpenAIProposer(BaseProposer):
    """Proposer that uses OpenAI-compatible API with tool loop."""

    def __init__(
        self,
        model: str = "gpt-4o",
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
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
        toolkit = WorkspaceToolkit(workspace_root, candidate_dir)
        system = _build_system_prompt(workspace_root, candidate_dir, iteration, parent)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": "Please analyze the workspace and produce an improved harness candidate."},
        ]

        changes_summary = ""
        tool_calls_count = 0
        max_tool_rounds = 50

        for _round in range(max_tool_rounds):
            kwargs = {
                "model": self.model,
                "messages": messages,
                "tools": TOOL_DEFINITIONS,
            }
            if self.temperature is not None:
                kwargs["temperature"] = self.temperature
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

                result = toolkit.execute(tool_call.function.name, args)

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
