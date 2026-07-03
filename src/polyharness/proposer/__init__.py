from polyharness.proposer.adapters import ADAPTER_REGISTRY
from polyharness.proposer.api_proposer import APIProposer
from polyharness.proposer.base import BaseProposer
from polyharness.proposer.cli_proposer import CLIProposer
from polyharness.proposer.local_proposer import LocalProposer
from polyharness.proposer.openai_proposer import OpenAIProposer

# CLI backends are all backends that have an adapter registered.
CLI_BACKENDS = set(ADAPTER_REGISTRY)


def create_proposer(config) -> BaseProposer:
    """Factory: create a proposer from config."""
    if config.backend == "api":
        return APIProposer(
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    if config.backend == "openai":
        return OpenAIProposer(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
        )
    if config.backend == "local":
        return LocalProposer()
    if config.backend in CLI_BACKENDS:
        return CLIProposer(
            backend=config.backend,
            cli_path=config.cli_path,
            timeout=getattr(config, "timeout", 600),
        )
    raise ValueError(
        f"Unsupported proposer backend: {config.backend}. "
        f"Supported backends: api, openai, local, {', '.join(sorted(CLI_BACKENDS))}."
    )

__all__ = ["APIProposer", "OpenAIProposer", "CLIProposer", "LocalProposer", "BaseProposer", "create_proposer"]
