"""محوّل Yahoo Finance — للسوقين الأمريكي والسعودي.

مساران عمداً:
  1) مكتبة `yfinance` إن كانت مثبتة — تتكفّل بمصادقة الكوكيز/الـcrumb التي
     صارت Yahoo تطلبها، وهي أكثر ما ينكسر عند التعامل المباشر.
  2) واجهة chart المباشرة عبر المكتبة القياسية عند غياب yfinance.

تحذير مهم: `yfinance` غير رسمية، وYahoo تغيّر واجهتها دون إشعار. لهذا عُزل
كل التعامل هنا: انكسارها يعني استبدال هذا الملف وحده.

للسوق السعودي: الرموز بصيغة `NNNN.SR` وبيانات نهاية يوم فقط.
التغطية تحتاج اختباراً رمزاً برمز — لا تفترض اكتمالها.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .base import MarketAdapter

CHART_HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
UA = {"User-Agent": "Mozilla/5.0 (compatible; market-scanner/0.1)"}

# فريم الماسح → فاصل Yahoo
INTERVAL = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "1d": "1d", "1w": "1wk", "1M": "1mo",
}

# أقصى مدى تسمح به Yahoo لكل فاصل
MAX_RANGE = {"1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d", "1h": "730d"}

# ═══════════════════════════════════════════════════════════════
#  فريماتٌ تُشتقّ — لأنّ Yahoo لا يعطيها
# ═══════════════════════════════════════════════════════════════
#
# ‏Yahoo لا فاصلَ ‎4h‎ عنده. وكان ``fetch`` يرمي «فريم غير مدعوم»،
# فتفشل مزامنة كل رمزٍ سعوديّ على ‎4h‎ — في كل دورة، إلى الأبد.
#
# وأثرُه لم يكن رسالة خطأ بل **غياباً كاملاً**: الماسحات تقرأ
# ``stored_symbols(market, "4h")``، فالسوق السعودي كلّه — ٣٢٥
# شركة — لم يدخل تقييم PES ولا مرّة. صفر ملفّات، صفر صفوف، ولا
# سطر يقول لماذا.
#
# والاشتقاق من ‎1h‎ لا من ‎1d‎: ياهو يعطي ٧٣٠ يوماً من الساعيّ،
# أي ما يكفي لأكثر من ألف شمعة أربع‑ساعية.
DERIVED = {"2h": ("1h", 2), "4h": ("1h", 4), "12h": ("1h", 12)}

_AGG = {"open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum"}


class YahooAdapter(MarketAdapter):
    name = "yahoo"

    def __init__(self, timeout: int = 25, pause: float = 0.15):
        self.timeout = timeout
        self.pause = pause
        self._yf = None
        try:
            import yfinance  # type: ignore

            self._yf = yfinance
        except ImportError:
            pass

    # ------------------------------------------------------------------ جلب

    def fetch(self, symbol: str, timeframe: str, limit: int = 1500) -> pd.DataFrame:
        # ═══ المشتقّ قبل المباشر ═══
        #
        # ‎4h‎ ليست في ``INTERVAL`` ولن تكون: ياهو لا يعطيها. فتُبنى
        # من الساعيّ هنا، ويبقى بقيّة النظام لا يعرف الفرق.
        derived = DERIVED.get(timeframe)
        if derived:
            base, factor = derived
            # هامشٌ فوق الحاجة: جلسة السوق لا تملأ كل دلوٍ أربع‑ساعيّ،
            # فعددُ الشمعات الناتج أقلّ من القسمة النظرية.
            raw = self.fetch(symbol, base,
                             limit=min(limit * factor + factor * 4, 20000))
            return self._to_derived(raw, timeframe, limit, symbol)

        interval = INTERVAL.get(timeframe)
        if interval is None:
            raise ValueError(f"فريم غير مدعوم في Yahoo: {timeframe}")

        if self._yf is not None:
            df = self._fetch_yfinance(symbol, interval, limit)
        else:
            df = self._fetch_chart_api(symbol, interval, limit)

        if df is None or df.empty:
            raise RuntimeError(f"{symbol}: لا توجد بيانات (تحقق من صحة الرمز)")
        return self.validate(df.tail(limit), symbol)

    def _to_derived(self, raw: pd.DataFrame, timeframe: str,
                    limit: int, symbol: str) -> pd.DataFrame:
        """يجمّع الساعيّ إلى الفريم المطلوب.

        ═══ ``label="left"`` لا ``"right"`` ═══

        شمعة ‎4h‎ تُنسَب إلى **بداية** مدّتها، كما تفعل المنصّات
        كلّها: شمعة ‎12:00‎ تحمل ما جرى بين ‎12:00‎ و‎16:00‎. وبالنسبة
        إلى النهاية يزيح التاريخَ أربع ساعات، فينزلق كل مؤشّرٍ
        يُقارَن بشمعةٍ من فريمٍ آخر.

        ═══ والدلاء الفارغة تُحذف ═══

        السوق السعودي يعمل نحو خمس ساعات في اليوم، فأغلب دلاء
        اليوم فارغة. و``dropna`` يزيلها — وبلاه تدخل شمعاتٌ
        بأسعار ‎NaN‎ تُفسد كل حسابٍ بعدها بصمت.
        """
        if raw is None or raw.empty:
            raise RuntimeError(f"{symbol}: لا بيانات ساعية لاشتقاق {timeframe}")
        # ‏"4h" و"2h" و"12h" أسماءُ إزاحةٍ يفهمها pandas كما هي
        out = (raw.resample(timeframe, label="left", closed="left")
                  .agg(_AGG)
                  .dropna(subset=["open", "high", "low", "close"]))
        # حجمٌ صفر بلا سعرٍ صفر: عطلةٌ داخل الدلو، لا شمعةٌ باطلة
        out = out[out["high"] >= out["low"]]
        if out.empty:
            raise RuntimeError(f"{symbol}: تعذّر اشتقاق {timeframe} من الساعيّ")
        return self.validate(out.tail(limit), symbol)

    def _fetch_yfinance(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        period = self._period_for(interval, limit)
        raw = self._yf.Ticker(symbol).history(
            period=period, interval=interval, auto_adjust=False, actions=False
        )
        if raw is None or raw.empty:
            return pd.DataFrame()
        raw = raw.rename(columns=str.lower)
        idx = pd.to_datetime(raw.index, utc=True)
        out = pd.DataFrame(
            {c: pd.to_numeric(raw[c], errors="coerce") for c in
             ("open", "high", "low", "close", "volume")},
            index=idx,
        )
        return self._clean(out)

    def _fetch_chart_api(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        params = {
            "interval": interval,
            "range": self._period_for(interval, limit),
            "includePrePost": "false",
        }
        payload = self._get(f"/v8/finance/chart/{urllib.parse.quote(symbol)}", params)
        return self.parse_chart(payload)

    @staticmethod
    def parse_chart(payload: dict) -> pd.DataFrame:
        """تحويل استجابة chart v8 إلى الشكل الموحّد.

        مفصولة عن الشبكة عمداً حتى تُختبر بلا اتصال.
        """
        chart = (payload or {}).get("chart") or {}
        if chart.get("error"):
            raise RuntimeError(f"Yahoo: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            return pd.DataFrame()

        r = results[0]
        stamps = r.get("timestamp") or []
        quote_list = ((r.get("indicators") or {}).get("quote") or [{}])
        q = quote_list[0] if quote_list else {}
        if not stamps or not q:
            return pd.DataFrame()

        df = pd.DataFrame(
            {
                "open": q.get("open"),
                "high": q.get("high"),
                "low": q.get("low"),
                "close": q.get("close"),
                "volume": q.get("volume"),
            },
            index=pd.to_datetime(stamps, unit="s", utc=True),
        )
        return YahooAdapter._clean(df)

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        df = df[~df.index.duplicated(keep="last")].sort_index()
        # Yahoo يُرجع فراغات في العطل والجلسات الناقصة — تُحذف لا تُملأ
        df = df.dropna(subset=["open", "high", "low", "close"])
        df["volume"] = df["volume"].fillna(0.0)
        return df.astype("float64")

    @staticmethod
    def _period_for(interval: str, limit: int) -> str:
        if interval in MAX_RANGE:
            return MAX_RANGE[interval]
        days = int(limit * 1.6) + 30  # هامش للعطل وأيام التعطيل
        if days <= 365:
            return f"{days}d"
        return "max" if days > 3650 else f"{days // 365 + 1}y"

    # ------------------------------------------------------------- الشبكة

    def _get(self, path: str, params: dict):
        query = urllib.parse.urlencode(params)
        last: Exception | None = None
        for host in CHART_HOSTS:
            url = f"{host}{path}?{query}"
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers=UA)
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        return json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as exc:
                    last = exc
                    if exc.code in (429, 503) and attempt < 2:
                        time.sleep(2 ** attempt)
                        continue
                    break
                except (urllib.error.URLError, TimeoutError, OSError) as exc:
                    last = exc
                    time.sleep(1)
        raise RuntimeError(
            f"تعذّر الوصول لـ Yahoo: {last}. جرّب: pip install yfinance"
        )

    # ------------------------------------------------------------- الرموز

    # ------------------------------------------------------- الأسعار الآنية

    def quotes(self, symbols: list[str]) -> dict[str, dict]:
        """آخر سعر معروف لكل رمز.

        Yahoo لا توفّر بثّاً مجانياً كبينانس، فالبديل سحب دوري من الخادم.
        مهم أن تعرف: هذه الأسعار **مؤجّلة** — عادة ربع ساعة للأسهم الأمريكية،
        وقد تكون أكثر لتداول. لا تصلح للدخول بتوقيت دقيق، تصلح للمتابعة.
        """
        if not symbols:
            return {}
        if self._yf is not None:
            out = self._quotes_yfinance(symbols)
            if out:
                return out
        return self._quotes_chart(symbols)

    def _quotes_yfinance(self, symbols: list[str]) -> dict[str, dict]:
        try:
            data = self._yf.download(
                tickers=" ".join(symbols), period="2d", interval="1d",
                progress=False, group_by="ticker", auto_adjust=False, threads=True,
            )
        except Exception:  # noqa: BLE001
            return {}
        if data is None or data.empty:
            return {}

        out: dict[str, dict] = {}
        for sym in symbols:
            try:
                frame = data[sym] if len(symbols) > 1 else data
                closes = frame["Close"].dropna()
                if closes.empty:
                    continue
                last = float(closes.iloc[-1])
                prev = float(closes.iloc[-2]) if len(closes) > 1 else last
                out[sym] = {
                    "price": last,
                    "change_pct": (last - prev) / prev * 100 if prev else None,
                }
            except (KeyError, IndexError, ValueError):
                continue
        return out

    def _quotes_chart(self, symbols: list[str], limit: int = 40) -> dict[str, dict]:
        """احتياط بلا yfinance: طلب لكل رمز، لذا نحدّ العدد."""
        out: dict[str, dict] = {}
        for sym in symbols[:limit]:
            try:
                payload = self._get(f"/v8/finance/chart/{urllib.parse.quote(sym)}",
                                    {"interval": "1d", "range": "5d"})
                meta = ((payload.get("chart") or {}).get("result") or [{}])[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if price is None:
                    continue
                out[sym] = {
                    "price": float(price),
                    "change_pct": ((float(price) - float(prev)) / float(prev) * 100)
                    if prev else None,
                }
            except Exception:  # noqa: BLE001
                continue
            time.sleep(self.pause)
        return out

    def search(self, query: str, limit: int = 12) -> list[dict]:
        """بحث Yahoo بالاسم أو الرمز — يغطي الأمريكي والسعودي معاً."""
        q = query.strip()
        if not q:
            return []
        try:
            payload = self._get("/v1/finance/search",
                                {"q": q, "quotesCount": limit, "newsCount": 0})
        except Exception:  # noqa: BLE001
            return []

        out = []
        for item in (payload or {}).get("quotes", []):
            sym = item.get("symbol")
            if not sym:
                continue
            # .SR لاحقة السوق السعودي، وما عداها نعتبره أمريكياً
            market = "saudi" if str(sym).endswith(".SR") else "us"
            out.append({
                "symbol": sym,
                "name": item.get("shortname") or item.get("longname") or sym,
                "exchange": item.get("exchange", ""),
                "type": item.get("quoteType", ""),
                "market": market,
            })
        return out[:limit]

    def usdt_universe(self, *args, **kwargs) -> list[str]:
        """لا اكتشاف تلقائي للرموز هنا — تُحدَّد في ملف الإعدادات.

        سبب ذلك: قوائم الأسهم لا تتغير يومياً كأزواج العملات، والتغطية
        تحتاج تحققاً يدوياً خصوصاً في السوق السعودي.
        """
        raise NotImplementedError(
            "محوّل Yahoo لا يكتشف الرموز تلقائياً — استخدم universe: list في الإعدادات."
        )
