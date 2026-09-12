# -*- coding: utf-8 -*-
"""Walk-forward optimization — no look-ahead bias."""
from __future__ import annotations

from typing import Any

from .evaluation import ParameterEvaluator, sort_rows_by_time
from .grid_search import GridSearchOptimizer
from .parameter_space import ParameterSpace
from .random_search import RandomSearchOptimizer
from .ranking import ParameterRanker


def _fold_bounds(n: int, train_window: int, validation_window: int,
                 step: int) -> list[tuple[int, int, int]]:
    """Return (start, train_end, val_end) indices for each fold."""
    folds: list[tuple[int, int, int]] = []
    i = 0
    while i + train_window + validation_window <= n:
        folds.append((i, i + train_window, i + train_window + validation_window))
        i += step
    return folds


class WalkForwardOptimizer:
    """Optimize on train window, validate on OOS window — rolling evaluation."""

    def __init__(self, *, inner_method: str = "grid") -> None:
        self._inner_method = inner_method
        self._grid = GridSearchOptimizer()
        self._random = RandomSearchOptimizer()
        self._ranker = ParameterRanker()

    def search(self, space: ParameterSpace, evaluator: ParameterEvaluator,
               rows: list[dict], *, train_window: int = 30,
               validation_window: int = 10, step: int = 10,
               n_samples: int = 20, seed: int = 42,
               **kwargs: Any) -> list[dict[str, Any]]:
        sorted_rows = sort_rows_by_time(rows)
        n = len(sorted_rows)
        folds = _fold_bounds(n, train_window, validation_window, step)
        if not folds:
            # Fallback: single split 70/30
            split = max(1, int(n * 0.7))
            folds = [(0, split, n)]

        fold_results: list[dict[str, Any]] = []
        all_oos: list[dict[str, Any]] = []

        for fold_idx, (start, train_end, val_end) in enumerate(folds):
            train_rows = sorted_rows[start:train_end]
            val_rows = sorted_rows[train_end:val_end]

            if self._inner_method == "random":
                candidates = self._random.search(
                    space, evaluator, train_rows,
                    n_samples=n_samples, seed=seed + fold_idx)
            else:
                candidates = self._grid.search(space, evaluator, train_rows)

            if not candidates:
                continue

            ranked = self._ranker.rank(candidates)
            best_params = ranked[0]["params"]

            oos_eval = evaluator.evaluate_oos(train_rows, val_rows, best_params)
            oos_eval["fold_index"] = fold_idx
            oos_eval["train_size"] = len(train_rows)
            oos_eval["validation_size"] = len(val_rows)
            fold_results.append(oos_eval)
            all_oos.append(oos_eval)

        if not all_oos:
            return [evaluator.evaluate(rows, space.defaults())]

        # Pick params with best mean OOS expectancy across folds
        param_scores: dict[str, tuple[dict[str, Any], list[float]]] = {}
        for result in all_oos:
            key = str(sorted(result["params"].items()))
            oos_exp = (result.get("oos_performance") or {}).get("expectancy")
            if oos_exp is not None:
                entry = param_scores.setdefault(key, (result["params"], []))
                entry[1].append(float(oos_exp))

        if param_scores:
            best_key = max(
                param_scores,
                key=lambda k: sum(param_scores[k][1]) / len(param_scores[k][1]),
            )
            best_params = dict(param_scores[best_key][0])
        else:
            best_params = space.defaults()

        final = evaluator.evaluate_oos(
            sorted_rows[:folds[-1][1]],
            sorted_rows[folds[-1][1]:folds[-1][2]],
            best_params,
        )
        final["walk_forward"] = {
            "fold_count": len(fold_results),
            "folds": [
                {
                    "fold_index": f["fold_index"],
                    "train_size": f["train_size"],
                    "validation_size": f["validation_size"],
                    "is_expectancy": f.get("expectancy"),
                    "oos_expectancy": (f.get("oos_performance") or {}).get("expectancy"),
                }
                for f in fold_results
            ],
            "mean_oos_expectancy": (
                round(sum(
                    (f.get("oos_performance") or {}).get("expectancy") or 0
                    for f in fold_results
                ) / len(fold_results), 4) if fold_results else None
            ),
        }
        return [final]
