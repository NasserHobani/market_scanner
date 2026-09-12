# -*- coding: utf-8 -*-
"""Deterministic feature importance — no ML-based importance."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from scanner.ml.label_store import LabelName


@dataclass
class ImportanceResult:
    feature: str
    correlation_win_rate: float | None = None
    correlation_r_multiple: float | None = None
    mean_diff_winners_losers: float | None = None
    statistical_importance: float | None = None
    mutual_information: float | None = None
    information_gain: float | None = None
    sample_size: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "correlation_win_rate": self.correlation_win_rate,
            "correlation_r_multiple": self.correlation_r_multiple,
            "mean_diff_winners_losers": self.mean_diff_winners_losers,
            "statistical_importance": self.statistical_importance,
            "mutual_information": self.mutual_information,
            "information_gain": self.information_gain,
            "sample_size": self.sample_size,
            "notes": list(self.notes),
        }


class FeatureImportanceEngine:
    """Compute explainable, deterministic importance indicators."""

    def compute(self, rows: list[dict[str, Any]], *,
                feature_names: list[str] | None = None) -> list[ImportanceResult]:
        if not rows:
            return []
        features = feature_names or self._discover_features(rows)
        results: list[ImportanceResult] = []
        for feat in features:
            results.append(self._compute_one(feat, rows))
        return results

    def _compute_one(self, feature: str, rows: list[dict]) -> ImportanceResult:
        pairs = self._extract_pairs(feature, rows)
        numeric_vals = [v for v, _ in pairs if v is not None]
        wins = [w for _, w in pairs if w is not None]
        r_mults = [self._r_multiple(row) for row in rows
                   if self._feature_val(row, feature) is not None]

        notes: list[str] = []
        if len(numeric_vals) < 5:
            notes.append("Insufficient sample size (n<5)")

        corr_wr = self._correlation_win_rate(pairs)
        corr_r = self._correlation_r_multiple(feature, rows)
        mean_diff = self._mean_diff_winners_losers(feature, rows)
        stat_imp = self._statistical_importance(corr_wr, corr_r, mean_diff)

        return ImportanceResult(
            feature=feature,
            correlation_win_rate=corr_wr,
            correlation_r_multiple=corr_r,
            mean_diff_winners_losers=mean_diff,
            statistical_importance=stat_imp,
            mutual_information=self._mutual_information_placeholder(feature, rows),
            information_gain=self._information_gain_placeholder(feature, rows),
            sample_size=len(numeric_vals),
            notes=notes,
        )

    def _extract_pairs(self, feature: str, rows: list[dict]) -> list[tuple[float | None, int | None]]:
        pairs: list[tuple[float | None, int | None]] = []
        for row in rows:
            val = self._feature_val(row, feature)
            win = row.get(LabelName.BINARY_WIN.value)
            if win is None:
                win = row.get(LabelName.WINNER.value)
            if val is not None and win is not None:
                pairs.append((float(val), int(win)))
        return pairs

    def _correlation_win_rate(self, pairs: list[tuple[float | None, int | None]]) -> float | None:
        vals = [(v, w) for v, w in pairs if v is not None and w is not None]
        if len(vals) < 5:
            return None
        xs = [v for v, _ in vals]
        ys = [float(w) for _, w in vals]
        return _pearson(xs, ys)

    def _correlation_r_multiple(self, feature: str, rows: list[dict]) -> float | None:
        pairs = []
        for row in rows:
            v = self._feature_val(row, feature)
            r = self._r_multiple(row)
            if v is not None and r is not None:
                pairs.append((float(v), float(r)))
        if len(pairs) < 5:
            return None
        return _pearson([p[0] for p in pairs], [p[1] for p in pairs])

    def _mean_diff_winners_losers(self, feature: str, rows: list[dict]) -> float | None:
        winners = [self._feature_val(r, feature) for r in rows
                   if r.get(LabelName.WINNER.value) == 1]
        losers = [self._feature_val(r, feature) for r in rows
                  if r.get(LabelName.LOSER.value) == 1]
        winners = [float(v) for v in winners if v is not None]
        losers = [float(v) for v in losers if v is not None]
        if not winners or not losers:
            return None
        return round(sum(winners) / len(winners) - sum(losers) / len(losers), 4)

    def _statistical_importance(self, corr_wr: float | None, corr_r: float | None,
                                mean_diff: float | None) -> float | None:
        """Composite deterministic score from available signals."""
        parts: list[float] = []
        if corr_wr is not None:
            parts.append(abs(corr_wr))
        if corr_r is not None:
            parts.append(abs(corr_r))
        if mean_diff is not None:
            parts.append(min(abs(mean_diff) / 10.0, 1.0))
        if not parts:
            return None
        return round(sum(parts) / len(parts), 4)

    @staticmethod
    def _mutual_information_placeholder(feature: str, rows: list[dict]) -> float | None:
        """Placeholder — requires binning; deferred to ML training sprint."""
        return None

    @staticmethod
    def _information_gain_placeholder(feature: str, rows: list[dict]) -> float | None:
        """Placeholder — requires entropy computation; deferred to ML training sprint."""
        return None

    @staticmethod
    def _feature_val(row: dict, feature: str) -> Any:
        if feature in row:
            return row[feature]
        feats = row.get("features") or {}
        return feats.get(feature)

    @staticmethod
    def _r_multiple(row: dict) -> float | None:
        r = row.get(LabelName.R_MULTIPLE.value)
        if r is None:
            r = row.get("r_multiple")
        if r is None:
            labels = row.get("labels") or {}
            r = labels.get(LabelName.R_MULTIPLE.value)
        return float(r) if r is not None else None

    @staticmethod
    def _discover_features(rows: list[dict]) -> list[str]:
        skip = {LabelName.WINNER.value, LabelName.LOSER.value, LabelName.BREAK_EVEN.value,
                LabelName.R_MULTIPLE.value, LabelName.BINARY_WIN.value,
                LabelName.OUTCOME_CLASS.value,
                "event_id", "snapshot_id", "_meta", "_missing_features",
                "status", "r_multiple", "labels", "meta"}
        names: set[str] = set()
        for row in rows:
            if "features" in row:
                names.update(row["features"].keys())
            names.update(k for k in row if k not in skip and not k.startswith("label_")
                           and not k.startswith("_"))
        return sorted(names)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return round(num / (den_x * den_y), 4)
