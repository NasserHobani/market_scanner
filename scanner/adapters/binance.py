"""محوّل Binance — بيانات سوق عامة، بلا مفتاح، بلا تكلفة.

المضيف الافتراضي `data-api.binance.vision` هو نقطة البيانات العامة الرسمية
من Binance: للقراءة فقط، ولا تتأثر بحجب الوصول الجغرافي الذي يطال
`api.binance.com` في بعض الشبكات. عند فشله يُجرَّب المضيف الرئيسي تلقائياً.

الحد: 6000 وحدة وزن في الدقيقة لكل IP. وزن طلب الشموع 2،
أي أن 400 زوج × 3 فريمات (~2400 وحدة) يبقى تحت نصف الحد.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .base import MarketAdapter

HOSTS = [
    "https://data-api.binance.vision",
    "https://api.binance.com",
]
MAX_PER_REQUEST = 1000
UNIVERSE_TTL = 600.0        # ثوانٍ — قائمة الرموز لا تتغير كل دقيقة
UA = {"User-Agent": "market-scanner/0.1"}

KLINE_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]

# رموز الرافعة المالية: لواحق لا أجزاء. المطابقة الجزئية كانت تحذف عملات
# حقيقية مثل JUP و SUPER لمجرد احتوائها على "UP".
LEVERAGE_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")

# العملات المستقرة والورقية: تحليلها فنياً بلا معنى، سعرها مثبّت
STABLE_BASES = {
    "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "GBP", "AEUR",
    "PAX", "SUSD", "USD1", "RLUSD", "PYUSD", "USDE", "USDS", "USDD",
    "GUSD", "LUSD", "FRAX", "TRY", "BRL", "ARS", "JPY", "RUB", "ZAR",
    "UAH", "PLN", "RON", "CZK", "MXN", "COP", "IDRT", "NGN", "VAI",
    # أُضيفت بعد أن أصدر المحرّك خطة على BFUSDUSDT بوقف **0.01%**:
    # مدى شمعتها الوسيط صفر، فـ ATR يقارب الصفر والوقف يتبعه. خطة
    # كهذه تُبتلع كلفتها آلاف المرات، وتُفسد أي متوسط تدخله لأن
    # الكلفة تتناسب عكسياً مع الوقف.
    "BFUSD", "USDF", "XUSD", "USDX", "EURI", "USTC", "USDQ", "AUD",
}

# الذهب المرمّز: يتحرك مع الذهب لا مع السوق، فمنطق الفوليوم عليه مضلّل
COMMODITY_BASES = {"PAXG", "XAUT", "XAU", "TGOLD"}


def is_leveraged(base: str) -> bool:
    """رموز الرافعة تنتهي باللاحقة ويسبقها اسم أصل (BTCUP، ETHBEAR)."""
    for suf in LEVERAGE_SUFFIXES:
        if base.endswith(suf) and len(base) > len(suf) + 1:
            return True
    return False


def is_tokenized_equity(base: str) -> bool:
    """أسهم مرمّزة على بينانس (لاحقة B): SPCXB، SNDKB، SKHYB.

    تُستبعد افتراضياً لأنها تتبع سوق الأسهم بساعاته وفجواته،
    فمؤشرات الفوليوم المستمر عليها لا تعني ما تعنيه في العملات.
    """
    return len(base) >= 4 and base.endswith("B") and base[:-1].isalpha() and base[:-1].isupper()


class BinanceAdapter(MarketAdapter):
    name = "binance"
    _universe_cache: tuple[float, list[str]] | None = None

    def __init__(self, pause: float = 0.05, retries: int = 3, timeout: int = 20):
        self.pause = pause
        self.retries = retries
        self.timeout = timeout
        self._host = HOSTS[0]

    # ------------------------------------------------------------------ جلب

    def fetch(self, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
        rows: list[list] = []
        remaining = limit
        end_time: int | None = None

        while remaining > 0:
            batch = min(remaining, MAX_PER_REQUEST)
            params = {"symbol": symbol, "interval": timeframe, "limit": batch}
            if end_time is not None:
                params["endTime"] = end_time
            chunk = self._get("/api/v3/klines", params)
            if not chunk:
                break
            rows = chunk + rows
            remaining -= len(chunk)
            end_time = chunk[0][0] - 1
            if len(chunk) < batch:
                break
            time.sleep(self.pause)

        if not rows:
            raise RuntimeError(f"{symbol}: لم تصل أي بيانات")
        return self.validate(self.to_frame(rows), symbol)

    @staticmethod
    def to_frame(rows: list[list], drop_unclosed: bool = True) -> pd.DataFrame:
        """تحويل استجابة Binance الخام إلى الشكل الموحّد.

        مفصولة عن الجلب عمداً حتى تُختبر على حمولة حقيقية بلا شبكة.
        """
        df = pd.DataFrame(rows, columns=KLINE_COLUMNS)
        df["open_time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True)
        df = df.set_index("open_time")
        df = df[~df.index.duplicated(keep="last")].sort_index()

        if drop_unclosed:
            # الشمعة الجارية تُستبعد دائماً — هذا ما يمنع إعادة الرسم
            now_ms = int(time.time() * 1000)
            df = df[df["close_time"].astype("int64") <= now_ms]

        return df[["open", "high", "low", "close", "volume"]].astype("float64")

    # ------------------------------------------------------------- الرموز

    def usdt_universe(
        self,
        min_quote_volume: float = 5_000_000,
        top_n: int | None = None,
        exclude_stables: bool = True,
        exclude_equities: bool = True,
        exclude_commodities: bool = True,
        diagnose: bool = False,
    ) -> list[str]:
        """كل أزواج USDT الفورية، مرتّبة بحجم التداول خلال 24 ساعة."""
        data = self._get("/api/v3/ticker/24hr", {})
        stats = {"إجمالي الرموز": len(data), "أزواج USDT": 0, "رافعة": 0,
                 "مستقرة/ورقية": 0, "أسهم مرمّزة": 0, "سلع": 0,
                 "دون حد الحجم": 0, "مقبولة": 0}
        pairs: list[tuple[str, float]] = []
        rejected_by_volume: list[tuple[str, float]] = []

        for d in data:
            sym = d.get("symbol", "")
            if not sym.endswith("USDT"):
                continue
            stats["أزواج USDT"] += 1
            base = sym[:-4]

            if is_leveraged(base):
                stats["رافعة"] += 1
                continue
            if exclude_stables and base in STABLE_BASES:
                stats["مستقرة/ورقية"] += 1
                continue
            if exclude_commodities and base in COMMODITY_BASES:
                stats["سلع"] += 1
                continue
            if exclude_equities and is_tokenized_equity(base):
                stats["أسهم مرمّزة"] += 1
                continue

            try:
                qv = float(d.get("quoteVolume", 0.0))
            except (TypeError, ValueError):
                continue
            if qv < min_quote_volume:
                stats["دون حد الحجم"] += 1
                rejected_by_volume.append((sym, qv))
                continue

            stats["مقبولة"] += 1
            pairs.append((sym, qv))

        pairs.sort(key=lambda p: p[1], reverse=True)

        if diagnose:
            print("\n--- مسار التصفية ---")
            for k, v in stats.items():
                print(f"  {k:16} {v}")
            rejected_by_volume.sort(key=lambda p: p[1], reverse=True)
            if rejected_by_volume:
                print(f"\n  أعلى 10 مرفوضة بسبب الحجم (الحد {min_quote_volume:,.0f}$):")
                for sym, qv in rejected_by_volume[:10]:
                    print(f"    {sym:14} {qv:>18,.0f}$")
            if pairs:
                print("\n  أعلى 10 مقبولة:")
                for sym, qv in pairs[:10]:
                    print(f"    {sym:14} {qv:>18,.0f}$")
            print()

        # الأحجام تُحفظ للنداء اللاحق: المسح يحتاجها لتصنيف السيولة،
        # وإعادة طلب ticker/24hr (~2 ميجابايت) لأجلها إهدار محض
        self.last_volumes = dict(pairs)

        symbols = [p[0] for p in pairs]
        return symbols[:top_n] if top_n else symbols

    def quote_volumes(self) -> dict[str, float]:
        """أحجام 24 ساعة من آخر نداء لـ usdt_universe — قد تكون فارغة."""
        return dict(getattr(self, "last_volumes", {}) or {})

    def search(self, query: str, limit: int = 12) -> list[dict]:
        """بحث بالرمز أو باسم العملة الأساسي.

        طلب ticker/24hr يجلب آلاف الرموز (~2 ميجابايت) وله وزن ثقيل،
        فنخزّنه مؤقتاً. وإن تعذّر الوصول نجرّب الرمز مباشرة بطلب خفيف
        بدل إرجاع «لا نتائج» — الفرق بين «غير موجود» و«تعذّر الجلب» مهم.
        """
        q = query.strip().upper().replace(" ", "")
        if not q:
            return []

        universe, error = self._cached_universe()

        if universe:
            exact, starts, contains = [], [], []
            for sym in universe:
                base = sym[:-4]
                if base == q or sym == q:
                    exact.append(sym)
                elif base.startswith(q):
                    starts.append(sym)
                elif q in base:
                    contains.append(sym)
            ordered = exact + starts + contains
            if ordered:
                return [{"symbol": s, "name": s[:-4], "market": "crypto"}
                        for s in ordered[:limit]]

        # احتياط: تحقّق مباشر من الرمز بطلب خفيف.
        # نقتصر على أزواج USDT — غيرها يعطي اسماً فارغاً عند القصّ [:-4]
        # ولا يدعمه المحرك أصلاً.
        candidate = q if q.endswith("USDT") else q + "USDT"
        if len(candidate) > 4 and self.symbol_exists(candidate):
            return [{"symbol": candidate, "name": candidate[:-4],
                     "market": "crypto"}]

        if error:
            raise RuntimeError(f"تعذّر جلب قائمة الرموز: {error}")
        return []

    def symbol_exists(self, symbol: str) -> bool:
        """طلب خفيف جداً (وزن 1) للتحقق من وجود الرمز."""
        try:
            data = self._get("/api/v3/ticker/price", {"symbol": symbol})
            return bool(data and data.get("symbol") == symbol)
        except Exception:  # noqa: BLE001
            return False

    def _cached_universe(self) -> tuple[list[str], str]:
        """قائمة الرموز مع ذاكرة مؤقتة. يعيد (القائمة، نص الخطأ)."""
        now = time.time()
        cached = BinanceAdapter._universe_cache
        if cached and (now - cached[0]) < UNIVERSE_TTL:
            return cached[1], ""
        try:
            symbols = self.usdt_universe(min_quote_volume=0)
            BinanceAdapter._universe_cache = (now, symbols)
            return symbols, ""
        except Exception as exc:  # noqa: BLE001
            if cached:
                return cached[1], ""          # قائمة قديمة خير من لا شيء
            return [], str(exc)[:200]

    # ------------------------------------------------------------- الشبكة

    def _get(self, path: str, params: dict):
        query = urllib.parse.urlencode(params)
        last_error: Exception | None = None

        for host in [self._host] + [h for h in HOSTS if h != self._host]:
            url = f"{host}{path}" + (f"?{query}" if query else "")
            delay = 1.0
            for attempt in range(self.retries):
                try:
                    req = urllib.request.Request(url, headers=UA)
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        self._host = host  # نثبت على المضيف الناجح
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    last_error = exc
                    if exc.code in (418, 429) and attempt < self.retries - 1:
                        time.sleep(delay)
                        delay *= 3  # تباعد تصاعدي عند تجاوز الحد
                        continue
                    break  # خطأ لا تنفع معه الإعادة على هذا المضيف
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    last_error = exc
                    if attempt == self.retries - 1:
                        break
                    time.sleep(delay)
                    delay *= 2

        raise RuntimeError(f"تعذّر الوصول لـ Binance: {last_error}")
