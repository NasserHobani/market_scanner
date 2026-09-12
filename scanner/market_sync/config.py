# -*- coding: utf-8 -*-
"""Configurable thresholds for background market-data sync (MD-01)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MarketSyncConfig:
    """Sync cadence and freshness gates — timeframe-aware, not hardcoded in the loop."""

    # Seconds between sync loops for each timeframe (background worker)
    interval_seconds: dict[str, int] = field(default_factory=lambda: {
        "15m": 120,
        "1h": 300,
        "4h": 900,
        "1d": 1800,
        "1w": 3600,
    })
    # Age thresholds as fraction of candle period (bars_behind)
    fresh_max_bars: float = 0.35      # within ~1/3 of a bar → FRESH
    stale_max_bars: float = 1.5       # up to 1.5 bars behind → STALE
    # ما تجاوز هذا لا يُصلحه تحديث — رمزٌ مشطوب. مئة شمعة على 4h
    # سبعة عشر يوماً، وعلى 1d مئة جلسة: انقطاعٌ حقيقيّ لأسبوع يبقى
    # دونها بكثير، فلا يُبتلع عطلٌ صادق تحت اسم «ميّت».
    dead_max_bars: float = 100.0      # beyond → DEAD (delisted)
    # beyond stale_max_bars → CRITICAL
    bootstrap_min_candles: int = 60
    max_workers: int = 10
    # ═══ لماذا رُفع من 200 ═══
    #
    # كان سقفاً صامتاً: ``resolve_symbols`` يقصّ ``out[:200]`` بلا
    # كلمة. وتاسي + نمو نحو ثلاثمئة شركة، فكان مئةٌ منها لا تُزامَن
    # أبداً ولا يُقال لماذا. والقصّ بلا ترتيب معنيّ (وهو حال الباقة
    # المجانية التي يتعذّر فيها الترتيب بالحجم) قصٌّ أبجديّ — أي
    # اختيار عشوائيّ لمن يُحلَّل.
    #
    # السقف يبقى حارساً من كون منفلت (آلاف أزواج الكريبتو)، لكنّه
    # يجب أن يتّسع لسوق أسهم كامل.
    max_symbols_per_market: int = 1000
    retry_backoff_seconds: tuple[int, ...] = (30, 60, 120, 300)
    status_path: str = "data/market_sync/status.json"
    events_path: str = "data/market_sync/events.jsonl"
    lock_dir: str = "data/market_sync/locks"
    # Prefer UI timeframes when market YAML lists only the auto-scan TF
    sync_timeframes: tuple[str, ...] = ("15m", "1h", "4h", "1d")


DEFAULT_SYNC_CONFIG = MarketSyncConfig()
