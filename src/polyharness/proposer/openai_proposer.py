"""OpenAI Proposer — uses OpenAI-compatible API (e.g. Ollama, vLLM, LM Studio) to generate candidates."""

from __future__ import annotations

import json
from pathlib import Path

from polyharness.proposer.base import BaseProposer, build_proposer_context
from polyharness.proposer.toolkit import WorkspaceToolkit, openai_tool_definitions

TOOL_DEFINITIONS = openai_tool_definitions()


def _build_system_prompt(workspace_root: Path, candidate_dir: Path, iteration: int, parent: int | None) -> str:
    """Build the system prompt for the OpenAI compatible Proposer agent."""
    context = build_proposer_context(workspace_root, candidate_dir, iteration, parent)
    return (
        "You are PolyHarness Proposer — an expert AI agent that optimizes harness code.\n\n"
        "Use file_read / list_dir / file_search to explore the workspace history, "
        "and file_write to modify harness code files in your candidate directory. "
        "Describe changes made in your final response without calling tools.\n\n"
        f"{context}"
    )


class OpenAIProposer(BaseProposer):
    """Proposer that uses OpenAI-compatible API with tool loop."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        from polyharness.config import DEFAULT_OPENAI_MODEL

        self.model = model or DEFAULT_OPENAI_MODEL
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
