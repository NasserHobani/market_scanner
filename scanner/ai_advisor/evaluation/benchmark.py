# -*- coding: utf-8 -*-
"""Provider benchmark — compare A vs B on the same Decision Package."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from scanner.tracking import wilson

EVALUATION_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _two_proportion_z(n1: int, x1: int, n2: int, x2: int) -> float | None:
    """Two-proportion z-test for statistical confidence."""
    if n1 < 2 or n2 < 2:
        return None
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    return (p1 - p2) / se


def _confidence_from_z(z: float | None) -> str:
    if z is None:
        return "insufficient_data"
    az = abs(z)
    if az >= 2.576:
        return "99%"
    if az >= 1.96:
        return "95%"
    if az >= 1.645:
        return "90%"
    return "not_significant"


class ProviderBenchmark:
    """Compare two providers on shared decision packages."""

    def compare(self, records: list[dict[str, Any]], *,
                provider_a: str, provider_b: str) -> dict[str, Any]:
        by_pkg: dict[str, dict[str, dict]] = {}
        for r in records:
            pkg_id = r.get("decision_package_id", "")
            if not pkg_id:
                continue
            provider = r.get("provider", "")
            if provider not in (provider_a, provider_b):
                continue
            by_pkg.setdefault(pkg_id, {})[provider] = r

        paired_a: list[dict] = []
        paired_b: list[dict] = []
        for pkg_records in by_pkg.values():
            if provider_a in pkg_records and provider_b in pkg_records:
                paired_a.append(pkg_records[provider_a])
                paired_b.append(pkg_records[provider_b])

        n = len(paired_a)
        correct_a = sum(1 for r in paired_a if r.get("advisor_correct"))
        correct_b = sum(1 for r in paired_b if r.get("advisor_correct"))
        hall_a = sum(1 for r in paired_a if r.get("hallucination"))
        hall_b = sum(1 for r in paired_b if r.get("hallucination"))
        useful_a = sum(1 for r in paired_a if r.get("useful_warning"))
        useful_b = sum(1 for r in paired_b if r.get("useful_warning"))

        acc_a = correct_a / n * 100 if n else 0
        acc_b = correct_b / n * 100 if n else 0
        z = _two_proportion_z(n, correct_a, n, correct_b)

        if acc_a > acc_b:
            winner = provider_a
        elif acc_b > acc_a:
            winner = provider_b
        else:
            winner = "tie"

        lo_a, hi_a = wilson(correct_a, n) if n else (0, 0)
        lo_b, hi_b = wilson(correct_b, n) if n else (0, 0)

        return {
            "provider_a": provider_a,
            "provider_b": provider_b,
            "paired_packages": n,
            "winner": winner,
            "metric_differences": {
                "accuracy": round(acc_a - acc_b, 1),
                "hallucination_rate": round(
                    (hall_a / n * 100 if n else 0) - (hall_b / n * 100 if n else 0), 1,
                ),
                "useful_warnings": useful_a - useful_b,
            },
            "provider_a_metrics": {
                "accuracy": round(acc_a, 1),
                "accuracy_ci": [lo_a, hi_a],
                "hallucination_rate": round(hall_a / n * 100, 1) if n else None,
                "useful_warnings": useful_a,
            },
            "provider_b_metrics": {
                "accuracy": round(acc_b, 1),
                "accuracy_ci": [lo_b, hi_b],
                "hallucination_rate": round(hall_b / n * 100, 1) if n else None,
                "useful_warnings": useful_b,
            },
            "statistical_confidence": _confidence_from_z(z),
            "z_score": round(z, 3) if z is not None else None,
            "benchmark_version": EVALUATION_VERSION,
            "generated_at": _now(),
        }
