"""ph doctor — detect installed agents and environment status."""

from __future__ import annotations

import os
import shutil

import click


def run_doctor() -> None:
    """Check environment and report available agent backends."""
    click.echo("PolyHarness Environment Check")
    click.echo("═" * 40)

    # API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    _status("Anthropic API Key", "configured" if api_key else "not set", bool(api_key))

    # CLI agent backends
    click.echo()
    click.echo("CLI Agent Backends")
    click.echo("─" * 40)

    from poly_harness.proposer.adapters import ADAPTER_REGISTRY

    available = []
    for backend_name, adapter_cls in sorted(ADAPTER_REGISTRY.items()):
        adapter = adapter_cls()
        binary = adapter.default_binary
        found = shutil.which(binary) is not None
        _status(backend_name, f"{binary} → found" if found else f"{binary} → not found", found)
        if found:
            available.append(backend_name)

    click.echo()
    click.echo("Other Backends")
    click.echo("─" * 40)
    _status("api", "Anthropic API — " + ("configured" if api_key else "no key"), bool(api_key))
    _status("local", "offline development — always available", True)

    # Recommendation
    click.echo()
    if "claude-code" in available:
        click.echo("Recommended: claude-code (highest paper fidelity)")
    elif "claw-code" in available:
        click.echo("Recommended: claw-code (open-source, full tool support)")
    elif "codex" in available:
        click.echo("Recommended: codex (OpenAI agent)")
    elif "opencode" in available:
        click.echo("Recommended: opencode (open-source agent)")
    elif api_key:
        click.echo("Recommended: api (Anthropic API direct)")
    else:
        click.echo("Recommended: local (offline development mode)")
    click.echo(f"\nUsage: ph init --agent <backend>")


def _status(label: str, detail: str, ok: bool) -> None:
    icon = "✅" if ok else "❌"
    click.echo(f"  {icon} {label}: {detail}")
