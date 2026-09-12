# -*- coding: utf-8 -*-
"""Pre-trade feature engineering — snapshots + point-in-time historical context."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from scanner.tracking import LOST, WON

from .feature_registry import FEATURE_VERSION_V2, V2_COLUMNS
from .trade_dataset import (
    GRADE_MAP,
    MARKET_MAP,
    TF_MAP,
    _encode_trade_row,
    _normalize_factors,
)

LIQUIDITY_MAP = {"unknown": 0, "micro": 1, "low": 2, "mid": 3, "high": 4}
_SNAPSHOT_INDEX: dict[str, dict[str, Any]] | None = None


def _load_snapshot_index() -> dict[str, dict[str, Any]]:
    global _SNAPSHOT_INDEX
    if _SNAPSHOT_INDEX is not None:
        return _SNAPSHOT_INDEX
    index: dict[str, dict[str, Any]] = {}
    path = Path("data/features/snapshots.jsonl")
    if path.exists():
        import json
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                sid = row.get("snapshot_id", "")
                if sid:
                    index[sid] = row
            except json.JSONDecodeError:
                continue
    _SNAPSHOT_INDEX = index
    return index


def reset_snapshot_cache() -> None:
    global _SNAPSHOT_INDEX
    _SNAPSHOT_INDEX = None


def _snapshot_features(trade: dict[str, Any]) -> dict[str, float]:
    sid = trade.get("feature_snapshot_id") or ""
    snap = _load_snapshot_index().get(sid) if sid else None
    if not snap:
        return {
            "snap_available": 0.0,
            "snap_confluence": 0.0,
            "snap_htf": 0.0,
            "snap_score": 0.0,
            "snap_quote_volume": 0.0,
            "liquidity_enc": 0.0,
        }
    liq = str(snap.get("liquidity") or "unknown").lower()
    qv = snap.get("quote_volume")
    return {
        "snap_available": 1.0,
        "snap_confluence": float(snap.get("confluence") or 0),
        "snap_htf": float(snap.get("htf") or 0),
        "snap_score": float(snap.get("score") or 0),
        "snap_quote_volume": float(qv) if qv is not None else 0.0,
        "liquidity_enc": float(LIQUIDITY_MAP.get(liq, 0)),
    }


def _base_features(trade: dict[str, Any]) -> dict[str, float]:
    factors = _normalize_factors(trade.get("factors"))
    return {
        "score": float(trade.get("score") or 0),
        "confidence": float(trade.get("confidence") or 0),
        "rr": float(trade.get("rr") or 0),
        "grade_enc": float(GRADE_MAP.get(str(trade.get("grade") or "—"), 0)),
        "factor_htf": 1.0 if "htf" in factors else 0.0,
        "factor_confluence": 1.0 if "confluence" in factors else 0.0,
        "factor_sweep": 1.0 if "sweep" in factors else 0.0,
        "factor_breakout": 1.0 if "breakout" in factors else 0.0,
        "market_enc": float(MARKET_MAP.get(str(trade.get("market") or "").lower(), 0)),
        "timeframe_enc": float(TF_MAP.get(str(trade.get("timeframe") or "").lower(), 0)),
        "side_buy": 1.0 if str(trade.get("side") or "buy").lower() == "buy" else 0.0,
        "factor_count": float(len(factors)),
    }


def encode_trade_row_v2(trade: dict[str, Any]) -> dict[str, Any] | None:
    """Encode trade with v2 features — delegates labels to v1 encoder."""
    base = _encode_trade_row(trade)
    if not base:
        return None
    features = _base_features(trade)
    features.update(_snapshot_features(trade))
    # historical filled in batch pass
    for k in ("hist_win_rate_symbol", "hist_win_rate_tf",
              "hist_trade_count_symbol", "hist_expectancy_symbol"):
        features.setdefault(k, 0.0)

    base["features"] = features
    for k, v in features.items():
        base[k] = v
    base["feature_version"] = FEATURE_VERSION_V2
    base["feature_timestamp"] = str(trade.get("signal_at") or "")
    return base


def add_point_in_time_history(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add historical win-rate features using only PRIOR trades (chronological)."""
    sym_wins: dict[str, int] = {}
    sym_total: dict[str, int] = {}
    sym_r_sum: dict[str, float] = {}
    tf_wins: dict[str, int] = {}
    tf_total: dict[str, int] = {}

    for row in rows:
        sym = (row.get("_meta") or {}).get("symbol") or ""
        tf = (row.get("_meta") or {}).get("timeframe") or ""
        feats = row.get("features") or {}

        st = sym_total.get(sym, 0)
        feats["hist_trade_count_symbol"] = float(st)
        feats["hist_win_rate_symbol"] = round(sym_wins.get(sym, 0) / st, 4) if st else 0.0
        feats["hist_expectancy_symbol"] = round(sym_r_sum.get(sym, 0) / st, 4) if st else 0.0

        tt = tf_total.get(tf, 0)
        feats["hist_win_rate_tf"] = round(tf_wins.get(tf, 0) / tt, 4) if tt else 0.0

        row["features"] = feats
        for k, v in feats.items():
            row[k] = v

        label = int(row.get("label_binary_win") or 0)
        r_mult = float(row.get("label_r_multiple") or row.get("r_multiple") or 0)
        sym_total[sym] = st + 1
        sym_wins[sym] = sym_wins.get(sym, 0) + label
        sym_r_sum[sym] = sym_r_sum.get(sym, 0.0) + r_mult
        tf_total[tf] = tt + 1
        tf_wins[tf] = tf_wins.get(tf, 0) + label

    return rows


def get_feature_columns(version: str = FEATURE_VERSION_V2) -> list[str]:
    return list(V2_COLUMNS if version == FEATURE_VERSION_V2 else V2_COLUMNS[:11])
