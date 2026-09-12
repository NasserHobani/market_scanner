# -*- coding: utf-8 -*-
"""Redundancy detection — highly correlated feature groups."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .feature_correlation import FeatureCorrelationEngine, CorrelationPair


@dataclass
class RedundancyGroup:
    features: list[str]
    max_correlation: float
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "features": list(self.features),
            "max_correlation": self.max_correlation,
            "warnings": list(self.warnings),
        }


@dataclass
class RedundancyResult:
    redundant_pairs: list[CorrelationPair] = field(default_factory=list)
    groups: list[RedundancyGroup] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "redundant_pairs": [p.to_dict() for p in self.redundant_pairs],
            "groups": [g.to_dict() for g in self.groups],
            "warnings": list(self.warnings),
        }


class RedundancyDetector:
    """Identify highly correlated and redundant features."""

    def __init__(self, correlation_engine: FeatureCorrelationEngine | None = None,
                 threshold: float = 0.85) -> None:
        self._corr = correlation_engine or FeatureCorrelationEngine()
        self._threshold = threshold

    def detect(self, rows: list[dict[str, Any]], *,
               feature_names: list[str] | None = None,
               threshold: float | None = None) -> RedundancyResult:
        thresh = threshold if threshold is not None else self._threshold
        pairs = self._corr.pair_correlations(rows, feature_names=feature_names,
                                             min_abs=thresh)
        redundant = [p for p in pairs if p.correlation is not None
                     and abs(p.correlation) >= thresh]

        groups = self._build_groups(redundant)
        warnings: list[str] = []
        for p in redundant:
            warnings.append(
                f"High correlation: {p.feature_a} ↔ {p.feature_b} "
                f"(r={p.correlation:.3f})"
            )
        for g in groups:
            if len(g.features) > 2:
                warnings.append(
                    f"Redundancy group: {', '.join(g.features)} "
                    f"(max r={g.max_correlation:.3f})"
                )

        return RedundancyResult(
            redundant_pairs=redundant,
            groups=groups,
            warnings=warnings,
        )

    def _build_groups(self, pairs: list[CorrelationPair]) -> list[RedundancyGroup]:
        """Union-find style grouping of correlated features."""
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            parent.setdefault(x, x)
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        max_corr: dict[str, float] = {}
        for p in pairs:
            if p.correlation is None:
                continue
            union(p.feature_a, p.feature_b)
            key = f"{p.feature_a}|{p.feature_b}"
            max_corr[key] = abs(p.correlation)

        clusters: dict[str, set[str]] = {}
        for p in pairs:
            root = find(p.feature_a)
            clusters.setdefault(root, set()).update([p.feature_a, p.feature_b])

        groups: list[RedundancyGroup] = []
        for members in clusters.values():
            if len(members) < 2:
                continue
            feats = sorted(members)
            mc = max(
                (abs(p.correlation or 0) for p in pairs
                 if p.feature_a in members and p.feature_b in members),
                default=0.0,
            )
            groups.append(RedundancyGroup(
                features=feats,
                max_correlation=round(mc, 4),
                warnings=[f"Consider removing redundant features from: {', '.join(feats)}"],
            ))
        return groups
