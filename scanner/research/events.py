# -*- coding: utf-8 -*-
"""Independent event clustering for honest sample sizing."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable


def _to_ts(value) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    return None


def count_independent_events(rows: Iterable[dict], *,
                             bucket_hours: int = 4) -> int:
    """Cluster trades by market+timeframe+time bucket."""
    buckets: set[tuple] = set()
    for row in rows:
        if row.get("status") not in ("won", "lost"):
            continue
        market = row.get("market") or "—"
        tf = row.get("timeframe") or "—"
        ts = _to_ts(row.get("closed_at") or row.get("signal_at"))
        if ts is None:
            buckets.add((market, tf, "unknown"))
            continue
        hour_bucket = int(ts.timestamp() // (bucket_hours * 3600))
        buckets.add((market, tf, hour_bucket))
    return len(buckets) or 0


def event_clusters(rows: Iterable[dict], *, bucket_hours: int = 4) -> list[dict]:
    """Return cluster summaries for export."""
    groups: dict[tuple, list] = defaultdict(list)
    for row in rows:
        if row.get("status") not in ("won", "lost"):
            continue
        market = row.get("market") or "—"
        tf = row.get("timeframe") or "—"
        ts = _to_ts(row.get("closed_at") or row.get("signal_at"))
        key = (market, tf, int(ts.timestamp() // (bucket_hours * 3600)) if ts else -1)
        r = row.get("r_multiple")
        if r is not None:
            groups[key].append(float(r))
    out = []
    for key, rs in groups.items():
        out.append({
            "market": key[0],
            "timeframe": key[1],
            "bucket": key[2],
            "trades": len(rs),
            "net_r": round(sum(rs), 2),
        })
    return sorted(out, key=lambda x: -abs(x["net_r"]))
