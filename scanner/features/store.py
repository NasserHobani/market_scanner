"""Append-only feature snapshot store."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .schema import FeatureSnapshot

STORE = Path("data/features/snapshots.jsonl")


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def _make_id(payload: dict) -> str:
    digest = hashlib.sha256(_canonical(payload)).hexdigest()[:20]
    return f"fs_{digest}"


def _append(payload: dict, path: Path = STORE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def write_snapshot(*, symbol: str, market: str, timeframe: str, candle_time: datetime,
                   score: float, confluence: int, htf: int, liquidity: str,
                   quote_volume: float | None, reco: dict | None,
                   extra_features: dict[str, Any] | None = None) -> str:
    reco = reco or {}
    features = extra_features or {}
    payload = {
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "candle_time": candle_time.astimezone(timezone.utc).isoformat(),
        "score": float(score),
        "confluence": int(confluence),
        "htf": int(htf),
        "liquidity": liquidity or "unknown",
        "quote_volume": quote_volume,
        "action": reco.get("action", "none"),
        "grade": reco.get("grade", "—"),
        "confidence": float(reco.get("confidence") or 0.0),
        "rr": reco.get("rr"),
        "factors": [x.get("label") for x in (reco.get("breakdown") or [])
                    if isinstance(x, dict) and x.get("value", 0) > 0],
        "features": features,
    }
    snapshot_id = _make_id(payload)
    row = {"snapshot_id": snapshot_id, **payload, "written_at": datetime.now(timezone.utc).isoformat()}
    _append(row)
    return snapshot_id


def read_snapshots(path: Path = STORE) -> list[FeatureSnapshot]:
    if not path.exists():
        return []
    out: list[FeatureSnapshot] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out.append(FeatureSnapshot(
            snapshot_id=row["snapshot_id"],
            symbol=row["symbol"],
            market=row["market"],
            timeframe=row["timeframe"],
            candle_time=datetime.fromisoformat(row["candle_time"].replace("Z", "+00:00")),
            score=float(row["score"]),
            confluence=int(row["confluence"]),
            htf=int(row["htf"]),
            liquidity=row.get("liquidity") or "unknown",
            quote_volume=row.get("quote_volume"),
            action=row.get("action", "none"),
            grade=row.get("grade", "—"),
            confidence=float(row.get("confidence") or 0),
            rr=row.get("rr"),
            factors=list(row.get("factors") or []),
            features=dict(row.get("features") or {}),
        ))
    return out


def rebuild_recommendation(snapshot_id: str, path: Path = STORE) -> dict | None:
    """إعادة بناء التوصية الأساسية من snapshot محفوظ."""
    for snap in read_snapshots(path):
        if snap.snapshot_id != snapshot_id:
            continue
        return {
            "action": snap.action,
            "grade": snap.grade,
            "confidence": snap.confidence,
            "rr": snap.rr,
            "factors": snap.factors,
            "features": snap.features,
        }
    return None
