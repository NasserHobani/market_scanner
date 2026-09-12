"""خطوط أساس للمقارنة العادلة مع أي استراتيجية."""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Iterable

import pandas as pd

from .. import execution
from ..tracking import LOST, WON, Plan, resolve, summarize


@dataclass
class BaselineSummary:
    name: str
    stats: dict


def _risk_pct(entry: float, stop: float) -> float:
    if entry <= 0:
        return 0.0
    return abs(entry - stop) / entry * 100


def _net_rows(rows: Iterable[dict], model: execution.CostModel | None = None) -> list[dict]:
    """يضيف صافي R بعد الكلفة لنفس صفوف التقييم."""
    model = model or execution.DEFAULT
    out: list[dict] = []
    for row in rows:
        r = row.get("r_multiple")
        if r is None:
            out.append(dict(row))
            continue
        rp = float(row.get("risk_pct") or 0.0)
        liq = row.get("liquidity") or "unknown"
        net = model.net_r(float(r), rp, liq, entry_kind="maker", exit_kind="stop")
        cloned = dict(row)
        cloned["r_multiple"] = round(net, 4)
        out.append(cloned)
    return out


def _buy_hold_rows(df: pd.DataFrame, symbol: str, timeframe: str, warmup: int) -> list[dict]:
    if len(df) <= warmup + 5:
        return []
    entry = float(df["close"].iloc[warmup])
    end = float(df["close"].iloc[-1])
    stop = entry * 0.95
    risk = entry - stop
    if risk <= 0:
        return []
    r = (end - entry) / risk
    return [{
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": "buy_hold",
        "status": WON if r > 0 else LOST,
        "r_multiple": round(r, 4),
        "risk_pct": _risk_pct(entry, stop),
        "liquidity": "unknown",
    }]


def _ema_cross_rows(df: pd.DataFrame, symbol: str, timeframe: str, warmup: int,
                    fast: int = 20, slow: int = 50) -> list[dict]:
    if len(df) <= max(warmup + slow + 2, 80):
        return []
    ef = df["close"].ewm(span=fast, adjust=False).mean()
    es = df["close"].ewm(span=slow, adjust=False).mean()
    rows: list[dict] = []
    n = len(df)
    for i in range(max(warmup, slow + 1), n - 3):
        prev_up = ef.iloc[i - 1] <= es.iloc[i - 1]
        now_up = ef.iloc[i] > es.iloc[i]
        if not (prev_up and now_up):
            continue
        entry = float(df["close"].iloc[i])
        stop = float(df["low"].iloc[max(0, i - 10):i + 1].min())
        if stop >= entry:
            continue
        risk = entry - stop
        target = entry + risk * 2.0
        plan = Plan(side="buy", entry=entry, stop=stop, target=target)
        bars = [{
            "open": float(df["open"].iloc[j]),
            "high": float(df["high"].iloc[j]),
            "low": float(df["low"].iloc[j]),
            "close": float(df["close"].iloc[j]),
        } for j in range(i + 1, min(n, i + 1 + 120))]
        res = resolve(bars, plan, already_entered=True, entry_price=entry, max_bars=60)
        if res.status not in (WON, LOST):
            continue
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": "ema_cross",
            "status": res.status,
            "r_multiple": res.r_multiple,
            "risk_pct": _risk_pct(entry, stop),
            "liquidity": "unknown",
        })
    return rows


def _random_rows(df: pd.DataFrame, symbol: str, timeframe: str, warmup: int,
                 seed: int = 42, entries: int = 12) -> list[dict]:
    if len(df) <= warmup + 20:
        return []
    rnd = random.Random(f"{seed}:{symbol}:{timeframe}")
    start = warmup
    end = len(df) - 5
    if end <= start:
        return []
    picks = sorted(rnd.sample(range(start, end), k=min(entries, end - start)))
    rows: list[dict] = []
    for i in picks:
        entry = float(df["close"].iloc[i])
        stop = entry * 0.98
        risk = entry - stop
        if risk <= 0:
            continue
        target = entry + risk * 2.0
        plan = Plan(side="buy", entry=entry, stop=stop, target=target)
        bars = [{
            "open": float(df["open"].iloc[j]),
            "high": float(df["high"].iloc[j]),
            "low": float(df["low"].iloc[j]),
            "close": float(df["close"].iloc[j]),
        } for j in range(i + 1, min(len(df), i + 1 + 80))]
        res = resolve(bars, plan, already_entered=True, entry_price=entry, max_bars=40)
        if res.status not in (WON, LOST):
            continue
        rows.append({
            "symbol": symbol,
            "timeframe": timeframe,
            "strategy": "random_entry",
            "status": res.status,
            "r_multiple": res.r_multiple,
            "risk_pct": _risk_pct(entry, stop),
            "liquidity": "unknown",
        })
    return rows


def run_baselines(data: dict[str, pd.DataFrame], timeframe: str, *,
                  warmup: int = 300, seed: int = 42) -> list[BaselineSummary]:
    by_name: dict[str, list[dict]] = {"buy_hold": [], "ema_cross": [], "random_entry": []}
    for symbol, df in data.items():
        by_name["buy_hold"].extend(_buy_hold_rows(df, symbol, timeframe, warmup))
        by_name["ema_cross"].extend(_ema_cross_rows(df, symbol, timeframe, warmup))
        by_name["random_entry"].extend(_random_rows(df, symbol, timeframe, warmup, seed=seed))

    out: list[BaselineSummary] = []
    for name, rows in by_name.items():
        net = _net_rows(rows)
        stats = summarize(net)
        stats["name"] = name
        out.append(BaselineSummary(name=name, stats=stats))
    return out
