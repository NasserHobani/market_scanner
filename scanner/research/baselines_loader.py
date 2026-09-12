# -*- coding: utf-8 -*-
"""Baseline comparison for research dashboard."""
from __future__ import annotations

import json
from pathlib import Path

from scanner.backtest.baselines import run_baselines
from scanner import storage
from scanner.tracking import summarize


_BASELINE_AR = {
    "buy_hold": "شراء واحتفاظ",
    "ema_cross": "تقاطع EMA",
    "random_entry": "دخول عشوائي",
}


def _strategy_row(name: str, rows: list[dict], *, source: str = "live") -> dict:
    s = summarize(rows)
    exp = s.get("expectancy")
    return {
        "name": name,
        "source": source,
        "trades": s.get("closed"),
        "expectancy": exp,
        "profit_factor": s.get("profit_factor"),
        "max_drawdown_r": s.get("max_drawdown_r"),
        "sharpe": s.get("sharpe"),
        "pass_gate": exp is not None and exp > 0,
    }


def _load_market_frames(market: str, timeframe: str, limit: int = 50) -> dict:
    base = Path("data") / market / timeframe
    symbols = sorted({p.stem for p in base.glob("*.csv")}
                     | {p.stem for p in base.glob("*.parquet")})
    if limit:
        symbols = symbols[:limit]
    data = {}
    for sym in symbols:
        df = storage.load(market, sym, timeframe)
        if df is not None and len(df) > 100:
            data[sym] = df
    return data


def baseline_comparison(live_rows: list[dict], *,
                        market: str = "crypto",
                        timeframe: str = "4h") -> dict:
    """Compare live strategy vs baselines and backtest cache."""
    table = [_strategy_row("الاستراتيجية الحالية (حيّ)", live_rows, source="live")]

    # Backtest cache as proxy for strategy on full history
    cache_path = Path("data/backtest")
    best_cache = None
    best_exp = None
    for path in cache_path.glob("reco_*.jsonl"):
        rows = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.extend(json.loads(line).get("rows") or [])
        except Exception:
            continue
        s = summarize(rows)
        if s.get("closed") and (best_exp is None or (s.get("expectancy") or -99) > best_exp):
            best_exp = s.get("expectancy")
            best_cache = (path.stem, rows, s)

    if best_cache:
        table.append(_strategy_row(
            f"اختبار خلفي ({best_cache[0]})", best_cache[1], source="backtest"))

    # Baselines from stored market data (sample)
    if market and timeframe:
        frames = _load_market_frames(market, timeframe, limit=30)
        if frames:
            for item in run_baselines(frames, timeframe):
                s = item.stats
                table.append({
                    "name": _BASELINE_AR.get(item.name, item.name),
                    "source": "baseline",
                    "trades": s.get("closed"),
                    "expectancy": s.get("expectancy"),
                    "profit_factor": s.get("profit_factor"),
                    "max_drawdown_r": s.get("max_drawdown_r"),
                    "sharpe": s.get("sharpe"),
                    "pass_gate": False,
                })

    live_exp = table[0].get("expectancy")
    baseline_exps = [r.get("expectancy") for r in table[1:]
                     if r.get("source") == "baseline" and r.get("expectancy") is not None]
    best_baseline = max(baseline_exps) if baseline_exps else None
    gate_pass = (live_exp is not None and best_baseline is not None
                 and live_exp > best_baseline)
    for row in table:
        if row["source"] == "live":
            row["pass_gate"] = gate_pass
        exp = row.get("expectancy")
        if exp is not None and best_baseline is not None and row["source"] == "baseline":
            row["pass_gate"] = live_exp is not None and live_exp > exp

    return {
        "rows": table,
        "gate_pass": gate_pass,
        "best_baseline_expectancy": best_baseline,
        "strategy_expectancy": live_exp,
    }
