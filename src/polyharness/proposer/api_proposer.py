"""API Proposer — uses Anthropic API with a tool loop to generate candidates."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import anthropic

from polyharness.proposer.base import BaseProposer, build_proposer_context
from polyharness.proposer.toolkit import WorkspaceToolkit, anthropic_tool_definitions

TOOL_DEFINITIONS: list[dict[str, Any]] = anthropic_tool_definitions()


def _build_system_prompt(workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> str:
    """Build the system prompt for the Proposer agent."""
    context = build_proposer_context(workspace_root, candidate_dir, iteration, parent)
    return (
        "You are PolyHarness Proposer — an expert AI agent that optimizes harness code.\n\n"
        "Use file_read / list_dir / file_search to explore the workspace history, "
        "and file_write to modify harness code files in your candidate directory. "
        "When done, respond with a summary of your changes.\n\n"
        f"{context}"
    )


class APIProposer(BaseProposer):
    """Proposer that uses Anthropic API with tool loop."""

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 16384,
        temperature: float | None = None,
    ):
        from polyharness.config import DEFAULT_API_MODEL

        model = model or DEFAULT_API_MODEL
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
