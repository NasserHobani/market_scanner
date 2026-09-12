# -*- coding: utf-8 -*-
"""AIA-11 feature quality analysis for Dataset V3 rows."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from scanner.predictive.feature_registry import V3_COLUMNS


def analyze_feature_quality(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Variance, missingness, cardinality, pairwise correlation for V3 features."""
    n = len(rows)
    if n == 0:
        return {
            "rows": 0,
            "features": {},
            "constant_features": [],
            "near_duplicate_pairs": [],
            "high_missing": [],
        }

    by_feat: dict[str, list[float | None]] = {c: [] for c in V3_COLUMNS}
    for row in rows:
        feats = row.get("features") or {}
        for c in V3_COLUMNS:
            v = feats.get(c)
            by_feat[c].append(float(v) if v is not None else None)

    feature_stats: dict[str, Any] = {}
    constant: list[str] = []
    high_missing: list[str] = []
    for name, vals in by_feat.items():
        present = [v for v in vals if v is not None]
        missing_n = n - len(present)
        missingness = round(missing_n / n, 4) if n else 1.0
        if not present:
            feature_stats[name] = {
                "present": 0, "missingness": 1.0, "variance": None,
                "cardinality": 0, "mean": None,
            }
            high_missing.append(name)
            constant.append(name)
            continue
        uniq = len(set(round(v, 8) for v in present))
        var = round(statistics.pvariance(present), 8) if len(present) > 1 else 0.0
        feature_stats[name] = {
            "present": len(present),
            "missingness": missingness,
            "variance": var,
            "cardinality": uniq,
            "mean": round(statistics.mean(present), 6),
        }
        if uniq <= 1 or var == 0.0:
            constant.append(name)
        if missingness >= 0.5:
            high_missing.append(name)

    # Near-duplicate: |corr| >= 0.98 on overlapping present values
    near_dupes: list[dict[str, Any]] = []
    names = list(V3_COLUMNS)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pairs = [
                (va, vb) for va, vb in zip(by_feat[a], by_feat[b])
                if va is not None and vb is not None
            ]
            if len(pairs) < 8:
                continue
            corr = _pearson([p[0] for p in pairs], [p[1] for p in pairs])
            if corr is not None and abs(corr) >= 0.98:
                near_dupes.append({"a": a, "b": b, "corr": round(corr, 4)})

    return {
        "rows": n,
        "features": feature_stats,
        "constant_features": constant,
        "near_duplicate_pairs": near_dupes[:20],
        "high_missing": high_missing,
    }


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = statistics.mean(xs)
    my = statistics.mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    denx = sum((x - mx) ** 2 for x in xs) ** 0.5
    deny = sum((y - my) ** 2 for y in ys) ** 0.5
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def dataset_class_balance(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from scanner.ml.label_store import LabelName
    wins = sum(1 for r in rows if int(r.get(LabelName.BINARY_WIN.value) or 0) == 1)
    n = len(rows)
    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": round(wins / n, 4) if n else None,
    }


def rejection_breakdown(rejected: list[dict[str, str]]) -> dict[str, int]:
    return dict(Counter(r.get("reason", "unknown").split(":")[0] for r in rejected))
