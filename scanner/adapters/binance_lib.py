"""محوّل بديل يعتمد مكتبة binance-python.

    pip install binance-python
    # ثم في config/crypto.yaml:  adapter: binance_lib

تنبيه: المكتبة غير مثبتة في بيئة التطوير هنا، فلم يُختبر هذا المحوّل على
اتصال حقيقي. لهذا كُتب دفاعياً: يستنتج أسماء حقول الشمعة بدل افتراضها،
حتى لا ينكسر إذا اختلفت التسمية بين الإصدارات.

المكتبة غير متزامنة (async)، والمحرك متزامن، لذا نغلّف كل نداء بـ asyncio.run.
هذا آمن لأن كل عامل في ThreadPoolExecutor يحصل على حلقة أحداث مستقلة.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pandas as pd

from .base import MarketAdapter

# أسماء محتملة لكل حقل — أول موجود يُستخدم
FIELD_CANDIDATES = {
    "open_time": ("open_time", "openTime", "time", "timestamp"),
    "open": ("open", "open_price", "o"),
    "high": ("high", "high_price", "h"),
    "low": ("low", "low_price", "l"),
    "close": ("close", "close_price", "c"),
    "volume": ("volume", "base_volume", "baseVolume", "v"),
    "close_time": ("close_time", "closeTime"),
}

MAX_PER_REQUEST = 1000


def _pick(candle, names: tuple[str, ...]):
    for n in names:
        if hasattr(candle, n):
            return getattr(candle, n)
        if isinstance(candle, dict) and n in candle:
            return candle[n]
    return None


def _num(value) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


class BinanceLibAdapter(MarketAdapter):
    name = "binance_lib"

    def __init__(self, timeout: int = 20):
        try:
            from binance.spot import MarketData  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "المحوّل يحتاج: pip install binance-python\n"
                "أو أعد adapter: binance في ملف الإعدادات لاستخدام المحوّل المدمج."
            ) from exc
        self._MarketData = MarketData
        self.timeout = timeout

    # ------------------------------------------------------------------ جلب

    def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        if limit > MAX_PER_REQUEST:
            # الترقيم عبر endTime غير موثّق في المكتبة؛ لا نخمّن اسم المعامل
            limit = MAX_PER_REQUEST
        candles = asyncio.run(self._candles(symbol, timeframe, limit))
        if not candles:
            raise RuntimeError(f"{symbol}: لم تصل أي بيانات")
        return self.validate(self.to_frame(candles), symbol)

    async def _candles(self, symbol: str, timeframe: str, limit: int):
        client = self._MarketData()
        ctx = getattr(client, "__aenter__", None)
        if ctx is not None:
            async with client:
                return await client.candles(symbol, interval=timeframe, limit=limit)
        return await client.candles(symbol, interval=timeframe, limit=limit)

    @staticmethod
    def to_frame(candles, drop_unclosed: bool = True) -> pd.DataFrame:
        rows = []
        for c in candles:
            row = {k: _pick(c, names) for k, names in FIELD_CANDIDATES.items()}
            if row["open_time"] is None:
                raise ValueError(
                    "تعذّر التعرف على حقل الوقت في كائن الشمعة. "
                    f"الحقول المتاحة: {sorted(vars(c)) if hasattr(c, '__dict__') else type(c)}"
                )
            rows.append(row)

        df = pd.DataFrame(rows)
        df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
        df = df.set_index("open_time").sort_index()
        df = df[~df.index.duplicated(keep="last")]

        if drop_unclosed and df["close_time"].notna().all():
            now = pd.Timestamp.now("UTC")
            close_times = pd.to_datetime(df["close_time"], utc=True)
            df = df[close_times <= now]

        for col in ("open", "high", "low", "close", "volume"):
            df[col] = df[col].map(_num)

        return df[["open", "high", "low", "close", "volume"]].astype("float64")

    # ------------------------------------------------------------- الرموز

    def usdt_universe(self, min_quote_volume: float = 5_000_000,
                      top_n: int | None = None, exclude_stables: bool = True) -> list[str]:
        """قائمة الأزواج عبر إحصاءات 24 ساعة من المكتبة نفسها."""
        from .binance import STABLE_BASES, is_leveraged

        stats = asyncio.run(self._stats_24h())
        pairs: list[tuple[str, float]] = []
        for d in stats:
            sym = _pick(d, ("symbol", "s"))
            qv = _pick(d, ("quote_volume", "quoteVolume", "q"))
            if not sym or not str(sym).endswith("USDT"):
                continue
            base = str(sym)[:-4]
            if is_leveraged(base):
                continue
            if exclude_stables and base in STABLE_BASES:
                continue
            try:
                qvf = _num(qv)
            except (TypeError, ValueError):
                continue
            if qvf != qvf or qvf < min_quote_volume:  # NaN أو دون الحد
                continue
            pairs.append((str(sym), qvf))

        pairs.sort(key=lambda p: p[1], reverse=True)
        symbols = [p[0] for p in pairs]
        return symbols[:top_n] if top_n else symbols

    async def _stats_24h(self):
        client = self._MarketData()
        for method in ("stats_24h", "stats24h", "ticker_24h"):
            fn = getattr(client, method, None)
            if fn is not None:
                return await fn()
        raise AttributeError(
            "لم أجد دالة إحصاءات 24 ساعة في المكتبة. "
            "استخدم adapter: binance أو حدّد universe: list في الإعدادات."
        )
