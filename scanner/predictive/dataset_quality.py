# -*- coding: utf-8 -*-
"""Dataset quality report."""
from __future__ import annotations

from collections import Counter
from typing import Any


def dataset_quality_report(manifest: dict[str, Any]) -> dict[str, Any]:
    rows = manifest.get("rows") or []
    labels = [int(r.get("label_binary_win") or 0) for r in rows]
    pos = sum(labels)
    neg = len(labels) - pos

    symbols = Counter((r.get("_meta") or {}).get("symbol") for r in rows)
    timeframes = Counter((r.get("_meta") or {}).get("timeframe") for r in rows)
    dates = [r.get("signal_at", "")[:10] for r in rows if r.get("signal_at")]

    dup_ids = [tid for tid, c in Counter(r.get("trade_id") for r in rows).items() if c > 1]

    top_symbol = symbols.most_common(1)[0] if symbols else ("", 0)
    concentration_warning = ""
    if top_symbol[1] > len(rows) * 0.15:
        concentration_warning = (
            f"Dataset dominated by {top_symbol[0]} ({top_symbol[1]}/{len(rows)} trades)"
        )

    tf_top = timeframes.most_common(1)[0] if timeframes else ("", 0)
    if tf_top[1] > len(rows) * 0.6:
        concentration_warning += (
            f"; timeframe {tf_top[0]} is {tf_top[1]}/{len(rows)}"
        )

    snap_avail = sum(
        1 for r in rows
        if (r.get("features") or {}).get("snap_available", 0) > 0
    )

    return {
        "total_trades": manifest.get("sample_count", len(rows)) + manifest.get("rejected_count", 0),
        "eligible_trades": manifest.get("sample_count", len(rows)),
        "rejected_trades": manifest.get("rejected_count", 0),
        "rejection_reasons": manifest.get("rejection_reasons", {}),
        "missing_feature_rows": sum(
            1 for r in rows if not r.get("features")),
        "duplicate_trade_ids": dup_ids,
        "class_distribution": {
            "positive": pos,
            "negative": neg,
            "positive_rate": round(pos / len(labels), 4) if labels else 0,
            "imbalance_ratio": round(max(pos, neg) / max(min(pos, neg), 1), 2),
        },
        "symbols": {"count": len(symbols), "top": symbols.most_common(10)},
        "timeframes": dict(timeframes),
        "date_range": manifest.get("date_range", {}),
        "snapshot_coverage": {
            "with_snapshot": snap_avail,
            "without_snapshot": len(rows) - snap_avail,
            "coverage_rate": round(snap_avail / len(rows), 4) if rows else 0,
        },
        "concentration_warning": concentration_warning.strip("; "),
        "diversity_ok": not concentration_warning,
        "fingerprint": manifest.get("fingerprint", ""),
    }
