# -*- coding: utf-8 -*-
"""Build prediction datasets from closed trades — no look-ahead bias."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner.ml.label_store import LabelName
from scanner.tracking import LOST, WON

from .feature_registry import (
    FEATURE_VERSION_V1,
    FEATURE_VERSION_V2,
    V1_COLUMNS,
    V2_COLUMNS,
    columns_for_version,
)

DATASET_REGISTRY = Path("data/predictive/datasets/registry.jsonl")

# Pre-decision features only — never include outcome fields as inputs.
FEATURE_COLUMNS = list(V1_COLUMNS)
FEATURE_COLUMNS_V2 = list(V2_COLUMNS)
DEFAULT_FEATURE_VERSION = FEATURE_VERSION_V2

LEAKAGE_FIELDS = frozenset({
    "r_multiple", "status", "closed_at", "exit_price", "entry_price",
    "bars_held", "best_r", "worst_r", "resolution_note",
    LabelName.BINARY_WIN.value, LabelName.WINNER.value, LabelName.LOSER.value,
})

GRADE_MAP = {"A": 3, "B": 2, "C": 1, "—": 0, "-": 0, "": 0}
TF_MAP = {"4h": 1, "1h": 2, "1d": 3, "15m": 4, "30m": 5, "1w": 6}
MARKET_MAP = {"crypto": 1, "forex": 2, "stocks": 3, "commodities": 4}
FACTOR_KEYS = ("htf", "confluence", "sweep", "breakout")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_dataset_id() -> str:
    return f"ds_{uuid.uuid4().hex[:16]}"


def _normalize_factors(factors: list | None) -> set[str]:
    out: set[str] = set()
    for f in factors or []:
        key = str(f).lower().replace(" ", "_")
        for k in FACTOR_KEYS:
            if k in key:
                out.add(k)
    return out


def _encode_trade_row(trade: dict[str, Any]) -> dict[str, Any] | None:
    """Extract pre-decision features + labels from a trade dict."""
    status = trade.get("status")
    if status not in (WON, LOST, "won", "lost"):
        return None
    score = trade.get("score")
    if score is None:
        return None

    factors = _normalize_factors(trade.get("factors"))
    features = {
        "score": float(score),
        "confidence": float(trade.get("confidence") or 0.0),
        "rr": float(trade.get("rr") or 0.0),
        "grade_enc": float(GRADE_MAP.get(str(trade.get("grade") or "—"), 0)),
        "factor_htf": 1.0 if "htf" in factors else 0.0,
        "factor_confluence": 1.0 if "confluence" in factors else 0.0,
        "factor_sweep": 1.0 if "sweep" in factors else 0.0,
        "factor_breakout": 1.0 if "breakout" in factors else 0.0,
        "market_enc": float(MARKET_MAP.get(str(trade.get("market") or "").lower(), 0)),
        "timeframe_enc": float(TF_MAP.get(str(trade.get("timeframe") or "").lower(), 0)),
        "side_buy": 1.0 if str(trade.get("side") or "buy").lower() == "buy" else 0.0,
    }

    r_mult = trade.get("r_multiple")
    is_win = status in (WON, "won") or (r_mult is not None and float(r_mult) > 0)
    labels = {
        LabelName.BINARY_WIN.value: 1 if is_win else 0,
        LabelName.R_MULTIPLE.value: float(r_mult) if r_mult is not None else 0.0,
    }

    return {
        "trade_id": str(trade.get("trade_id") or trade.get("pk") or ""),
        "event_id": trade.get("event_id") or "",
        "signal_at": str(trade.get("signal_at") or ""),
        "features": features,
        **features,
        **labels,
        "labels": labels,
        "_meta": {
            "symbol": trade.get("symbol"),
            "market": trade.get("market"),
            "timeframe": trade.get("timeframe"),
            "status": trade.get("status"),
            "feature_snapshot_id": trade.get("feature_snapshot_id") or "",
        },
    }


def _encode_row(trade: dict[str, Any], *, feature_version: str) -> dict[str, Any] | None:
    if feature_version == FEATURE_VERSION_V2:
        from .feature_engineering import encode_trade_row_v2
        return encode_trade_row_v2(trade)
    return _encode_trade_row(trade)


def build_from_trade_dicts(trades: list[dict[str, Any]], *,
                           dataset_id: str | None = None,
                           feature_version: str = DEFAULT_FEATURE_VERSION,
                           validate_leakage: bool = True) -> dict[str, Any]:
    """Build versioned dataset manifest + training rows from trade dicts."""
    did = dataset_id or new_dataset_id()
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for trade in trades:
        row = _encode_row(trade, feature_version=feature_version)
        if row:
            eligible.append(row)
        else:
            tid = str(trade.get("trade_id") or trade.get("pk") or "?")
            reason = "missing_score" if trade.get("score") is None else "not_closed"
            rejected.append({"trade_id": tid, "reason": reason})

    eligible.sort(key=lambda r: r.get("signal_at") or "")

    if feature_version == FEATURE_VERSION_V2:
        from .feature_engineering import add_point_in_time_history
        eligible = add_point_in_time_history(eligible)

    leakage_report = {"passed": True, "rows_checked": len(eligible)}
    if validate_leakage and eligible:
        from .leakage_detector import validate_dataset
        leakage_report = validate_dataset(
            eligible, feature_version=feature_version, fail_loud=True)

    cols = columns_for_version(feature_version)
    symbols = sorted({r["_meta"]["symbol"] for r in eligible if r["_meta"].get("symbol")})
    timeframes = sorted({r["_meta"]["timeframe"] for r in eligible if r["_meta"].get("timeframe")})
    dates = [r["signal_at"][:10] for r in eligible if r.get("signal_at")]
    date_range = {"start": dates[0], "end": dates[-1]} if dates else {}

    schema_hash = hashlib.sha256(
        json.dumps(cols, sort_keys=True).encode(),
    ).hexdigest()[:16]

    fingerprint = hashlib.sha256(
        json.dumps(
            [{"t": r["trade_id"], "s": r["signal_at"], "v": feature_version} for r in eligible],
            sort_keys=True,
        ).encode(),
    ).hexdigest()[:24]

    manifest = {
        "dataset_id": did,
        "dataset_version": feature_version,
        "created_at": _now(),
        "feature_schema": {
            "columns": cols,
            "feature_version": feature_version,
            "feature_schema_hash": f"fsh_{schema_hash}",
            "leakage_excluded": sorted(LEAKAGE_FIELDS),
            "source": "pre_trade_trade_fields+snapshots+history" if feature_version == FEATURE_VERSION_V2
                      else "pre_trade_trade_fields",
        },
        "label_definition": {
            "primary": LabelName.BINARY_WIN.value,
            "description": "1 if status=WON or r_multiple > 0, else 0",
            "deterministic": True,
            "source_layer": "tracking",
        },
        "leakage_validation": leakage_report,
        "sample_count": len(eligible),
        "rejected_count": len(rejected),
        "rejection_reasons": _count_reasons(rejected),
        "symbols": symbols,
        "timeframes": timeframes,
        "date_range": date_range,
        "fingerprint": f"dsfp_{fingerprint}",
        "rows": eligible,
    }
    return manifest


def _count_reasons(rejected: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in rejected:
        reason = r.get("reason", "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return counts


def chronological_split(rows: list[dict[str, Any]], *,
                        train_ratio: float = 0.7,
                        val_ratio: float = 0.15) -> dict[str, list[dict[str, Any]]]:
    """Chronological split — no random shuffle."""
    n = len(rows)
    if n == 0:
        return {"train": [], "validation": [], "test": []}
    train_end = max(1, int(n * train_ratio))
    val_end = max(train_end + 1, int(n * (train_ratio + val_ratio)))
    return {
        "train": rows[:train_end],
        "validation": rows[train_end:val_end],
        "test": rows[val_end:],
    }


def persist_dataset_manifest(manifest: dict[str, Any]) -> str:
    DATASET_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    record = {k: v for k, v in manifest.items() if k != "rows"}
    record["row_count"] = manifest.get("sample_count", 0)
    with DATASET_REGISTRY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    return manifest["dataset_id"]


def load_trades_from_django() -> list[dict[str, Any]]:
    """Load closed trades with pre-decision fields from Django."""
    try:
        from dashboard.models import Trade
    except ImportError:
        from web.dashboard.models import Trade

    from scanner.tracking import WON as W, LOST as L
    qs = Trade.objects.filter(status__in=[W, L]).order_by("signal_at")
    rows = []
    for t in qs:
        rows.append({
            "trade_id": str(t.pk),
            "symbol": t.symbol,
            "market": t.market,
            "timeframe": t.timeframe,
            "side": t.side,
            "status": t.status,
            "score": t.score,
            "confidence": t.confidence,
            "rr": t.rr,
            "grade": t.grade,
            "factors": list(t.factors or []),
            "r_multiple": t.r_multiple,
            "signal_at": t.signal_at.isoformat() if t.signal_at else "",
            "feature_snapshot_id": t.feature_snapshot_id or "",
            "pit_snapshot_id": getattr(t, "pit_snapshot_id", "") or "",
            "recommendation_id": getattr(t, "recommendation_id", "") or "",
            "decision_timestamp": (
                t.decision_timestamp.isoformat()
                if getattr(t, "decision_timestamp", None) else ""
            ),
            "feature_version": getattr(t, "feature_version", "") or "",
        })
    return rows


@dataclass
class DatasetBuildResult:
    manifest: dict[str, Any]
    eligible_count: int = 0
    rejected_count: int = 0
    reason: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        m = self.manifest
        return {
            "dataset_id": m.get("dataset_id", ""),
            "sample_count": m.get("sample_count", 0),
            "eligible": self.eligible_count,
            "rejected": self.rejected_count,
            "reason": self.reason,
            "fingerprint": m.get("fingerprint", ""),
            "label_definition": m.get("label_definition", {}),
            "feature_schema": m.get("feature_schema", {}),
            "date_range": m.get("date_range", {}),
            "rejection_reasons": m.get("rejection_reasons", {}),
        }
