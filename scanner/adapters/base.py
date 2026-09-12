"""عقد موحّد لكل مصادر البيانات.

كل محوّل يعيد DataFrame بنفس الشكل تماماً، فلا يعرف محرك التسجيل
من أي سوق جاءت البيانات. إضافة سوق رابع لاحقاً = ملف واحد هنا.

الأعمدة: open, high, low, close, volume
الفهرس:  DatetimeIndex بتوقيت UTC، تصاعدي، شموع مغلقة فقط
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


class MarketAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def fetch(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """يعيد آخر `limit` شمعة مغلقة."""

    @staticmethod
    def validate(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"{symbol}: أعمدة ناقصة {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"{symbol}: الفهرس ليس زمنياً")
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()
        return df[REQUIRED_COLUMNS].astype("float64")
