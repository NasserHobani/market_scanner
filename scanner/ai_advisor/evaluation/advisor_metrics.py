# -*- coding: utf-8 -*-
"""Advisor metrics — every metric includes sample size and confidence interval."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from scanner.tracking import wilson

CALIBRATION_BUCKETS = [
    (50, 60), (60, 70), (70, 80), (80, 90), (90, 100),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rate_metric(correct: int, total: int) -> dict[str, Any]:
    if total == 0:
        return {"value": None, "sample_size": 0, "confidence_interval": [0.0, 0.0],
                "last_updated": _now()}
    lo, hi = wilson(correct, total)
    return {
        "value": round(correct / total * 100, 1),
        "sample_size": total,
        "confidence_interval": [lo, hi],
        "last_updated": _now(),
    }


class AdvisorMetrics:
    """Compute all advisor quality metrics from evaluation records."""

    def compute(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            return self._empty()

        n = len(records)
        correct = sum(1 for r in records if r.get("advisor_correct"))
        hallucinations = sum(1 for r in records if r.get("hallucination"))
        useful = sum(1 for r in records if r.get("useful_warning"))
        false_warn = sum(1 for r in records if r.get("false_warning"))
        missed = sum(1 for r in records if r.get("missed_warning"))
        agreements = sum(1 for r in records if r.get("advisor_agreement") == "agree")

        confidences = [float(r["advisor_confidence"]) for r in records
                       if r.get("advisor_confidence") is not None]
        avg_conf = round(sum(confidences) / len(confidences), 1) if confidences else None

        return {
            "overall_accuracy": _rate_metric(correct, n),
            "agreement_rate": _rate_metric(agreements, n),
            "useful_warnings": _rate_metric(useful, n),
            "false_warnings": _rate_metric(false_warn, n),
            "missed_warnings": _rate_metric(missed, n),
            "hallucination_rate": _rate_metric(hallucinations, n),
            "average_confidence": {
                "value": avg_conf,
                "sample_size": len(confidences),
                "confidence_interval": [None, None],
                "last_updated": _now(),
            },
            "confidence_calibration": self._calibration(records),
            "market_accuracy": self._group_accuracy(records, "market"),
            "timeframe_accuracy": self._group_accuracy(records, "timeframe"),
            "strategy_accuracy": self._group_accuracy(records, "strategy"),
            "trend_accuracy": self._group_accuracy(records, "trend"),
            "long_accuracy": self._direction_accuracy(records, "long"),
            "short_accuracy": self._direction_accuracy(records, "short"),
        }

    def _calibration(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets = []
        for lo, hi in CALIBRATION_BUCKETS:
            in_bucket = [
                r for r in records
                if r.get("advisor_confidence") is not None
                and lo <= float(r["advisor_confidence"]) < hi
            ]
            if not in_bucket:
                buckets.append({
                    "bucket": f"{lo}-{hi}%",
                    "expected_midpoint": (lo + hi) / 2,
                    "actual_accuracy": None,
                    "sample_size": 0,
                    "calibration_error": None,
                })
                continue
            correct = sum(1 for r in in_bucket if r.get("advisor_correct"))
            actual = round(correct / len(in_bucket) * 100, 1)
            expected = (lo + hi) / 2
            buckets.append({
                "bucket": f"{lo}-{hi}%",
                "expected_midpoint": expected,
                "actual_accuracy": actual,
                "sample_size": len(in_bucket),
                "calibration_error": round(actual - expected, 1),
            })
        return buckets

    def _group_accuracy(self, records: list[dict[str, Any]],
                        field: str) -> dict[str, Any]:
        groups: dict[str, list[dict]] = {}
        for r in records:
            key = str(r.get(field) or "unknown")
            groups.setdefault(key, []).append(r)

        out = {}
        for key, items in groups.items():
            correct = sum(1 for r in items if r.get("advisor_correct"))
            out[key] = _rate_metric(correct, len(items))
        return out

    def _direction_accuracy(self, records: list[dict[str, Any]],
                            direction: str) -> dict[str, Any]:
        filtered = [
            r for r in records
            if str(r.get("direction", "")).lower() == direction
            or (direction == "long" and str(r.get("direction", "")).lower() in ("buy", "long"))
            or (direction == "short" and str(r.get("direction", "")).lower() in ("sell", "short"))
        ]
        correct = sum(1 for r in filtered if r.get("advisor_correct"))
        return _rate_metric(correct, len(filtered))

    def _empty(self) -> dict[str, Any]:
        empty = _rate_metric(0, 0)
        return {
            "overall_accuracy": empty,
            "agreement_rate": empty,
            "useful_warnings": empty,
            "false_warnings": empty,
            "missed_warnings": empty,
            "hallucination_rate": empty,
            "average_confidence": {"value": None, "sample_size": 0,
                                   "confidence_interval": [0, 0], "last_updated": _now()},
            "confidence_calibration": [],
            "market_accuracy": {},
            "timeframe_accuracy": {},
            "strategy_accuracy": {},
            "trend_accuracy": {},
            "long_accuracy": empty,
            "short_accuracy": empty,
        }
