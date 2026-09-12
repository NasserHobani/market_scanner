"""بناء بيانات التدريب من Feature Store."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from scanner.features.store import read_snapshots


@dataclass
class DatasetBundle:
    frame: pd.DataFrame
    features: list[str]
    target: str


def _to_frame() -> pd.DataFrame:
    snaps = read_snapshots()
    rows = []
    for s in snaps:
        rows.append({
            "snapshot_id": s.snapshot_id,
            "symbol": s.symbol,
            "market": s.market,
            "timeframe": s.timeframe,
            "score": s.score,
            "confluence": s.confluence,
            "htf": s.htf,
            "confidence": s.confidence,
            "action": s.action,
            "grade": s.grade,
            "rr": s.rr,
            "liquidity": s.liquidity,
            "quote_volume": s.quote_volume,
            **{f"f_{k}": v for k, v in s.features.items()},
        })
    return pd.DataFrame(rows)


def load_from_django() -> pd.DataFrame:
    """يربط اللقطات بنتيجة الصفقة الفعلية إن توفّرت Django."""
    base = _to_frame()
    if base.empty:
        return base
    try:
        from dashboard.models import Trade
    except Exception:
        return pd.DataFrame()
    trades = Trade.objects.filter(status__in=["won", "lost"]).values(
        "feature_snapshot_id", "r_multiple", "status", "source")
    labels = pd.DataFrame(list(trades))
    if labels.empty:
        return pd.DataFrame()
    labels = labels.rename(columns={"feature_snapshot_id": "snapshot_id"})
    out = base.merge(labels, on="snapshot_id", how="inner")
    out["target_cls"] = (out["r_multiple"] > 0).astype(int)
    out["target_reg"] = out["r_multiple"].astype(float)
    return out


def load_training_data(csv_path: str | None = None) -> pd.DataFrame:
    if csv_path:
        path = Path(csv_path)
        if path.exists():
            return pd.read_csv(path)
    return load_from_django()


def build_bundle(df: pd.DataFrame, target: str = "target_cls") -> DatasetBundle:
    excluded = {"snapshot_id", "symbol", "market", "timeframe", "status", "source",
                "r_multiple", "target_cls", "target_reg", "action", "grade", "liquidity"}
    frame = df.copy()
    frame["action"] = frame.get("action", "none").map({"none": 0, "pending": 1, "now": 2}).fillna(0)
    frame["grade"] = frame.get("grade", "—").map({"—": 0, "C": 1, "B": 2, "A": 3}).fillna(0)
    frame["liquidity"] = frame.get("liquidity", "unknown").map(
        {"unknown": 0, "micro": 1, "low": 2, "mid": 3, "high": 4}).fillna(0)
    features = [c for c in frame.columns if c not in excluded]
    return DatasetBundle(frame=frame, features=features, target=target)
