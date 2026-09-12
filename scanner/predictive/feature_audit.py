# -*- coding: utf-8 -*-
"""Feature audit report — distributions, missing rates, leakage risk."""
from __future__ import annotations

import statistics
from collections import Counter
from typing import Any

from .feature_registry import FeatureSpec, specs_for_version


def audit_features(rows: list[dict[str, Any]], *,
                   version: str = "2.0.0") -> dict[str, Any]:
    specs = specs_for_version(version)
    report_rows: list[dict[str, Any]] = []

    for spec in specs:
        vals = []
        for row in rows:
            feats = row.get("features") or row
            v = feats.get(spec.name)
            if v is not None:
                vals.append(v)

        n = len(rows)
        missing = n - len(vals)
        missing_rate = round(missing / n, 4) if n else 0.0
        uniq = len(set(vals)) if vals else 0

        numeric_vals = [float(v) for v in vals if isinstance(v, (int, float))]
        dist: dict[str, Any] = {}
        if numeric_vals:
            dist = {
                "min": round(min(numeric_vals), 4),
                "max": round(max(numeric_vals), 4),
                "mean": round(statistics.mean(numeric_vals), 4),
                "stdev": round(statistics.pstdev(numeric_vals), 4) if len(numeric_vals) > 1 else 0,
            }
            if uniq <= 10:
                dist["value_counts"] = dict(Counter(numeric_vals))

        status = "active"
        if missing_rate > 0.5:
            status = "sparse"
        if uniq <= 1 and numeric_vals:
            status = "CONSTANT"
            dist["note"] = "zero variance — rejected for V3"

        report_rows.append({
            **spec.to_dict(),
            "availability": round(1 - missing_rate, 4),
            "missing_rate": missing_rate,
            "unique_values": uniq,
            "distribution": dist,
            "importance": None,
            "status": status,
        })

    useless = [r["feature"] for r in report_rows if r["status"] in ("constant", "CONSTANT")]
    return {
        "feature_version": version,
        "row_count": len(rows),
        "features": report_rows,
        "useless_features": useless,
        "rejected_constant": useless,
        "active_feature_count": sum(1 for r in report_rows if r["status"] == "active"),
    }


def audit_features_v3(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """V3 audit with explicit classification statuses."""
    from .feature_registry import FEATURE_VERSION_V3

    base = audit_features(rows, version=FEATURE_VERSION_V3)
    for feat in base["features"]:
        avail = feat.get("availability", 0)
        if avail < 0.2:
            feat["status"] = "LOW_COVERAGE"
        elif feat["status"] == "CONSTANT":
            feat["status"] = "CONSTANT"
        elif feat.get("missing_rate", 0) > 0.8:
            feat["status"] = "HIGH_MISSING"
        elif avail >= 0.2:
            feat["status"] = "ACTIVE"
    base["classifications"] = {
        "ACTIVE": sum(1 for f in base["features"] if f["status"] == "ACTIVE"),
        "LOW_COVERAGE": sum(1 for f in base["features"] if f["status"] == "LOW_COVERAGE"),
        "CONSTANT": sum(1 for f in base["features"] if f["status"] == "CONSTANT"),
        "HIGH_MISSING": sum(1 for f in base["features"] if f["status"] == "HIGH_MISSING"),
    }
    return base
