"""Configuration models for PolyHarness."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# Single source of truth for proposer backend names. Used by both the fixed
# `backend` field and the optional `ensemble` list (which gets validation for
# free by reusing this Literal alias).
BackendName = Literal[
    "api", "openai", "claude-code", "claw-code", "codex", "hermes", "opencode", "pi", "local"
]


class SearchConfig(BaseModel):
    """Search loop parameters."""

    max_iterations: int = Field(default=20, ge=1, description="Maximum search iterations.")
    early_stop_patience: int = Field(
        default=5, ge=1, description="Stop after N iterations without improvement."
    )
    seed: int | None = Field(
        default=None,
        description=(
            "Optional RNG seed. When set, randomized strategies (tournament, "
            "pareto, novelty regeneration) become reproducible across runs."
        ),
    )
    parent_selection: Literal["best", "tournament", "all", "pareto"] = Field(
        default="best",
        description=(
            "Parent candidate selection strategy. "
            "'pareto' samples from the per-task winners (GEPA-style frontier) "
            "to avoid premature convergence to a single overall-best candidate."
        ),
    )
    novelty_filter: bool = Field(
        default=False,
        description=(
            "Reject near-duplicate candidates before evaluation to save budget "
            "(ShinkaEvolve-style novelty rejection). Off by default."
        ),
    )
    novelty_threshold: float = Field(
        default=0.97,
        ge=0.0,
        le=1.0,
        description=(
            "Text-similarity ratio (0–1) above which a candidate is treated as a "
            "near-duplicate of an earlier one. Higher = stricter (fewer rejections)."
        ),
    )
    novelty_max_retries: int = Field(
        default=1,
        ge=0,
        description=(
            "How many times to regenerate a near-duplicate candidate before "
            "skipping its evaluation entirely."
        ),
    )


class ProposerConfig(BaseModel):
    """Proposer agent configuration."""

    backend: BackendName = Field(
        default="api", description="Proposer backend type."
    )
    ensemble: list[BackendName] = Field(
        default_factory=list,
        description=(
            "Optional list of backends. When non-empty, the orchestrator picks a "
            "backend per iteration via a UCB bandit that favors backends producing "
            "improving candidates. Empty (default) = always use `backend`."
        ),
    )
    bandit_c: float = Field(
        default=1.41421356,
        ge=0.0,
        description="UCB exploration constant for ensemble selection. Higher = more exploration.",
    )
    model: str = Field(
        default="claude-sonnet-4-6",
        description="Model for the Proposer agent (api/openai backends; CLI backends use their own).",
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
    cascade: bool = Field(
        default=False,
        description=(
            "Staged evaluation: score a cheap first subset of tasks, and only run "
            "the rest if that subset clears `cascade_threshold` (AlphaEvolve/"
            "OpenEvolve-style cascade). Saves budget on weak candidates. Requires "
            "per-task mode (a non-empty `tasks` list); ignored otherwise."
        ),
    )
    cascade_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Minimum stage-1 mean score required to proceed to the full task set.",
    )
    cascade_stage1: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of tasks in the cheap first stage. 0 = auto (about one third "
            "of the task list, leaving at least one task for stage 2)."
        ),
    )
    eval_split: bool = Field(
        default=False,
        description=(
            "Hold out a test set: evolve on `val_tasks`, then evaluate only the best "
            "candidate once on `test_tasks` at the end (a held-out, honest score that "
            "never drives selection). Per-task mode only. Off by default = use `tasks` "
            "throughout."
        ),
    )
    val_tasks: list[str] = Field(
        default_factory=list,
        description=(
            "Task files used DURING search when eval_split is on "
            "(selection, Pareto, and early-stop all use these)."
        ),
    )
    test_tasks: list[str] = Field(
        default_factory=list,
        description=(
            "Held-out task files; the best candidate is scored on these ONCE at "
            "the end. Never used for selection."
        ),
    )


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
