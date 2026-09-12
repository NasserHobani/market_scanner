"""Walk-Forward evaluation للتوصية الحقيقية."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev

import pandas as pd

from ..config import MarketConfig
from . import recobt


@dataclass
class FoldResult:
    fold: int
    start: int
    train_end: int
    test_end: int
    is_expectancy: float | None
    oos_expectancy: float | None
    oos_closed: int


def _fold_bounds(n: int, train_window: int, test_window: int, step: int) -> list[tuple[int, int, int]]:
    out: list[tuple[int, int, int]] = []
    i = 0
    while i + train_window + test_window < n - 1:
        out.append((i, i + train_window, i + train_window + test_window))
        i += step
    return out


def run_symbol(df: pd.DataFrame, symbol: str, timeframe: str, cfg: MarketConfig,
               train_window: int, test_window: int, step: int,
               warmup: int = recobt.WARMUP) -> list[FoldResult]:
    folds = _fold_bounds(len(df), train_window, test_window, step)
    results: list[FoldResult] = []
    for idx, (start, train_end, test_end) in enumerate(folds, 1):
        train = recobt.report(recobt.scan_symbol(
            df, symbol, timeframe, cfg, step=1, warmup=warmup,
            start=max(start, warmup), end=train_end))
        test = recobt.report(recobt.scan_symbol(
            df, symbol, timeframe, cfg, step=1, warmup=warmup,
            start=max(train_end + 1, warmup), end=test_end))
        results.append(FoldResult(
            fold=idx,
            start=start,
            train_end=train_end,
            test_end=test_end,
            is_expectancy=train["overall"].get("expectancy"),
            oos_expectancy=test["overall"].get("expectancy"),
            oos_closed=int(test["overall"].get("closed") or 0),
        ))
    return results


def aggregate(folds: list[FoldResult]) -> dict:
    oos = [f.oos_expectancy for f in folds if f.oos_expectancy is not None]
    positives = [x for x in oos if x > 0]
    return {
        "folds": len(folds),
        "oos_expectancy_mean": round(mean(oos), 4) if oos else None,
        "oos_expectancy_std": round(pstdev(oos), 4) if len(oos) > 1 else 0.0 if oos else None,
        "oos_positive_ratio": round(len(positives) / len(oos) * 100, 1) if oos else None,
        "oos_worst_fold": round(min(oos), 4) if oos else None,
        "stable": bool(oos and len(positives) >= (len(oos) * 0.6) and min(oos) > -0.75),
    }
