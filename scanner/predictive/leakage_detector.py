# -*- coding: utf-8 -*-
"""Automated leakage detection for prediction datasets."""
from __future__ import annotations

from typing import Any

from scanner.ml.label_store import LabelName

from .feature_registry import columns_for_version
from .trade_dataset import LEAKAGE_FIELDS

FORBIDDEN_FEATURE_NAMES = frozenset(LEAKAGE_FIELDS | {
    "r_multiple", "closed_at", "exit_price", "entry_price", "bars_held",
    "evaluation_id", "advisor_correct", "hallucination", "failure_type",
    "claude_agreement", "review_id", "learning_lesson_id",
    LabelName.BINARY_WIN.value, LabelName.WINNER.value, LabelName.LOSER.value,
    LabelName.R_MULTIPLE.value, LabelName.OUTCOME_CLASS.value,
})

POST_TRADE_META_KEYS = frozenset({
    "closed_at", "exit_price", "entry_price", "resolution_note",
})


class LeakageError(Exception):
    """Raised when dataset contains look-ahead or outcome leakage."""


def validate_row_features(row: dict[str, Any], *,
                          feature_columns: list[str] | None = None,
                          decision_ts: str = "") -> list[str]:
    """Return list of leakage violations (empty = pass)."""
    violations: list[str] = []
    feats = row.get("features") or row
    feat_ts = str(row.get("feature_timestamp") or row.get("signal_at") or "")
    dec_ts = decision_ts or str(row.get("signal_at") or "")

    if feat_ts and dec_ts and feat_ts > dec_ts:
        violations.append(f"feature_timestamp {feat_ts} > decision {dec_ts}")

    for col in feature_columns or list(feats.keys()):
        if col in FORBIDDEN_FEATURE_NAMES:
            violations.append(f"forbidden feature column: {col}")

    for key in feats:
        if key in FORBIDDEN_FEATURE_NAMES:
            violations.append(f"forbidden feature key: {key}")

    meta = row.get("_meta") or {}
    for k in POST_TRADE_META_KEYS:
        if k in feats:
            violations.append(f"post-trade field in features: {k}")

    # Outcome must not appear in features dict
    label_keys = {LabelName.BINARY_WIN.value, "label_winner", "status"}
    for lk in label_keys:
        if lk in feats and lk != "status":
            violations.append(f"label leaked into features: {lk}")

    return violations


def validate_provenance(provenance: list[dict[str, Any]], *,
                        decision_ts: str) -> list[str]:
    """Ensure every feature source_timestamp <= decision_timestamp."""
    violations: list[str] = []
    if not provenance:
        violations.append("missing provenance")
        return violations
    for item in provenance:
        if not item.get("source"):
            violations.append(f"provenance missing source for {item.get('name')}")
        if not item.get("calculation_version"):
            violations.append(f"provenance missing calc version for {item.get('name')}")
        src_ts = str(item.get("source_timestamp") or "")
        if decision_ts and src_ts and src_ts > decision_ts:
            violations.append(
                f"future provenance {item.get('name')}: {src_ts} > {decision_ts}"
            )
    return violations


def adversarial_leakage_tests(base_row: dict[str, Any]) -> dict[str, bool]:
    """Inject future data patterns — all should fail validation."""
    tests: dict[str, bool] = {}
    future_ts = "2099-12-31T00:00:00+00:00"
    dec_ts = str(base_row.get("decision_timestamp") or base_row.get("signal_at") or "")

    scenarios = {
        "future_rsi": {"features": {"rsi": 99.0}, "provenance": [{
            "name": "rsi", "value": 99.0, "source": "momentum_engine",
            "source_timestamp": future_ts, "calculation_version": "rsi-v2",
        }]},
        "future_atr": {"features": {"atr_pct": 5.0}, "provenance": [{
            "name": "atr_pct", "value": 5.0, "source": "pine",
            "source_timestamp": future_ts, "calculation_version": "atr-v1",
        }]},
        "future_volume": {"features": {"rvol": 9.9}, "provenance": [{
            "name": "rvol", "value": 9.9, "source": "volume",
            "source_timestamp": future_ts, "calculation_version": "rvol-v1",
        }]},
        "future_bos": {"features": {"bos_count": 10.0}, "provenance": [{
            "name": "bos_count", "value": 10.0, "source": "structure",
            "source_timestamp": future_ts, "calculation_version": "struct-v1",
        }]},
        "future_similarity": {"features": {"historical_win_rate": 1.0}, "provenance": [{
            "name": "historical_win_rate", "value": 1.0, "source": "similarity",
            "source_timestamp": future_ts, "calculation_version": "sim-v1",
        }]},
        "future_outcome": {"features": {"score": 50.0}, LabelName.BINARY_WIN.value: 1},
    }

    for name, patch in scenarios.items():
        row = dict(base_row)
        feats = dict(row.get("features") or {})
        feats.update(patch.get("features") or {})
        row["features"] = feats
        if "provenance" in patch:
            row["provenance"] = patch["provenance"]
        if LabelName.BINARY_WIN.value in patch:
            feats[LabelName.BINARY_WIN.value] = patch[LabelName.BINARY_WIN.value]
        viols = validate_row_features(row, decision_ts=dec_ts)
        if patch.get("provenance"):
            viols.extend(validate_provenance(patch["provenance"], decision_ts=dec_ts))
        tests[name] = len(viols) > 0
    return tests


def validate_dataset(rows: list[dict[str, Any]], *,
                     feature_version: str = "2.0.0",
                     fail_loud: bool = True) -> dict[str, Any]:
    """Validate all rows; optionally raise LeakageError."""
    cols = columns_for_version(feature_version)
    all_violations: list[dict[str, Any]] = []
    for row in rows:
        viols = validate_row_features(row, feature_columns=cols,
                                      decision_ts=str(row.get("decision_timestamp") or row.get("signal_at") or ""))
        if feature_version.startswith("3"):
            viols.extend(validate_provenance(row.get("provenance") or [],
                                             decision_ts=str(row.get("decision_timestamp") or row.get("signal_at") or "")))
        if viols:
            all_violations.append({
                "trade_id": row.get("trade_id", ""),
                "violations": viols,
            })

    report = {
        "passed": len(all_violations) == 0,
        "rows_checked": len(rows),
        "violation_count": len(all_violations),
        "violations": all_violations[:20],
    }
    if fail_loud and all_violations:
        raise LeakageError(
            f"Leakage detected in {len(all_violations)} rows: "
            f"{all_violations[0]['violations']}"
        )
    return report


def inject_leakage_test_row(base_row: dict[str, Any]) -> dict[str, Any]:
    """Test helper — inject future outcome into features."""
    bad = dict(base_row)
    feats = dict(bad.get("features") or {})
    feats[LabelName.BINARY_WIN.value] = 1
    feats["r_multiple"] = 2.0
    bad["features"] = feats
    bad[LabelName.BINARY_WIN.value] = 1
    return bad
