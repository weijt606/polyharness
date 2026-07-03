"""API Proposer — uses Anthropic API with a tool loop to generate candidates."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anthropic

from polyharness.proposer.base import PROPOSER_PRINCIPLES, BaseProposer
from polyharness.proposer.toolkit import WorkspaceToolkit, anthropic_tool_definitions

TOOL_DEFINITIONS: list[dict[str, Any]] = anthropic_tool_definitions()


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
1. Use file_read / list_dir / file_search to explore the workspace history.
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
        temperature: float | None = None,
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
        toolkit = WorkspaceToolkit(workspace_root, candidate_dir)

        system = _build_system_prompt(workspace_root, candidate_dir, iteration, parent)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": "Please analyze the workspace and produce an improved harness candidate."},
        ]

        changes_summary = ""
        stop_reason: str | None = None
        tool_calls_count = 0
        max_tool_rounds = 50

        for _round in range(max_tool_rounds):
            response = self._call_api(client, system, messages)
            stop_reason = response.stop_reason

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
                    result = toolkit.execute(block.name, block.input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Tool budget exhausted mid-work — ask for a final summary so the
            # recorded changes_summary matches what was actually written.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Tool budget exhausted. Do not call any more tools. "
                        "Summarize the changes you have already written."
                    ),
                }
            )
            response = self._call_api(client, system, messages, tools_enabled=False)
            stop_reason = response.stop_reason
            for block in response.content:
                if block.type == "text":
                    changes_summary = block.text

        return {
            "changes_summary": changes_summary,
            "proposer_model": self.model,
            "tool_calls": tool_calls_count,
            "stop_reason": stop_reason,
        }

    def _call_api(
        self,
        client: anthropic.Anthropic,
        system: str,
        messages: list[dict[str, Any]],
        *,
        tools_enabled: bool = True,
    ):
        # Prompt caching: the system prompt and tool definitions are identical
        # across every round of the loop, so mark a cache breakpoint after them.
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            "messages": messages,
        }
        if tools_enabled:
            kwargs["tools"] = TOOL_DEFINITIONS
        # Current-generation Claude models (Sonnet 5+, Opus 4.8+) reject
        # explicit sampling params; only pass temperature if the user set one.
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                # SDK typing is stricter than our dynamic payloads; runtime
                # structure is valid.
                return client.messages.create(**kwargs)  # type: ignore[arg-type]
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
                status = getattr(exc, "status_code", None)
                retryable = status is None or status in (429, 500, 502, 503, 529)
                if not retryable or attempt == 2:
                    raise
                last_exc = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"API call failed after retries: {last_exc}")
