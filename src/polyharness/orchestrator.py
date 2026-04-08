"""Orchestrator — the Meta-Harness search loop coordinator."""

from __future__ import annotations

import random
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from polyharness.config import PolyHarnessConfig
from polyharness.evaluator import BaseEvaluator, create_evaluator
from polyharness.proposer import BaseProposer, create_proposer
from polyharness.search_log import SearchLog
from polyharness.workspace import Workspace

console = Console()


@dataclass
class SearchResult:
    """Final result of a search run."""

    best_iteration: int
    best_score: float
    total_iterations: int


class Orchestrator:
    """Meta-Harness search loop orchestrator.

    Coordinates proposer → evaluate → store cycle.
    """

    def __init__(
        self,
        workspace: Workspace,
        config: PolyHarnessConfig,
        proposer: BaseProposer | None = None,
        evaluator: BaseEvaluator | None = None,
    ):
        self.workspace = workspace
        self.config = config
        self.proposer = proposer or create_proposer(config.proposer)
        self.evaluator = evaluator or create_evaluator(config.evaluator, cwd=workspace.root)
        self.search_log = SearchLog(workspace.search_log_path)

    def run(self, resume: bool = False) -> SearchResult:
        """Execute the full search loop."""
        max_iter = self.config.search.max_iterations

        console.rule("[bold blue]PolyHarness Optimization Loop")
        console.print(f"Max iterations: {max_iter}")
        console.print(f"Early stop patience: {self.config.search.early_stop_patience}")
        console.print(f"Proposer backend: {self.config.proposer.backend}")
        console.print()

        # Determine starting point (resume or fresh)
        start_iter = 1
        best_score = 0.0
        best_iteration = 0
        patience_counter = 0

        if resume and len(self.search_log) > 0:
            # Restore state from existing search log
            entries = self.search_log.entries
            best_score = self.search_log.best_score
            best_iteration = self.search_log.best_iteration
            start_iter = max(e.iteration for e in entries) + 1

            # Recalculate patience_counter from tail of entries
            patience_counter = 0
            for e in reversed(entries):
                if e.iteration == 0:
                    break
                if e.score <= best_score and e.score < best_score:
                    patience_counter += 1
                else:
                    break

            console.print(
                f"[yellow]Resuming from iter_{start_iter - 1} "
                f"(best={best_score:.4f} at iter_{best_iteration}, "
                f"patience={patience_counter}/{self.config.search.early_stop_patience})[/yellow]"
            )
            console.print()
        else:
            # Step 0: Evaluate base harness
            console.print("[bold]Step 0:[/bold] Evaluating base harness...")
            try:
                base_result = self._evaluate_iteration(0, is_base=True)
            except FileNotFoundError as e:
                console.print(f"[red]Error:[/red] {e}")
                console.print(
                    "\n[yellow]Hint:[/yellow] Your workspace is missing an evaluate script. "
                    "Re-initialize with:\n"
                    "  ph init --task-dir ./your_tasks/   (if it contains evaluate.py)\n"
                    "  ph init --eval-script ./evaluate.py  (to specify one directly)\n"
                    "\nOr copy an evaluate.py into the workspace root."
                )
                raise SystemExit(1)
            best_score = base_result
            best_iteration = 0

            self._print_iteration(0, base_result, best_score, None)

        if max_iter == 0:
            console.print("\n[yellow]Dry run — base evaluation only.[/yellow]")
            return SearchResult(
                best_iteration=0,
                best_score=best_score,
                total_iterations=0,
            )

        remaining = max_iter - (start_iter - 1)
        if remaining <= 0:
            console.print("[yellow]All iterations already completed.[/yellow]")
            result = SearchResult(
                best_iteration=best_iteration,
                best_score=best_score,
                total_iterations=len(self.search_log) - 1,
            )
            self._print_summary(result)
            return result

        from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("best={task.fields[best]:.4f}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Searching", total=remaining, best=best_score)

            for i in range(start_iter, max_iter + 1):
                progress.update(task, description=f"iter_{i}")

                try:
                    # Step 1: Select parent
                    parent = self._select_parent()

                    # Step 2: Prepare candidate directory (copy from parent)
                    cand_dir = self.workspace.prepare_candidate(i, parent)

                    # Step 3: Proposer generates new candidate
                    metadata = self.proposer.propose(
                        workspace_root=self.workspace.root,
                        candidate_dir=cand_dir,
                        iteration=i,
                        parent=parent,
                    )

                    # Step 3.5: Verify proposer produced a harness file
                    if not (cand_dir / "harness.py").exists():
                        raise FileNotFoundError(
                            f"Proposer did not generate harness.py in iter_{i}"
                        )

                    # Step 4: Evaluate
                    score = self._evaluate_iteration(i)
                except Exception as exc:
                    console.print(f"\n[red]iter_{i} failed: {exc}[/red]")
                    patience_counter += 1
                    progress.update(task, advance=1)
                    if patience_counter >= self.config.search.early_stop_patience:
                        break
                    continue

                # Step 5: Store results
                log_entry = self.search_log.entries[-1]
                self.workspace.store_iteration(
                    iteration=i,
                    score=log_entry.score,
                    task_scores=log_entry.task_scores,
                    parent=parent,
                    metadata=metadata,
                )

                # Step 6: Update best & check early stop
                if score > best_score:
                    best_score = score
                    best_iteration = i
                    patience_counter = 0
                else:
                    patience_counter += 1

                progress.update(task, advance=1, best=best_score)

                if patience_counter >= self.config.search.early_stop_patience:
                    break

        # Print iteration summary after progress bar completes
        console.print()
        for entry in self.search_log.entries:
            if entry.iteration > 0:
                self._print_iteration(entry.iteration, entry.score, entry.best_so_far, entry.parent)

        if patience_counter >= self.config.search.early_stop_patience:
            console.print("\n[yellow]Early stopping triggered.[/yellow]")

        # Final summary
        result = SearchResult(
            best_iteration=best_iteration,
            best_score=best_score,
            total_iterations=len(self.search_log) - 1,
        )
        self._print_summary(result)
        return result

    def _evaluate_iteration(self, iteration: int, is_base: bool = False) -> float:
        """Evaluate a candidate and log results."""
        if is_base:
            cand_dir = self.workspace.base_harness_dir
            # Also store as iter_0
            iter_dir = self.workspace.candidate_path(0)
            if not iter_dir.exists():
                self.workspace.prepare_candidate(0, parent=None)
        else:
            cand_dir = self.workspace.candidate_path(iteration)

        eval_result = self.evaluator.evaluate(
            candidate_dir=cand_dir,
            tasks=self.config.evaluator.tasks,
        )

        parent = None if is_base else self.search_log.best_iteration
        self.search_log.append(
            iteration=iteration,
            parent=parent,
            score=eval_result.overall_score,
            task_scores=eval_result.task_scores,
        )

        if is_base:
            self.workspace.store_iteration(
                iteration=0,
                score=eval_result.overall_score,
                task_scores=eval_result.task_scores,
                parent=None,
                metadata={"source": "base_harness"},
            )

        return eval_result.overall_score

    def _select_parent(self) -> int:
        """Select parent candidate based on strategy."""
        strategy = self.config.search.parent_selection
        if strategy == "best":
            return self.search_log.best_iteration
        elif strategy == "tournament":
            return self._tournament_select()
        else:  # "all" — proposer decides, so we pass best as default parent
            return self.search_log.best_iteration

    def _tournament_select(self, k: int = 3) -> int:
        """Randomized tournament selection.

        Randomly sample *k* entries from the search log and return the
        iteration with the highest score.  This adds diversity while still
        biasing towards stronger candidates — matching the "candidate
        selection strategy" requirement from the product doc.
        """
        entries = self.search_log.entries
        if len(entries) <= k:
            contestants = entries
        else:
            contestants = random.sample(entries, k)
        return max(contestants, key=lambda e: e.score).iteration

    def _print_iteration(self, iteration: int, score: float, best_so_far: float, parent: int | None) -> None:
        parent_str = f"iter_{parent}" if parent is not None else "base"
        delta = score - best_so_far if iteration > 0 else 0
        delta_str = f"{delta:+.4f}" if iteration > 0 else "—"
        console.print(
            f"  iter_{iteration}: score={score:.4f}  best={max(score, best_so_far):.4f}  "
            f"delta={delta_str}  parent={parent_str}"
        )

    def _print_summary(self, result: SearchResult) -> None:
        console.print()
        console.rule("[bold green]Search Complete")
        table = Table(show_header=False)
        table.add_row("Best iteration", f"iter_{result.best_iteration}")
        table.add_row("Best score", f"{result.best_score:.4f}")
        table.add_row("Total iterations", str(result.total_iterations))
        console.print(table)
        console.print(
            "\nRun [bold]ph best[/bold] to see details, or [bold]ph apply[/bold] to apply the result."
        )
