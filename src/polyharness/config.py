"""Configuration models for PolyHarness."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field


class SearchConfig(BaseModel):
    """Search loop parameters."""

    max_iterations: int = Field(default=20, ge=1, description="Maximum search iterations.")
    early_stop_patience: int = Field(
        default=5, ge=1, description="Stop after N iterations without improvement."
    )
    parent_selection: Literal["best", "tournament", "all"] = Field(
        default="best", description="Parent candidate selection strategy."
    )


class ProposerConfig(BaseModel):
    """Proposer agent configuration."""

    backend: Literal["api", "openai", "claude-code", "claw-code", "codex", "opencode", "local"] = Field(
        default="api", description="Proposer backend type."
    )
    model: str = Field(
        default="claude-sonnet-4-20250514", description="Model for the Proposer agent."
    )
    base_url: str | None = Field(
        default=None, description="Optional base URL for the API (useful for local models)."
    )
    api_key: str | None = Field(
        default=None, description="Optional API key (if None, reads from environment variables)."
    )
    max_tokens: int = Field(default=16384, ge=1, description="Max output tokens per turn.")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature.")
    cli_path: str | None = Field(
        default=None, description="Path to CLI executable (auto-detect if None)."
    )


class EvaluatorConfig(BaseModel):
    """Evaluator configuration."""

    type: Literal["python", "docker", "custom"] = Field(
        default="python", description="Evaluator type."
    )
    entry: str = Field(default="evaluate.py", description="Evaluator script entrypoint.")
    timeout: int = Field(default=300, ge=1, description="Per-task timeout in seconds.")
    tasks: list[str] = Field(default_factory=list, description="Task file paths.")


class HarnessConfig(BaseModel):
    """Target harness configuration."""

    language: str = Field(default="python", description="Harness code language.")
    entry: str = Field(default="harness.py", description="Harness entrypoint file.")
    editable_files: list[str] = Field(
        default_factory=lambda: ["harness.py", "prompt_template.txt"],
        description="Files the Proposer is allowed to modify.",
    )


class EvolutionTriggerConfig(BaseModel):
    """Trigger strategy configuration for online evolution."""

    strategy: Literal["degradation", "accumulate", "cron", "manual"] = Field(
        default="manual", description="When to trigger an evolution cycle."
    )
    min_samples: int = Field(
        default=10, ge=1, description="Minimum traces before any trigger fires."
    )
    window_size: int = Field(
        default=20, ge=2, description="Sliding window size for degradation detection."
    )
    threshold: float = Field(
        default=-0.05, description="Score drop threshold to trigger (negative value)."
    )
    accumulate_count: int = Field(
        default=50, ge=1, description="Trigger after collecting this many traces."
    )
    cron: str | None = Field(
        default=None, description="Cron expression for scheduled triggers."
    )


class EvolutionNotifyConfig(BaseModel):
    """Notification configuration after evolution completes."""

    method: Literal["terminal", "webhook"] = Field(
        default="terminal", description="Notification method."
    )
    webhook_url: str | None = Field(
        default=None, description="Webhook URL for notifications."
    )


class EvolutionConfig(BaseModel):
    """Online evolution configuration (v0.2.0)."""

    mode: Literal["batch", "online"] = Field(
        default="batch", description="batch = v0.1.x manual ph run; online = auto-trigger."
    )
    trigger: EvolutionTriggerConfig = Field(default_factory=EvolutionTriggerConfig)
    auto_apply: bool = Field(
        default=False, description="Automatically apply best harness (dangerous; default off)."
    )
    max_iterations: int = Field(
        default=3, ge=1, description="Max search iterations per online evolution cycle."
    )
    record_output: bool = Field(
        default=True, description="Record stdout/stderr in traces."
    )
    notify: EvolutionNotifyConfig = Field(default_factory=EvolutionNotifyConfig)


class PolyHarnessConfig(BaseModel):
    """Top-level configuration for a PolyHarness workspace."""

    search: SearchConfig = Field(default_factory=SearchConfig)
    proposer: ProposerConfig = Field(default_factory=ProposerConfig)
    evaluator: EvaluatorConfig = Field(default_factory=EvaluatorConfig)
    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    evolution: EvolutionConfig = Field(default_factory=EvolutionConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> PolyHarnessConfig:
        """Load config from a YAML file."""
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Write config to a YAML file."""
        with open(path, "w") as f:
            yaml.dump(
                self.model_dump(mode="json"),
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
