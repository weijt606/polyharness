from poly_harness.proposer.adapters import ADAPTER_REGISTRY
from poly_harness.proposer.api_proposer import APIProposer
from poly_harness.proposer.base import BaseProposer
from poly_harness.proposer.cli_proposer import CLIProposer
from poly_harness.proposer.local_proposer import LocalProposer

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
	if config.backend == "local":
		return LocalProposer()
	if config.backend in CLI_BACKENDS:
		return CLIProposer(
			backend=config.backend,
			cli_path=config.cli_path,
		)
	raise ValueError(
		f"Unsupported proposer backend: {config.backend}. "
		f"Supported backends: api, local, {', '.join(sorted(CLI_BACKENDS))}."
	)

__all__ = ["APIProposer", "CLIProposer", "LocalProposer", "BaseProposer", "create_proposer"]
