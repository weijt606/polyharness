"""API Proposer — uses Anthropic API with a tool loop to generate candidates."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any

import anthropic

from polyharness.config import DEFAULT_API_MAX_TOKENS, DEFAULT_API_MODEL, DEFAULT_EFFORT
from polyharness.proposer.base import BaseProposer, build_proposer_context
from polyharness.proposer.toolkit import WorkspaceToolkit, anthropic_tool_definitions

TOOL_DEFINITIONS: list[dict[str, Any]] = anthropic_tool_definitions()

# Models documented to accept server-side refusal fallbacks. Other models
# never get the parameter (it is a beta and an unknown model may 400 on it).
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset(
    {
        "claude-fable-5-2",
        "claude-fable-5-1",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    }
)

# Models known NOT to accept `output_config.effort` (it 400s there). A deny-list
# keeps effort working on future models by default; everything older than the
# 4.5 generation, plus Sonnet/Haiku 4.5, is listed.
_NO_EFFORT_MODELS = re.compile(
    r"^claude-(?:3|2|instant)"                     # Claude 3.x and earlier
    r"|^claude-(?:opus|sonnet)-4(?:-0|-1|-2025)"   # Claude 4.0 / 4.1 family
    r"|^claude-(?:sonnet|haiku)-4-5"               # Sonnet 4.5, Haiku 4.5
)

# Streaming avoids HTTP timeouts on long turns; retry only transient errors.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 529})
# Mid-stream failures arrive as an SSE `error` event on an HTTP-200 stream, so
# the status code can't classify them — the error type in the body does.
_RETRYABLE_ERROR_TYPES = frozenset({"overloaded_error", "api_error", "rate_limit_error"})
_MAX_TOOL_ROUNDS = 50


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, anthropic.APIConnectionError):
        return True
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS:
        return True
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict) and err.get("type") in _RETRYABLE_ERROR_TYPES:
            return True
    return False


def _supports_effort(model: str) -> bool:
    return not _NO_EFFORT_MODELS.match(model)


# Before a mid-output `fallback` boundary, only these block types may be
# echoed back; the declined model's thinking / tool_use (and any other
# model-internal block) must be omitted, and its tool calls never executed.
_PRE_FALLBACK_KEEP = frozenset({"text"})


def _echo_content(content: list[Any]) -> list[Any]:
    """Assistant content to replay (and act on) for the next tool-loop round.

    Without a fallback block this is the content unchanged. With one, the
    declined partial before the LAST `fallback` block is reduced to its text
    blocks; the `fallback` block stays exactly where it appeared and
    everything after it (the fallback model's own output) is kept as-is.
    """
    boundary = max((i for i, b in enumerate(content) if b.type == "fallback"), default=None)
    if boundary is None:
        return list(content)
    head = [b for b in content[:boundary] if b.type in _PRE_FALLBACK_KEEP or b.type == "fallback"]
    return head + list(content[boundary:])


def _last_text(content: list[Any]) -> str:
    """Latest summary text: the last text block AFTER any fallback boundary.

    Text before a `fallback` block came from the model that declined; it is
    echoed back as context but must not be recorded as what was done.
    """
    boundary = max((i for i, b in enumerate(content) if b.type == "fallback"), default=-1)
    texts = [b.text for b in content[boundary + 1:] if b.type == "text"]
    return texts[-1] if texts else ""


class ProposerRefusalError(RuntimeError):
    """The model (and any fallback) declined to produce a candidate."""


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
        max_tokens: int | None = None,
        temperature: float | None = None,
        effort: str | None = DEFAULT_EFFORT,
        refusal_fallback: bool = True,
    ):
        self.model = model or DEFAULT_API_MODEL
        self.max_tokens = max_tokens or DEFAULT_API_MAX_TOKENS
        self.effort = effort  # None = don't send
        if effort and not _supports_effort(self.model):
            # An effort param would 400 every iteration on these models.
            print(
                f"warning: model {self.model} does not support proposer.effort; "
                "not sending it.",
                file=sys.stderr,
            )
            self.effort = None
        self.refusal_fallback = refusal_fallback
        if temperature is not None:
            # Every current Claude model rejects sampling params with a 400;
            # sending it would fail every iteration, so drop it loudly once.
            print(
                "warning: proposer.temperature is ignored by the 'api' backend "
                "(the Anthropic API rejects sampling parameters); use "
                "proposer.effort to trade quality against cost.",
                file=sys.stderr,
            )

    @property
    def uses_fallbacks(self) -> bool:
        return self.refusal_fallback and self.model in FALLBACK_MODELS

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
        served_by: set[str] = set()

        for _round in range(_MAX_TOOL_ROUNDS):
            response = self._call_api(client, system, messages)
            stop_reason = response.stop_reason
            served_by.add(response.model)
            self._raise_on_refusal(response)
            self._raise_on_truncation(response)

            content = _echo_content(response.content)
            changes_summary = _last_text(response.content) or changes_summary

            if response.stop_reason != "tool_use":
                break

            # Process tool calls; all results go back in ONE user message.
            tool_results = []
            for block in content:
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

            # Append the assistant content unchanged (thinking blocks must be
            # replayed verbatim on current models — history is append-only),
            # except for a declined partial before a fallback boundary.
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": tool_results})
        else:
            # Tool budget exhausted mid-work — ask for a final summary so the
            # recorded changes_summary matches what was actually written.
            # Tools stay declared (the history holds tool_use/tool_result
            # blocks, and the cached prefix stays valid); tool_choice "none"
            # forbids further calls. The instruction rides in the same user
            # turn as the last tool results.
            messages[-1] = {
                "role": "user",
                "content": [
                    *messages[-1]["content"],
                    {
                        "type": "text",
                        "text": (
                            "Tool budget exhausted. Do not call any more tools. "
                            "Summarize the changes you have already written."
                        ),
                    },
                ],
            }
            response = self._call_api(client, system, messages, tool_choice_none=True)
            stop_reason = response.stop_reason
            served_by.add(response.model)
            self._raise_on_refusal(response)
            changes_summary = _last_text(response.content) or changes_summary

        meta: dict[str, Any] = {
            "changes_summary": changes_summary,
            "proposer_model": self.model,
            "tool_calls": tool_calls_count,
            "stop_reason": stop_reason,
        }
        if self.effort:
            meta["proposer_effort"] = self.effort
        # Record when a fallback model answered — reproducibility matters.
        if served_by - {self.model}:
            meta["served_by_models"] = sorted(served_by)
        return meta

    def _raise_on_truncation(self, response: Any) -> None:
        # A turn cut off by max_tokens may hold a half-written tool call or a
        # partial plan; treating it as finished would evaluate an unchanged or
        # half-edited candidate as if the model meant it.
        if response.stop_reason == "max_tokens":
            raise RuntimeError(
                f"proposer response was truncated at max_tokens={self.max_tokens}; "
                "raise proposer.max_tokens or lower proposer.effort"
            )

    @staticmethod
    def _raise_on_refusal(response: Any) -> None:
        if response.stop_reason != "refusal":
            return
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ProposerRefusalError(
            f"model declined the proposal request (refusal category: {category or 'unspecified'})"
        )

    def _build_request(
        self,
        system: str,
        messages: list[dict[str, Any]],
        *,
        tool_choice_none: bool = False,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            # The system prompt is identical across every round of the loop:
            # explicit breakpoint after it ...
            "system": [
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            # ... plus automatic caching of the growing tool-loop history, so
            # each round only pays full price for the newest turn.
            "cache_control": {"type": "ephemeral"},
            "messages": messages,
        }
        kwargs["tools"] = TOOL_DEFINITIONS
        if tool_choice_none:
            kwargs["tool_choice"] = {"type": "none"}
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}
        if self.uses_fallbacks:
            kwargs["betas"] = [FALLBACK_BETA]
            # extra_body, not a typed kwarg: works on every SDK in the
            # supported range whether or not it knows the parameter.
            kwargs["extra_body"] = {"fallbacks": "default"}
        return kwargs

    def _call_api(
        self,
        client: anthropic.Anthropic,
        system: str,
        messages: list[dict[str, Any]],
        *,
        tool_choice_none: bool = False,
    ):
        kwargs = self._build_request(system, messages, tool_choice_none=tool_choice_none)
        stream_fn = client.beta.messages.stream if "betas" in kwargs else client.messages.stream

        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                # SDK typing is stricter than our dynamic payloads; runtime
                # structure is valid.
                with stream_fn(**kwargs) as stream:  # type: ignore[arg-type]
                    return stream.get_final_message()
            except (anthropic.APIConnectionError, anthropic.APIStatusError) as exc:
                if not _is_retryable(exc) or attempt == 2:
                    raise
                last_exc = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"API call failed after retries: {last_exc}")
