# -*- coding: utf-8 -*-
"""Symbol analysis context for manual AI review — no OHLC in Claude payload."""
from __future__ import annotations

from typing import Any

UI_TIMEFRAMES = frozenset({"15m", "1h", "4h", "1d", "1w"})


def build_symbol_context(symbol: str, market: str,
                         timeframe: str | None = None) -> dict[str, Any]:
    """Fetch candles, score, return recommendation + row for layer collectors."""
    from django.conf import settings

    from scanner import storage
    from scanner.config import load_market
    from scanner.scoring import score_with_recommendation
    from scanner.adapters import get_adapter

    cfg_path = settings.SCANNER_CONFIG_DIR / f"{market}.yaml"
    if not cfg_path.exists():
        raise ValueError(f"No market config: {market}")

    cfg = load_market(cfg_path)
    timeframe = timeframe or cfg.timeframes[0]
    if timeframe not in UI_TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    adapter = get_adapter(cfg.adapter)
    cached = storage.load(cfg.name, symbol, timeframe)
    fresh = adapter.fetch(symbol, timeframe, cfg.candles)
    df = storage.merge(cached, fresh)
    storage.save(cfg.name, symbol, timeframe, df)

    if len(df) < 60:
        raise ValueError(f"Insufficient data ({len(df)} candles)")

    result = score_with_recommendation(df, symbol, timeframe, cfg)
    row = result.to_row()

    return {
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "recommendation": result.recommendation,
        "row": row,
        "score": round(result.score, 1),
        "decision": result.decision,
        "ready": result.ready,
        "htf": result.htf,
        "close": result.close,
    }
