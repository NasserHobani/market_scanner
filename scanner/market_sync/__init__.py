# -*- coding: utf-8 -*-
"""Background market-data synchronization — independent of scan/AI/trading."""
from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig
from .freshness import FreshnessStatus, assess_freshness, expected_open_candle
from .service import MarketDataSyncService, get_service

__all__ = [
    "DEFAULT_SYNC_CONFIG",
    "FreshnessStatus",
    "MarketDataSyncService",
    "MarketSyncConfig",
    "assess_freshness",
    "expected_open_candle",
    "get_service",
]
