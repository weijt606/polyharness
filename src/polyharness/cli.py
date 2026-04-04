"""PolyHarness CLI — the `ph` command."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from polyharness import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="polyharness")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
@click.option("-q", "--quiet", is_flag=True, help="Suppress non-essential output.")
@click.pass_context
def main(ctx: click.Context, verbose: bool, quiet: bool):
    """PolyHarness — Make your AI Agent evolve automatically."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet
    console.quiet = quiet


@main.command()
def doctor():
    """Detect installed agents and environment status."""
    from polyharness.doctor import run_doctor

    run_doctor()


@main.command()
@click.option(
    "--agent",
    type=click.Choice(["claude-code", "claw-code", "codex", "opencode", "api", "local"], case_sensitive=False),
    default="api",
    help="Agent backend to configure.",
)
@click.option(
    "--workspace",
    type=click.Path(),
    default=".ph_workspace",
    help="Workspace directory (default: .ph_workspace).",
)
@click.option(
    "--task-dir",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Directory containing tasks/ and optionally evaluate.py.",
)
@click.option(
    "--eval-script",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Path to a custom evaluate.py script.",
)
@click.option(
    "--base-harness",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="Directory containing the starting harness code.",
)
def init(agent: str, workspace: str, task_dir: str | None, eval_script: str | None, base_harness: str | None):
    """Initialize an optimization workspace for the given agent."""
    from polyharness.workspace import Workspace

    ws = Workspace.init(
        root=workspace,
        agent_backend=agent,
        task_dir=task_dir,
        eval_script=eval_script,
        base_harness=base_harness,
    )
    console.print(f"Initialized workspace at [bold]{ws.root}[/bold]")
    console.print(f"  Agent backend: {agent}")
    if base_harness:
        console.print(f"  Base harness:  copied from {base_harness}")
    if task_dir:
        console.print(f"  Tasks:         copied from {task_dir}")
    if eval_script:
        console.print(f"  Eval script:   copied {eval_script}")
    console.print("  Run 'ph run' to start optimization.")


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--max-iterations", type=int, default=None, help="Override max iterations.")
@click.option("--dry-run", is_flag=True, help="Only evaluate base harness, don't start search.")
@click.option("--resume", is_flag=True, help="Resume an interrupted search from where it left off.")
@click.option(
    "--backend",
    type=click.Choice(["api", "claude-code", "claw-code", "codex", "opencode", "local"], case_sensitive=False),
    default=None,
    help="Override proposer backend without editing config.",
)
@click.option(
    "--strategy",
    type=click.Choice(["best", "tournament", "all"], case_sensitive=False),
    default=None,
    help="Override parent selection strategy.",
)
def run(
    workspace: str,
    max_iterations: int | None,
    dry_run: bool,
    resume: bool,
    backend: str | None,
    strategy: str | None,
):
    """Start the optimization search loop."""
    from polyharness.orchestrator import Orchestrator
    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace. Run 'ph init' first.")
        raise SystemExit(1)

    config = ws.load_config()
    if max_iterations is not None:
        config.search.max_iterations = max_iterations

    if backend is not None:
        config.proposer.backend = backend  # type: ignore[assignment]

    if strategy is not None:
        config.search.parent_selection = strategy  # type: ignore[assignment]

    if dry_run:
        config.search.max_iterations = 0

    orch = Orchestrator(workspace=ws, config=config)
    orch.run(resume=resume)


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
def status(workspace: str):
    """Show current optimization progress."""
    from datetime import datetime

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    log = ws.search_log()
    if not log.entries:
        console.print("No iterations recorded yet. Run 'ph run' to start.")
        return

    table = Table(title="Search Progress")
    table.add_column("Iteration", style="cyan")
    table.add_column("Parent", style="dim")
    table.add_column("Score", style="green")
    table.add_column("Best So Far", style="bold green")

    for entry in log.entries:
        parent_str = f"iter_{entry.parent}" if entry.parent is not None else "—"
        table.add_row(
            f"iter_{entry.iteration}",
            parent_str,
            f"{entry.score:.4f}",
            f"{entry.best_so_far:.4f}",
        )

    console.print(table)

    # Summary stats
    entries = log.entries
    total = len(entries)
    best_i = log.best_iteration
    best_s = log.best_score
    base_s = entries[0].score if entries else 0.0
    improved_count = sum(1 for e in entries[1:] if e.score > base_s)
    improvement_rate = improved_count / (total - 1) if total > 1 else 0.0

    console.print(f"\nTotal iterations: {total}")
    console.print(f"Best: iter_{best_i} (score: {best_s:.4f})")
    console.print(
        f"Improvement: {base_s:.4f} → {best_s:.4f} "
        f"([green]+{best_s - base_s:.4f}[/green])"
    )
    if total > 1:
        console.print(f"Improvement rate: {improvement_rate:.0%} ({improved_count}/{total - 1} iterations beat base)")

    # Elapsed time from first to last entry timestamp
    try:
        t0 = datetime.fromisoformat(entries[0].timestamp)
        t1 = datetime.fromisoformat(entries[-1].timestamp)
        elapsed = t1 - t0
        mins = elapsed.total_seconds() / 60
        if mins < 1:
            console.print(f"Elapsed: {elapsed.total_seconds():.0f}s")
        else:
            console.print(f"Elapsed: {mins:.1f}min")
    except (ValueError, AttributeError):
        pass


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option(
    "--target",
    type=click.Path(),
    default=None,
    help="Target directory (default: workspace's base_harness/).",
)
def apply(workspace: str, target: str | None):
    """Apply the best harness back to base_harness (or a custom target).

    Copies the best candidate's code files into the target directory,
    replacing the existing harness. This closes the optimization loop.
    """
    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    target_path = Path(target) if target else ws.base_harness_dir

    try:
        best_i, copied = ws.apply_best(target_path)
    except RuntimeError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1)

    log = ws.search_log()
    console.print(
        f"[green]Applied iter_{best_i} (score: {log.best_score:.4f}) → {target_path}[/green]  "
        f"({copied} file{'s' if copied != 1 else ''})"
    )


@main.command()
@click.argument("left")
@click.argument("right")
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--no-diff", is_flag=True, help="Skip code diff output.")
def compare(left: str, right: str, workspace: str, no_diff: bool):
    """Compare two iteration candidates (scores + code diff)."""
    import difflib

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    def _parse_iter(s: str) -> int:
        s = s.strip()
        if s.startswith("iter_"):
            s = s[5:]
        return int(s)

    left_i, right_i = _parse_iter(left), _parse_iter(right)
    left_dir = ws.candidate_path(left_i)
    right_dir = ws.candidate_path(right_i)

    for label, d in [("Left", left_dir), ("Right", right_dir)]:
        if not d.exists():
            console.print(f"[red]Error:[/red] {label} candidate not found: {d}")
            raise SystemExit(1)

    left_score = _load_score(left_dir)
    right_score = _load_score(right_dir)

    # --- Score table with delta column ---
    table = Table(title=f"Comparison: iter_{left_i} vs iter_{right_i}")
    table.add_column("", style="bold")
    table.add_column(f"iter_{left_i}", style="cyan")
    table.add_column(f"iter_{right_i}", style="green")
    table.add_column("Δ", style="bold")

    l_overall = left_score.get("overall_score")
    r_overall = right_score.get("overall_score")
    table.add_row(
        "Overall Score",
        f"{l_overall}" if l_overall is not None else "?",
        f"{r_overall}" if r_overall is not None else "?",
        _format_delta(l_overall, r_overall),
    )

    # Per-task deltas
    l_tasks = left_score.get("task_scores", {})
    r_tasks = right_score.get("task_scores", {})
    all_tasks = sorted(set(l_tasks) | set(r_tasks))

    improved = regressed = unchanged = 0
    for task in all_tasks:
        l_val = l_tasks.get(task)
        r_val = r_tasks.get(task)
        delta_str = _format_delta(l_val, r_val)
        if isinstance(l_val, (int, float)) and isinstance(r_val, (int, float)):
            diff = r_val - l_val
            if diff > 0:
                improved += 1
            elif diff < 0:
                regressed += 1
            else:
                unchanged += 1
        table.add_row(
            f"  {task}",
            str(l_val) if l_val is not None else "—",
            str(r_val) if r_val is not None else "—",
            delta_str,
        )

    console.print(table)

    # Summary line
    parts = []
    if improved:
        parts.append(f"[green]+{improved} improved[/green]")
    if regressed:
        parts.append(f"[red]-{regressed} regressed[/red]")
    if unchanged:
        parts.append(f"{unchanged} unchanged")
    if parts:
        console.print(f"\nTasks: {', '.join(parts)}  (total {len(all_tasks)})")

    # --- Code diff ---
    if no_diff:
        return

    skip_names = {"score.json", "metadata.json", "traces", "__pycache__"}
    left_files = _collect_files(left_dir, skip_names)
    right_files = _collect_files(right_dir, skip_names)
    all_files = sorted(set(left_files) | set(right_files))

    if not all_files:
        return

    has_diff = False
    for rel in all_files:
        l_path = left_dir / rel
        r_path = right_dir / rel
        l_lines = l_path.read_text().splitlines(keepends=True) if l_path.exists() else []
        r_lines = r_path.read_text().splitlines(keepends=True) if r_path.exists() else []

        diff_lines = list(
            difflib.unified_diff(
                l_lines,
                r_lines,
                fromfile=f"iter_{left_i}/{rel}",
                tofile=f"iter_{right_i}/{rel}",
            )
        )
        if diff_lines:
            if not has_diff:
                console.print("\n[bold]Code Diff:[/bold]")
                has_diff = True
            _print_diff(diff_lines)

    if not has_diff:
        console.print("\n[dim]No code changes between candidates.[/dim]")


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
def best(workspace: str):
    """Show the best candidate so far."""
    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    log = ws.search_log()
    if not log.entries:
        console.print("No candidates yet. Run 'ph run' first.")
        return

    best_i = log.best_iteration
    best_dir = ws.candidate_path(best_i)

    console.print(f"[bold green]Best candidate: iter_{best_i}[/bold green]")
    console.print(f"Score: {log.best_score:.4f}")
    console.print(f"Directory: {best_dir}")

    # Show score details
    score_data = _load_score(best_dir)
    if score_data.get("task_scores"):
        console.print("\nTask scores:")
        for task, val in score_data["task_scores"].items():
            console.print(f"  {task}: {val}")

    # Show metadata
    meta_file = best_dir / "metadata.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        summary = meta.get("changes_summary", "")
        if summary:
            console.print(f"\nChanges: {summary[:200]}")


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--flat", is_flag=True, help="Show flat chronological list instead of tree.")
def log(workspace: str, flat: bool):
    """Show the search history as a tree (or flat list)."""

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    search_log = ws.search_log()
    if not search_log.entries:
        console.print("No iterations recorded yet. Run 'ph run' to start.")
        return

    best_i = search_log.best_iteration
    parent_scores = {e.iteration: e.score for e in search_log.entries}

    if flat:
        _print_log_flat(search_log.entries, best_i, parent_scores)
    else:
        _print_log_tree(search_log.entries, best_i, parent_scores)

    console.print(
        f"\n{len(search_log)} iterations  |  "
        f"best: iter_{best_i} ({search_log.best_score:.4f})"
    )


def _log_entry_label(entry, best_i: int, parent_scores: dict[int, float] | None = None) -> str:
    """Format a single log entry as a rich-styled label."""
    star = " [bold yellow]★[/bold yellow]" if entry.iteration == best_i else ""
    score_color = "green" if entry.score >= entry.best_so_far else "white"
    delta = ""
    if parent_scores and entry.parent is not None and entry.parent in parent_scores:
        d = entry.score - parent_scores[entry.parent]
        if d > 0:
            delta = f"  [green]+{d:.4f}[/green]"
        elif d < 0:
            delta = f"  [red]{d:.4f}[/red]"
        else:
            delta = "  [dim]+0.0000[/dim]"
    return (
        f"[bold cyan]iter_{entry.iteration}[/bold cyan]  "
        f"[{score_color}]{entry.score:.4f}[/{score_color}]{delta}{star}"
    )


def _print_log_tree(entries, best_i: int, parent_scores: dict[int, float] | None = None) -> None:
    """Print a rich Tree showing parent→child relationships."""
    from rich.tree import Tree

    if not entries:
        return

    # Build children map: parent_iteration → [child entries]
    children: dict[int | None, list] = {}
    for e in entries:
        children.setdefault(e.parent, []).append(e)

    # Root is iter_0 (parent=None)
    roots = children.get(None, [])
    if not roots:
        # Fallback to flat if no root found
        _print_log_flat(entries, best_i, parent_scores)
        return

    tree = Tree("[bold]Search Tree[/bold]")

    def _add_children(parent_tree, iteration: int) -> None:
        for child in children.get(iteration, []):
            label = _log_entry_label(child, best_i, parent_scores)
            branch = parent_tree.add(label)
            _add_children(branch, child.iteration)

    for root_entry in roots:
        label = _log_entry_label(root_entry, best_i, parent_scores)
        root_branch = tree.add(label)
        _add_children(root_branch, root_entry.iteration)

    console.print(tree)


def _print_log_flat(entries, best_i: int, parent_scores: dict[int, float] | None = None) -> None:
    """Print a chronological table of all iterations."""
    table = Table(title="Search Log")
    table.add_column("Iteration", style="cyan")
    table.add_column("Parent", style="dim")
    table.add_column("Score", style="green")
    table.add_column("Δ", style="bold")
    table.add_column("Best", style="bold green")
    table.add_column("", style="yellow")

    for e in entries:
        parent_str = f"iter_{e.parent}" if e.parent is not None else "—"
        star = "★" if e.iteration == best_i else ""
        delta = "—"
        if parent_scores and e.parent is not None and e.parent in parent_scores:
            d = e.score - parent_scores[e.parent]
            if d > 0:
                delta = f"[green]+{d:.4f}[/green]"
            elif d < 0:
                delta = f"[red]{d:.4f}[/red]"
            else:
                delta = "[dim]+0.0000[/dim]"
        table.add_row(
            f"iter_{e.iteration}",
            parent_str,
            f"{e.score:.4f}",
            delta,
            f"{e.best_so_far:.4f}",
            star,
        )

    console.print(table)


@main.command(name="export")
@click.argument("target")
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option(
    "--iteration",
    type=int,
    default=None,
    help="Export a specific iteration (default: best).",
)
@click.option(
    "--include-meta",
    is_flag=True,
    help="Also copy score.json, metadata.json, and traces/.",
)
def export_cmd(target: str, workspace: str, iteration: int | None, include_meta: bool):
    """Export a candidate to TARGET directory.

    By default exports the best candidate. Use --iteration to pick a specific one.
    Metadata files (score.json, metadata.json, traces/) are excluded unless --include-meta is set.
    """
    import shutil

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    log = ws.search_log()
    if not log.entries:
        console.print("[red]Error:[/red] No candidates yet. Run 'ph run' first.")
        raise SystemExit(1)

    if iteration is not None:
        iter_i = iteration
    else:
        iter_i = log.best_iteration

    src_dir = ws.candidate_path(iter_i)
    if not src_dir.exists():
        console.print(f"[red]Error:[/red] Candidate iter_{iter_i} not found: {src_dir}")
        raise SystemExit(1)

    target_path = Path(target)
    target_path.mkdir(parents=True, exist_ok=True)

    skip_meta = {"score.json", "metadata.json", "traces"}

    copied = 0
    for item in sorted(src_dir.rglob("*")):
        rel = item.relative_to(src_dir)
        if not include_meta and any(part in skip_meta for part in rel.parts):
            continue
        if item.name == "__pycache__" or "__pycache__" in rel.parts:
            continue
        dest = target_path / rel
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied += 1

    score_data = _load_score(src_dir)
    score_str = f" (score: {score_data['overall_score']:.4f})" if "overall_score" in score_data else ""
    console.print(
        f"[green]Exported iter_{iter_i}{score_str} → {target_path}[/green]  ({copied} file{'s' if copied != 1 else ''})"
    )


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--keep-best", is_flag=True, help="Keep the best candidate directory.")
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def clean(workspace: str, keep_best: bool, yes: bool):
    """Remove candidate directories and search log to free disk space."""
    import shutil

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    candidates_dir = ws.candidates_dir
    if not candidates_dir.exists() or not any(candidates_dir.iterdir()):
        console.print("Nothing to clean.")
        return

    log = ws.search_log()
    best_i = log.best_iteration if log.entries else None
    dirs = sorted(d for d in candidates_dir.iterdir() if d.is_dir())
    to_remove = [d for d in dirs if not (keep_best and best_i is not None and d.name == f"iter_{best_i}")]

    if not to_remove:
        console.print("Nothing to clean (best candidate preserved).")
        return

    total_size = sum(f.stat().st_size for d in to_remove for f in d.rglob("*") if f.is_file())
    size_mb = total_size / (1024 * 1024)

    console.print(f"Will remove {len(to_remove)} candidate dir(s) ({size_mb:.1f} MB)")
    if keep_best and best_i is not None:
        console.print(f"  Keeping: iter_{best_i} (best)")

    if not yes:
        click.confirm("Proceed?", abort=True)

    for d in to_remove:
        shutil.rmtree(d)

    # Clear search log and summary unless keeping best
    if not keep_best:
        log_path = ws.search_log_path
        if log_path.exists():
            log_path.write_text("")
        summary_dir = ws.summary_dir
        if summary_dir.exists():
            shutil.rmtree(summary_dir)
            summary_dir.mkdir()

    console.print(f"[green]Cleaned {len(to_remove)} candidate(s) ({size_mb:.1f} MB freed)[/green]")


# --- config command group ---


@main.group(name="config")
def config_group():
    """View or modify workspace configuration."""
    pass


@config_group.command(name="show")
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
def config_show(workspace: str):
    """Display the current workspace configuration."""
    import yaml

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    config = ws.load_config()
    console.print(yaml.dump(config.model_dump(), default_flow_style=False, sort_keys=False).rstrip())


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
def config_set(key: str, value: str, workspace: str):
    """Set a configuration value (dot-notation key).

    Examples:

      ph config set search.max_iterations 30

      ph config set proposer.backend claude-code

      ph config set proposer.temperature 0.5
    """
    import yaml

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    config_path = ws.root / ws.CONFIG_FILE
    with open(config_path) as f:
        data = yaml.safe_load(f) or {}

    # Navigate dot-notation key
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        if part not in target or not isinstance(target[part], dict):
            target[part] = {}
        target = target[part]

    # Auto-convert value types
    final_key = parts[-1]
    old_value = target.get(final_key)

    if value.lower() in ("true", "false"):
        converted = value.lower() == "true"
    else:
        try:
            converted = int(value)
        except ValueError:
            try:
                converted = float(value)
            except ValueError:
                converted = value

    target[final_key] = converted

    # Validate by loading the full config
    from polyharness.config import PolyHarnessConfig
    try:
        PolyHarnessConfig.model_validate(data)
    except Exception as exc:
        console.print(f"[red]Invalid configuration:[/red] {exc}")
        raise SystemExit(1)

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]{key}:[/green] {old_value} → {converted}")


# --- diff command ---


@main.command()
@click.argument("iteration", type=int)
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--no-diff", is_flag=True, help="Skip code diff output.")
def diff(iteration: int, workspace: str, no_diff: bool):
    """Show score comparison and code diff between base (iter_0) and ITERATION.

    This is a shorthand for: ph compare 0 <ITERATION>
    """
    from click import Context

    ctx = Context(compare, info_name="diff")
    ctx.invoke(compare, left="0", right=str(iteration), workspace=workspace, no_diff=no_diff)


# --- leaderboard command ---


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("-n", "--top", type=int, default=None, help="Show only top N candidates.")
@click.option("--tasks", is_flag=True, help="Show per-task score breakdown.")
def leaderboard(workspace: str, top: int | None, tasks: bool):
    """Display a ranked leaderboard of all candidates."""
    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    log = ws.search_log()
    if not log.entries:
        console.print("No iterations recorded yet. Run 'ph run' to start.")
        return

    # Build ranked list sorted by score descending
    entries = sorted(log.entries, key=lambda e: e.score, reverse=True)
    if top is not None:
        entries = entries[:top]

    base_score = next((e.score for e in log.entries if e.iteration == 0), 0.0)

    # Gather all task names
    all_task_names: list[str] = []
    if tasks:
        task_set: set[str] = set()
        for e in entries:
            task_set.update(e.task_scores.keys())
        all_task_names = sorted(task_set)

    table = Table(title="Leaderboard")
    table.add_column("#", style="dim", width=4)
    table.add_column("Candidate", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("vs Base", style="bold")
    table.add_column("Parent", style="dim")
    if tasks:
        for tn in all_task_names:
            table.add_column(tn, style="white", width=8)

    for rank, entry in enumerate(entries, 1):
        diff = entry.score - base_score
        if diff > 0:
            vs_base = f"[green]+{diff:.4f}[/green]"
        elif diff < 0:
            vs_base = f"[red]{diff:.4f}[/red]"
        else:
            vs_base = "[dim]±0[/dim]"

        parent_str = f"iter_{entry.parent}" if entry.parent is not None else "—"
        marker = " ★" if rank == 1 else ""

        row = [
            str(rank),
            f"iter_{entry.iteration}{marker}",
            f"{entry.score:.4f}",
            vs_base,
            parent_str,
        ]
        if tasks:
            for tn in all_task_names:
                val = entry.task_scores.get(tn)
                row.append(f"{val:.2f}" if val is not None else "—")

        table.add_row(*row)

    console.print(table)
    console.print(f"\n{len(log)} total iterations  |  Showing top {len(entries)}")


# --- trace command ---


@main.command()
@click.argument("iteration", type=int)
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option("--task", type=str, default=None, help="Show traces for a specific task only.")
def trace(iteration: int, workspace: str, task: str | None):
    """View execution traces (stdout, stderr, metrics) for ITERATION."""
    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    cand_dir = ws.candidate_path(iteration)
    if not cand_dir.exists():
        console.print(f"[red]Error:[/red] iter_{iteration} not found.")
        raise SystemExit(1)

    traces_dir = cand_dir / "traces"
    if not traces_dir.exists() or not any(traces_dir.iterdir()):
        console.print(f"No traces found for iter_{iteration}.")
        return

    # Collect unique task names from trace files
    task_names: set[str] = set()
    for f in traces_dir.iterdir():
        if f.is_file():
            name = f.stem
            # Remove suffixes like .stdout, .stderr, .exitcode, .metrics
            for suffix in (".stdout", ".stderr", ".exitcode", ".metrics"):
                if name.endswith(suffix):
                    name = name[: -len(suffix)]
                    break
            task_names.add(name)

    if task:
        task_names = {t for t in task_names if t == task}
        if not task_names:
            console.print(f"[red]Error:[/red] No traces for task '{task}'.")
            raise SystemExit(1)

    # Show score
    score_data = _load_score(cand_dir)
    if score_data:
        console.print(f"[bold]iter_{iteration}[/bold]  score={score_data.get('overall_score', '?')}")
    console.print()

    from rich.panel import Panel

    for tn in sorted(task_names):
        console.rule(f"[bold cyan]Task: {tn}[/bold cyan]")

        # Exit code
        exitcode_file = traces_dir / f"{tn}.exitcode"
        if exitcode_file.exists():
            code = exitcode_file.read_text().strip()
            color = "green" if code == "0" else "red"
            console.print(f"Exit code: [{color}]{code}[/{color}]")

        # Metrics
        metrics_file = traces_dir / f"{tn}.metrics.json"
        if metrics_file.exists():
            metrics = json.loads(metrics_file.read_text())
            score_val = metrics.get("score", metrics.get("overall_score"))
            if score_val is not None:
                console.print(f"Score: {score_val}")
            task_s = metrics.get("task_scores", {})
            if task_s:
                for k, v in task_s.items():
                    console.print(f"  {k}: {v}")

        # Stdout
        stdout_file = traces_dir / f"{tn}.stdout"
        if stdout_file.exists():
            content = stdout_file.read_text()
            if content.strip():
                # Truncate if very long
                lines = content.splitlines()
                if len(lines) > 50:
                    display = "\n".join(lines[:25] + [f"... ({len(lines) - 50} lines omitted) ..."] + lines[-25:])
                else:
                    display = content
                console.print(Panel(display, title="stdout", border_style="green", expand=False))

        # Stderr
        stderr_file = traces_dir / f"{tn}.stderr"
        if stderr_file.exists():
            content = stderr_file.read_text()
            if content.strip():
                lines = content.splitlines()
                if len(lines) > 30:
                    display = "\n".join(lines[:15] + [f"... ({len(lines) - 30} lines omitted) ..."] + lines[-15:])
                else:
                    display = content
                console.print(Panel(display, title="stderr", border_style="red", expand=False))

        console.print()


# --- report command ---


@main.command()
@click.option(
    "--workspace",
    type=click.Path(exists=True),
    default=".ph_workspace",
    help="Workspace directory.",
)
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=None,
    help="Output file path (default: summary/report.md).",
)
def report(workspace: str, output: str | None):
    """Generate a markdown report summarizing the optimization run."""
    from datetime import datetime

    from polyharness.workspace import Workspace

    ws = Workspace(workspace)
    if not ws.is_initialized():
        console.print("[red]Error:[/red] Not a PolyHarness workspace.")
        raise SystemExit(1)

    log = ws.search_log()
    if not log.entries:
        console.print("No iterations recorded yet. Run 'ph run' to start.")
        return

    config = ws.load_config()
    entries = log.entries
    best_i = log.best_iteration
    best_s = log.best_score
    base_s = entries[0].score if entries else 0.0
    total = len(entries)

    # Elapsed
    elapsed_str = "N/A"
    try:
        t0 = datetime.fromisoformat(entries[0].timestamp)
        t1 = datetime.fromisoformat(entries[-1].timestamp)
        elapsed = t1 - t0
        mins = elapsed.total_seconds() / 60
        elapsed_str = f"{mins:.1f} min" if mins >= 1 else f"{elapsed.total_seconds():.0f}s"
    except (ValueError, AttributeError):
        pass

    # Improvement stats
    improved_count = sum(1 for e in entries[1:] if e.score > base_s)
    improvement_rate = improved_count / (total - 1) if total > 1 else 0.0

    # Build markdown
    lines: list[str] = []
    lines.append("# PolyHarness Optimization Report\n")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    lines.append("## Configuration\n")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Backend | {config.proposer.backend} |")
    lines.append(f"| Model | {config.proposer.model} |")
    lines.append(f"| Max iterations | {config.search.max_iterations} |")
    lines.append(f"| Early stop patience | {config.search.early_stop_patience} |")
    lines.append(f"| Parent selection | {config.search.parent_selection} |")
    lines.append(f"| Evaluator | {config.evaluator.type} ({config.evaluator.entry}) |")
    lines.append("")

    lines.append("## Results Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total iterations | {total} |")
    lines.append(f"| Base score | {base_s:.4f} |")
    lines.append(f"| Best score | {best_s:.4f} (iter_{best_i}) |")
    if base_s > 0:
        delta_pct = (best_s - base_s) / base_s * 100
        lines.append(f"| Improvement | +{best_s - base_s:.4f} ({delta_pct:.1f}%) |")
    else:
        lines.append(f"| Improvement | +{best_s - base_s:.4f} |")
    if total > 1:
        lines.append(f"| Improvement rate | {improvement_rate:.0%} ({improved_count}/{total - 1}) |")
    else:
        lines.append("| Improvement rate | N/A |")
    lines.append(f"| Elapsed | {elapsed_str} |")
    lines.append("")

    # Iteration log table
    lines.append("## Iteration Log\n")
    lines.append("| # | Parent | Score | Best | Δ vs Parent |")
    lines.append("|---|--------|-------|------|-------------|")

    parent_scores = {e.iteration: e.score for e in entries}
    for e in entries:
        parent_str = f"iter_{e.parent}" if e.parent is not None else "—"
        delta = ""
        if e.parent is not None and e.parent in parent_scores:
            d = e.score - parent_scores[e.parent]
            delta = f"+{d:.4f}" if d >= 0 else f"{d:.4f}"
        best_marker = " **★**" if e.iteration == best_i else ""
        lines.append(
            f"| iter_{e.iteration}{best_marker} | {parent_str} | {e.score:.4f} | {e.best_so_far:.4f} | {delta} |"
        )
    lines.append("")

    # Task-level breakdown (if available)
    all_tasks: set[str] = set()
    for e in entries:
        all_tasks.update(e.task_scores.keys())

    if all_tasks:
        task_names = sorted(all_tasks)
        lines.append("## Per-Task Scores\n")
        header = "| Iteration |" + " | ".join(task_names) + " |"
        sep = "|-----------|" + " | ".join("-----" for _ in task_names) + " |"
        lines.append(header)
        lines.append(sep)

        for e in entries:
            row_parts = [f"iter_{e.iteration}"]
            for tn in task_names:
                val = e.task_scores.get(tn)
                row_parts.append(f"{val:.4f}" if val is not None else "—")
            lines.append("| " + " | ".join(row_parts) + " |")
        lines.append("")

    # Score trend (ASCII sparkline)
    lines.append("## Score Trend\n")
    lines.append("```")
    scores = [e.score for e in entries]
    max_s = max(scores) if scores else 1.0
    min_s = min(scores) if scores else 0.0
    range_s = max_s - min_s if max_s > min_s else 1.0
    bar_width = 40
    for e in entries:
        bar_len = int((e.score - min_s) / range_s * bar_width)
        bar = "█" * bar_len + "░" * (bar_width - bar_len)
        marker = " ★" if e.iteration == best_i else ""
        lines.append(f"iter_{e.iteration:>2} |{bar}| {e.score:.4f}{marker}")
    lines.append("```\n")

    md_content = "\n".join(lines)

    # Write to file
    out_path = Path(output) if output else ws.summary_dir / "report.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md_content)

    console.print(f"[green]Report written to {out_path}[/green]")
    console.print(f"  {total} iterations, best={best_s:.4f} (iter_{best_i}), Δ={best_s - base_s:+.4f}")


def _load_score(candidate_dir: Path) -> dict:
    score_file = candidate_dir / "score.json"
    if score_file.exists():
        return json.loads(score_file.read_text())
    return {}


def _format_delta(left_val: float | None, right_val: float | None) -> str:
    """Return a colored delta string like '+0.35' or '-0.10'."""
    if not isinstance(left_val, (int, float)) or not isinstance(right_val, (int, float)):
        return "—"
    diff = right_val - left_val
    if diff > 0:
        return f"[green]+{diff:.2f}[/green]"
    elif diff < 0:
        return f"[red]{diff:.2f}[/red]"
    return "[dim]0.00[/dim]"


def _collect_files(directory: Path, skip: set[str]) -> list[str]:
    """Collect relative file paths under *directory*, skipping names in *skip*."""
    results: list[str] = []
    for p in sorted(directory.rglob("*")):
        if any(part in skip for part in p.relative_to(directory).parts):
            continue
        if p.is_file():
            results.append(str(p.relative_to(directory)))
    return results


def _print_diff(diff_lines: list[str]) -> None:
    """Print unified diff lines with rich color."""
    for line in diff_lines:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            console.print(f"[bold]{line}[/bold]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        elif line.startswith("+"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-"):
            console.print(f"[red]{line}[/red]")
        else:
            console.print(line)
