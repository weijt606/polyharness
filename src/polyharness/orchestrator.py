"""Orchestrator — the Meta-Harness search loop coordinator."""

from __future__ import annotations

import random
import shutil
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table

from polyharness.config import PolyHarnessConfig
from polyharness.evaluator import BaseEvaluator, EvalResult, create_evaluator
from polyharness.proposer import BaseProposer, create_proposer
from polyharness.proposer.bandit import BackendBandit
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
        proposers: dict[str, BaseProposer] | None = None,
    ):
        self.workspace = workspace
        self.config = config
        self.evaluator = evaluator or create_evaluator(config.evaluator, cwd=workspace.root)
        self.search_log = SearchLog(workspace.search_log_path)

        # Cache of backend-name → proposer. Pre-seeded ones (e.g. from tests)
        # are used as-is; others are created lazily on first use.
        self._proposer_cache: dict[str, BaseProposer] = dict(proposers or {})

        # Ensemble (bandit) mode is opt-in and only active when the caller did
        # not inject a single fixed proposer. An explicit `proposer=` always
        # wins, keeping existing behavior and tests unchanged.
        ensemble = config.proposer.ensemble
        if proposer is None and ensemble:
            self.bandit: BackendBandit | None = BackendBandit(
                list(ensemble), c=config.proposer.bandit_c
            )
            self.proposer: BaseProposer | None = None  # chosen per iteration
        else:
            self.bandit = None
            self.proposer = (
                proposer
                or self._proposer_cache.get(config.proposer.backend)
                or create_proposer(config.proposer)
            )

    def run(self, resume: bool = False) -> SearchResult:
        """Execute the full search loop."""
        max_iter = self.config.search.max_iterations

        # Reproducibility: seed RNG so tournament/pareto/novelty are repeatable.
        if self.config.search.seed is not None:
            random.seed(self.config.search.seed)

        console.rule("[bold blue]PolyHarness Optimization Loop")
        console.print(f"Max iterations: {max_iter}")
        console.print(f"Early stop patience: {self.config.search.early_stop_patience}")
        if self.bandit is not None:
            console.print(
                f"Proposer ensemble: {', '.join(self.bandit.backends)} (UCB bandit)"
            )
        else:
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

                backend: str | None = None
                try:
                    # Step 1: Select parent
                    parent = self._select_parent()

                    # Step 1.5: Select which backend proposes this iteration
                    # (bandit) or fall back to the single fixed proposer.
                    backend, proposer = self._select_proposer()

                    # Steps 2–3: Propose a candidate, optionally rejecting
                    # near-duplicates (novelty filter).
                    cand_dir, metadata, accepted = self._propose_with_novelty(
                        i, parent, proposer
                    )

                    # If the candidate is a near-duplicate even after retries,
                    # skip its (potentially expensive) evaluation entirely.
                    if not accepted:
                        console.print(
                            f"\n[yellow]iter_{i}: skipped — near-duplicate of an "
                            f"earlier candidate (saved evaluation budget)[/yellow]"
                        )
                        # Drop the dangling candidate dir so its copied-from-parent
                        # score.json doesn't pollute the leaderboard.
                        shutil.rmtree(cand_dir, ignore_errors=True)
                        self._reward_backend(backend, 0.0)  # duplicate = no value
                        patience_counter += 1
                        progress.update(task, advance=1)
                        if patience_counter >= self.config.search.early_stop_patience:
                            break
                        continue

                    # Step 4: Evaluate
                    score = self._evaluate_iteration(i)
                except Exception as exc:
                    console.print(f"\n[red]iter_{i} failed: {exc}[/red]")
                    self._reward_backend(backend, 0.0)  # failure = no value
                    patience_counter += 1
                    progress.update(task, advance=1)
                    if patience_counter >= self.config.search.early_stop_patience:
                        break
                    continue

                # Record which backend produced this candidate (observability).
                if backend is not None:
                    metadata = {**metadata, "proposer_backend": backend}

                # Step 5: Store results
                log_entry = self.search_log.entries[-1]
                self.workspace.store_iteration(
                    iteration=i,
                    score=log_entry.score,
                    task_scores=log_entry.task_scores,
                    parent=parent,
                    metadata=metadata,
                )

                # Reward the backend when its candidate improved over its parent.
                self._reward_backend(
                    backend, 1.0 if score > self._parent_score(parent) else 0.0
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

        # Base harness is always scored in full; candidates may use cascade.
        eval_result = self._run_eval(cand_dir, allow_cascade=not is_base)

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

    def _run_eval(self, cand_dir, *, allow_cascade: bool) -> EvalResult:
        """Evaluate a candidate, applying cascade when enabled and applicable."""
        tasks = self.config.evaluator.tasks
        if allow_cascade and self.config.evaluator.cascade and len(tasks) >= 2:
            return self._evaluate_with_cascade(cand_dir, tasks)
        return self.evaluator.evaluate(candidate_dir=cand_dir, tasks=tasks)

    def _evaluate_with_cascade(self, cand_dir, tasks: list[str]) -> EvalResult:
        """Staged evaluation: cheap subset first, full set only if it clears the gate.

        Splits *tasks* into a stage-1 subset and the rest. A candidate whose
        stage-1 mean falls below ``cascade_threshold`` is rejected early without
        running stage 2, saving evaluation budget on weak candidates
        (AlphaEvolve/OpenEvolve-style cascade). Stage-1 tasks are never
        re-evaluated, so the result is deterministic.
        """
        k = self.config.evaluator.cascade_stage1
        if k <= 0:
            k = max(1, (len(tasks) + 2) // 3)  # ~1/3 of tasks, rounded up
        k = min(k, len(tasks) - 1)  # always leave at least one task for stage 2

        stage1, stage2 = tasks[:k], tasks[k:]
        r1 = self.evaluator.evaluate(candidate_dir=cand_dir, tasks=stage1)

        threshold = self.config.evaluator.cascade_threshold
        if r1.overall_score < threshold:
            console.print(
                f"[dim]  cascade: gated at stage 1 "
                f"({r1.overall_score:.2f} < {threshold:.2f}) — "
                f"skipped {len(stage2)} task(s)[/dim]"
            )
            return r1

        r2 = self.evaluator.evaluate(candidate_dir=cand_dir, tasks=stage2)
        task_scores = {**r1.task_scores, **r2.task_scores}
        traces = {**r1.traces, **r2.traces}
        overall = (
            sum(task_scores.values()) / len(task_scores) if task_scores else 0.0
        )
        return EvalResult(overall_score=overall, task_scores=task_scores, traces=traces)

    def _select_parent(self) -> int:
        """Select parent candidate based on strategy."""
        strategy = self.config.search.parent_selection
        if strategy == "best":
            return self.search_log.best_iteration
        elif strategy == "tournament":
            return self._tournament_select()
        elif strategy == "pareto":
            return self._pareto_select()
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

    def _pareto_select(self) -> int:
        """GEPA-style Pareto-frontier parent selection.

        Rather than always branching from the single best *overall* candidate,
        build the set of candidates that achieve the top score on at least one
        individual task ("per-task winners"), then sample one of them weighted
        by how many tasks it wins.  This keeps specialists that are strong on a
        subset of tasks alive as stepping stones, avoiding premature
        convergence (Pareto-based selection, GEPA — arXiv:2507.19457).

        Falls back to ``best`` when per-task scores are unavailable.
        """
        entries = [e for e in self.search_log.entries if e.task_scores]
        if not entries:
            return self.search_log.best_iteration

        task_names: set[str] = set()
        for e in entries:
            task_names.update(e.task_scores.keys())
        if not task_names:
            return self.search_log.best_iteration

        eps = 1e-9
        win_counts: dict[int, int] = {}
        for task in task_names:
            best_for_task = max(
                e.task_scores.get(task, float("-inf")) for e in entries
            )
            for e in entries:
                if e.task_scores.get(task, float("-inf")) >= best_for_task - eps:
                    win_counts[e.iteration] = win_counts.get(e.iteration, 0) + 1

        if not win_counts:
            return self.search_log.best_iteration

        iterations = list(win_counts.keys())
        weights = [win_counts[i] for i in iterations]
        return random.choices(iterations, weights=weights, k=1)[0]

    def _select_proposer(self) -> tuple[str | None, BaseProposer]:
        """Pick the proposer for this iteration.

        Returns ``(backend_name, proposer)``. In single-backend mode the name
        is ``None`` and the fixed proposer is returned. In ensemble mode the
        UCB bandit chooses a backend and its (lazily created) proposer.
        """
        if self.bandit is None:
            assert self.proposer is not None
            return None, self.proposer
        backend = self.bandit.select()
        return backend, self._get_proposer(backend)

    def _get_proposer(self, backend: str) -> BaseProposer:
        """Return (creating + caching on first use) the proposer for *backend*."""
        if backend not in self._proposer_cache:
            sub_config = self.config.proposer.model_copy(update={"backend": backend})
            self._proposer_cache[backend] = create_proposer(sub_config)
        return self._proposer_cache[backend]

    def _reward_backend(self, backend: str | None, reward: float) -> None:
        """Feed a reward to the bandit (no-op in single-backend mode)."""
        if self.bandit is not None and backend is not None:
            self.bandit.update(backend, reward)

    def _parent_score(self, parent: int | None) -> float:
        """Score of the parent iteration (0.0 if unknown)."""
        if parent is None:
            return 0.0
        for entry in self.search_log.entries:
            if entry.iteration == parent:
                return entry.score
        return 0.0

    def _propose_with_novelty(self, iteration: int, parent: int, proposer: BaseProposer):
        """Propose a candidate, optionally rejecting near-duplicates.

        Returns ``(candidate_dir, metadata, accepted)``.  When the novelty
        filter is enabled and the proposer keeps producing a candidate that is
        too similar to an earlier one, regenerate up to ``novelty_max_retries``
        times; if still a near-duplicate, return ``accepted=False`` so the
        caller can skip evaluation and save budget (ShinkaEvolve-style code
        novelty rejection — arXiv:2509.19349).
        """
        cand_dir, metadata = self._propose_candidate(iteration, parent, proposer)

        if not self.config.search.novelty_filter:
            return cand_dir, metadata, True

        threshold = self.config.search.novelty_threshold
        max_retries = self.config.search.novelty_max_retries

        for attempt in range(max_retries + 1):
            similarity = self._max_similarity(iteration, cand_dir)
            if similarity < threshold:
                return cand_dir, metadata, True
            if attempt < max_retries:
                console.print(
                    f"[dim]iter_{iteration}: candidate {similarity:.2f} similar to an "
                    f"existing one — regenerating ({attempt + 1}/{max_retries})[/dim]"
                )
                cand_dir, metadata = self._propose_candidate(iteration, parent, proposer)

        return cand_dir, metadata, False

    def _propose_candidate(self, iteration: int, parent: int, proposer: BaseProposer):
        """Prepare a candidate dir, run the proposer, and verify output.

        Returns ``(candidate_dir, metadata)``.  Raises ``FileNotFoundError``
        when the proposer fails to produce ``harness.py``.
        """
        cand_dir = self.workspace.prepare_candidate(iteration, parent)
        metadata = proposer.propose(
            workspace_root=self.workspace.root,
            candidate_dir=cand_dir,
            iteration=iteration,
            parent=parent,
        )
        if not (cand_dir / "harness.py").exists():
            raise FileNotFoundError(
                f"Proposer did not generate harness.py in iter_{iteration}"
            )
        return cand_dir, metadata

    def _max_similarity(self, iteration: int, cand_dir) -> float:
        """Max text similarity of *cand_dir* against all earlier candidates.

        Uses :class:`difflib.SequenceMatcher` (stdlib, no extra deps) on the
        concatenated editable harness files. Returns a ratio in ``[0, 1]``.
        """
        from difflib import SequenceMatcher

        new_text = self._candidate_text(cand_dir)
        if not new_text:
            return 0.0

        best = 0.0
        for entry in self.search_log.entries:
            if entry.iteration == iteration:
                continue
            other_dir = self.workspace.candidate_path(entry.iteration)
            if not other_dir.exists():
                continue
            other_text = self._candidate_text(other_dir)
            if not other_text:
                continue
            ratio = SequenceMatcher(None, new_text, other_text).ratio()
            if ratio > best:
                best = ratio
        return best

    def _candidate_text(self, cand_dir) -> str:
        """Concatenate a candidate's editable harness files into one blob."""
        parts: list[str] = []
        for fname in self.config.harness.editable_files:
            f = cand_dir / fname
            if f.is_file():
                parts.append(f.read_text())
        if not parts:
            entry = cand_dir / self.config.harness.entry
            if entry.is_file():
                parts.append(entry.read_text())
        return "\n".join(parts)

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

        # Ensemble bandit breakdown: which backend earned its picks.
        if self.bandit is not None and self.bandit.total_pulls > 0:
            bandit_table = Table(title="Proposer ensemble (UCB bandit)")
            bandit_table.add_column("Backend")
            bandit_table.add_column("Picks", justify="right")
            bandit_table.add_column("Improve rate", justify="right")
            for backend, s in self.bandit.stats().items():
                bandit_table.add_row(
                    backend, str(s["pulls"]), f"{s['mean_reward']:.2f}"
                )
            console.print(bandit_table)

        console.print(
            "\nRun [bold]ph best[/bold] to see details, or [bold]ph apply[/bold] to apply the result."
        )
