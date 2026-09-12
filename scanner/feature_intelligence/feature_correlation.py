# -*- coding: utf-8 -*-
"""Feature correlation analysis — feature vs feature, outcome, strategy."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner.ml.label_store import LabelName

from .feature_importance import _pearson


@dataclass
class CorrelationMatrix:
    features: list[str]
    matrix: dict[str, dict[str, float | None]] = field(default_factory=dict)
    outcome_correlations: dict[str, float | None] = field(default_factory=dict)
    strategy_correlations: dict[str, dict[str, float | None]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": list(self.features),
            "matrix": self.matrix,
            "outcome_correlations": self.outcome_correlations,
            "strategy_correlations": self.strategy_correlations,
        }


@dataclass
class CorrelationPair:
    feature_a: str
    feature_b: str
    correlation: float | None
    pair_type: str = "feature_vs_feature"

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_a": self.feature_a,
            "feature_b": self.feature_b,
            "correlation": self.correlation,
            "pair_type": self.pair_type,
        }


class FeatureCorrelationEngine:
    """Analyze correlations between features, outcomes, and strategies."""

    def compute_matrix(self, rows: list[dict[str, Any]], *,
                       feature_names: list[str] | None = None) -> CorrelationMatrix:
        features = feature_names or _discover_features(rows)
        matrix: dict[str, dict[str, float | None]] = {}
        for fa in features:
            matrix[fa] = {}
            for fb in features:
                if fa == fb:
                    matrix[fa][fb] = 1.0
                elif fb in matrix and fa in matrix.get(fb, {}):
                    matrix[fa][fb] = matrix[fb][fa]
                else:
                    matrix[fa][fb] = self._pair_correlation(fa, fb, rows)

        outcome_corr = {
            f: self._outcome_correlation(f, rows) for f in features
        }
        strategy_corr = self._strategy_correlations(features, rows)

        return CorrelationMatrix(
            features=features,
            matrix=matrix,
            outcome_correlations=outcome_corr,
            strategy_correlations=strategy_corr,
        )

    def pair_correlations(self, rows: list[dict], *,
                          feature_names: list[str] | None = None,
                          min_abs: float = 0.0) -> list[CorrelationPair]:
        features = feature_names or _discover_features(rows)
        pairs: list[CorrelationPair] = []
        for i, fa in enumerate(features):
            for fb in features[i + 1:]:
                corr = self._pair_correlation(fa, fb, rows)
                if corr is not None and abs(corr) >= min_abs:
                    pairs.append(CorrelationPair(fa, fb, corr))
        pairs.sort(key=lambda p: abs(p.correlation or 0), reverse=True)
        return pairs

    def _pair_correlation(self, fa: str, fb: str, rows: list[dict]) -> float | None:
        pairs: list[tuple[float, float]] = []
        for row in rows:
            a = _feature_val(row, fa)
            b = _feature_val(row, fb)
            if a is not None and b is not None and isinstance(a, (int, float)) and isinstance(b, (int, float)):
                pairs.append((float(a), float(b)))
        if len(pairs) < 5:
            return None
        return _pearson([p[0] for p in pairs], [p[1] for p in pairs])

    def _outcome_correlation(self, feature: str, rows: list[dict]) -> float | None:
        pairs: list[tuple[float, float]] = []
        for row in rows:
            v = _feature_val(row, feature)
            r = row.get(LabelName.R_MULTIPLE.value) or row.get("r_multiple")
            if r is None:
                labels = row.get("labels") or {}
                r = labels.get(LabelName.R_MULTIPLE.value)
            if v is not None and r is not None and isinstance(v, (int, float)):
                pairs.append((float(v), float(r)))
        if len(pairs) < 5:
            return None
        return _pearson([p[0] for p in pairs], [p[1] for p in pairs])

    def _strategy_correlations(self, features: list[str],
                               rows: list[dict]) -> dict[str, dict[str, float | None]]:
        strategies: dict[str, list[dict]] = {}
        for row in rows:
            strat = _meta_val(row, "strategy") or _meta_val(row, "source") or "default"
            strategies.setdefault(str(strat), []).append(row)
        if len(strategies) < 2:
            return {}
        out: dict[str, dict[str, float | None]] = {}
        for strat, srows in strategies.items():
            out[strat] = {f: self._outcome_correlation(f, srows) for f in features}
        return out


def _feature_val(row: dict, feature: str) -> Any:
    if feature in row:
        return row[feature]
    return (row.get("features") or {}).get(feature)


def _meta_val(row: dict, key: str) -> Any:
    meta = row.get("_meta") or row.get("meta") or {}
    return meta.get(key) or row.get(key)


def _discover_features(rows: list[dict]) -> list[str]:
    from .feature_importance import FeatureImportanceEngine
    return FeatureImportanceEngine._discover_features(rows)
