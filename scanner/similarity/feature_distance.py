# -*- coding: utf-8 -*-
"""Deterministic feature distance — no ML, fully configurable."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DistanceConfig:
    """Explicit weights — no hidden calculations."""

    numerical_weight: float = 1.0
    boolean_weight: float = 1.0
    categorical_weight: float = 1.0
    missing_penalty: float = 0.5
    max_numerical_delta: float = 100.0

    def to_dict(self) -> dict[str, float]:
        return {
            "numerical_weight": self.numerical_weight,
            "boolean_weight": self.boolean_weight,
            "categorical_weight": self.categorical_weight,
            "missing_penalty": self.missing_penalty,
            "max_numerical_delta": self.max_numerical_delta,
        }


@dataclass
class FeatureDistance:
    """Distance result with per-feature breakdown."""

    distance: float
    similarity: float
    matched: list[str] = field(default_factory=list)
    different: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    details: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "distance": round(self.distance, 4),
            "similarity": round(self.similarity, 4),
            "matched": list(self.matched),
            "different": list(self.different),
            "missing": list(self.missing),
            "details": dict(self.details),
        }


def _is_missing(value: Any) -> bool:
    return value is None or value == "" or value == "—"


def _numerical_distance(a: float, b: float, *, max_delta: float) -> float:
    return min(1.0, abs(a - b) / max_delta)


def _categorical_distance(a: Any, b: Any) -> float:
    return 0.0 if str(a) == str(b) else 1.0


def _boolean_distance(a: Any, b: Any) -> float:
    return 0.0 if bool(a) == bool(b) else 1.0


class FeatureDistanceCalculator:
    """Compare two feature payloads deterministically."""

    def __init__(self, config: DistanceConfig | None = None) -> None:
        self.config = config or DistanceConfig()

    def compare(self, query: dict[str, Any],
                candidate: dict[str, Any]) -> FeatureDistance:
        q_features = self._extract_features(query)
        c_features = self._extract_features(candidate)
        all_keys = sorted(set(q_features) | set(c_features))

        matched: list[str] = []
        different: list[str] = []
        missing: list[str] = []
        details: dict[str, dict[str, Any]] = {}
        total_weight = 0.0
        total_distance = 0.0

        for key in all_keys:
            qv = q_features.get(key)
            cv = c_features.get(key)
            q_miss = _is_missing(qv)
            c_miss = _is_missing(cv)

            if q_miss and c_miss:
                missing.append(key)
                dist = self.config.missing_penalty
                weight = self.config.numerical_weight
                kind = "missing"
            elif q_miss or c_miss:
                missing.append(key)
                dist = self.config.missing_penalty
                weight = self.config.numerical_weight
                kind = "partial_missing"
            elif isinstance(qv, bool) or isinstance(cv, bool):
                dist = _boolean_distance(qv, cv)
                weight = self.config.boolean_weight
                kind = "boolean"
            elif isinstance(qv, (int, float)) and isinstance(cv, (int, float)):
                dist = _numerical_distance(float(qv), float(cv),
                                           max_delta=self.config.max_numerical_delta)
                weight = self.config.numerical_weight
                kind = "numerical"
            else:
                dist = _categorical_distance(qv, cv)
                weight = self.config.categorical_weight
                kind = "categorical"

            if dist == 0.0 and not (q_miss or c_miss):
                matched.append(key)
            elif not (q_miss and c_miss):
                different.append(key)

            details[key] = {
                "kind": kind,
                "query": qv,
                "candidate": cv,
                "distance": round(dist, 4),
                "weight": weight,
            }
            total_distance += dist * weight
            total_weight += weight

        overall = total_distance / total_weight if total_weight else 1.0
        return FeatureDistance(
            distance=overall,
            similarity=max(0.0, 1.0 - overall),
            matched=matched,
            different=different,
            missing=missing,
            details=details,
        )

    def _extract_features(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Flatten feature snapshot or scan source into comparable features."""
        out: dict[str, Any] = {}

        registry = payload.get("feature_registry") or {}
        for name, entry in registry.items():
            if isinstance(entry, dict):
                out[name] = entry.get("value")
            else:
                out[name] = entry

        for name, val in (payload.get("raw_components") or {}).items():
            out[f"c_{name}"] = val

        groups = payload.get("groups") or {}
        trend = groups.get("trend") or {}
        out["htf_bias"] = out.get("htf_bias") or trend.get("htf_bias") or payload.get("htf")
        out["rsi"] = out.get("rsi") or (groups.get("momentum") or {}).get("rsi")
        out["rvol"] = out.get("rvol") or (groups.get("volume") or {}).get("rvol")

        scoring = groups.get("scoring") or {}
        out["score"] = out.get("score") or scoring.get("score") or payload.get("score")
        out["ready"] = scoring.get("ready", payload.get("ready"))

        structure = groups.get("market_structure") or {}
        out["bos"] = bool(structure.get("bos"))
        out["choch"] = bool(structure.get("choch"))

        liquidity = groups.get("liquidity") or {}
        out["liquidity_class"] = liquidity.get("class") or payload.get("liquidity")
        out["sweep_count"] = len(liquidity.get("sweeps") or [])

        patterns = groups.get("patterns") or {}
        out["pattern_count"] = len(patterns.get("chart_patterns") or [])
        out["candle_count"] = len(patterns.get("candlestick") or [])

        out["final_grade"] = payload.get("final_grade") or payload.get("grade")
        out["final_score"] = payload.get("final_score") or payload.get("score")

        ctx = payload.get("context") or payload.get("score_context") or {}
        if "atr_pct" not in out:
            out["atr_pct"] = ctx.get("atr_pct") or payload.get("atr_pct")

        return {k: v for k, v in out.items() if not _is_missing(v) or k in out}
