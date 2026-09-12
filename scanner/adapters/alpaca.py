"""محوّل Alpaca — السوق الأمريكي بشموع داخل اليوم واكتشاف رموز تلقائي.

لماذا بديلاً عن Yahoo وليس إضافة إليه:

  • Yahoo لا يكتشف الرموز (``usdt_universe`` يرفع NotImplementedError)،
    فالسوق الأمريكي كان محبوساً في عشرة رموز مكتوبة يدوياً بينما
    الكريبتو يمسح المئات. Alpaca يعطي قائمة الأصول القابلة للتداول
    كاملة عبر ``/v2/assets``.
  • Yahoo واجهة غير رسمية تتغيّر بلا إشعار؛ هذه موثّقة ومصادَق عليها.
  • Yahoo طلب لكل رمز؛ هنا مئة رمز في طلب واحد.

═══ التغذية: أخطر قرار في هذا الملف ═══

Alpaca يقدّم تغذيتين، والفرق بينهما ليس دقّة بل **معنى**:

  sip  — كل البورصات الأمريكية عبر CTA و UTP: 100٪ من حجم السوق.
  iex  — بورصة واحدة: **~2.5٪** من حجم السوق. المجانية الوحيدة.

ومحرّك هذا المشروع مبنيّ على الحجم بالكامل: OBV و CMF و MFI و RVOL
وشمعة الحجم المنفجر. وعيّنة 2.5٪ ليست «حجماً مصغّراً» يمكن قسمته على
معامل ثابت — بل حجم **مختلف الشكل**: حصّة IEX من سهم بعينه تتقلّب
بحسب توجيه الأوامر لا بحسب نشاط السوق. فقد يظهر «حجم ×20» لأن أمراً
كبيراً واحداً صادف المرور عبر IEX، بلا أي حدث حقيقي — وهذا بالضبط ما
يبحث عنه ``breakout.detect``.

فالسياسة هنا: تُجرَّب sip أولاً، وإن رفضها الاشتراك يُنزل إلى iex
**مع إعلان صريح** يُعرض في اللوحة لا في السجلّ وحده. إخفاء هذا الفرق
كان سيجعل كل رقم حجم في النظام كذبة صامتة.

═══ تأخير الربع ساعة ═══

الخطة المجانية تمنع بيانات SIP لآخر خمس عشرة دقيقة. وهذا هنا **غير
مؤثّر تقريباً**: المشروع لا يقرّر إلا على شمعة مغلقة أصلاً، فعلى فريم
يومي لا أثر له البتّة، وعلى 15m يتأخّر القرار ربع ساعة لا أكثر.

═══ تعديل التجزئة ═══

``adjustment=split`` ليس تفصيلاً: تجزئة 10:1 تُنزل السعر 90٪ في يوم
واحد. بلا تعديل يرى المحلّل انهياراً لم يحدث، ويحسب ATR كارثياً،
وتصير كل الشموع السابقة على مقياس آخر. أمّا توزيعات الأرباح فلا
تُعدَّل: هي هبوط سعري حقيقي حدث في السوق، وتعديلها يزوّر القيعان
التي تُبنى عليها الوقفيات.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from .base import MarketAdapter

log = logging.getLogger(__name__)

DATA_HOST = "https://data.alpaca.markets"
TRADING_HOST = "https://api.alpaca.markets"
PAPER_HOST = "https://paper-api.alpaca.markets"

# فريم الماسح → صيغة Alpaca
TIMEFRAME = {
    "1m": "1Min", "5m": "5Min", "15m": "15Min", "30m": "30Min",
    "1h": "1Hour", "2h": "2Hour", "4h": "4Hour",
    "1d": "1Day", "1w": "1Week", "1M": "1Month",
}

MAX_BARS_PER_REQUEST = 10_000
# مئة رمز لكل طلب: الحدّ العملي طول المسار لا قاعدة معلنة. الرموز
# الأمريكية ≤5 محارف غالباً، فمئة رمز ≈ 700 محرف — بعيد عن أي حدّ.
SYMBOLS_PER_REQUEST = 100

UNIVERSE_TTL = 3600.0       # قائمة الأسهم لا تتغير خلال الجلسة
UA = {"User-Agent": "market-scanner/0.1"}

# البورصات المعتبرة. استبعاد OTC مقصود: التسعير هناك متقطّع والحجم
# ضئيل، فمؤشرات الحجم عليها ضجيج خالص.
EXCHANGES = {"NYSE", "NASDAQ", "ARCA", "AMEX", "BATS"}

FEED_WARNING = (
    "تغذية IEX تغطي ~2.5٪ من حجم السوق فقط. كل مؤشرات الحجم في "
    "النظام (‏OBV و CMF و MFI و RVOL ورصد الاختراق) ستقرأ عيّنة "
    "جزئية متقلّبة لا حجماً حقيقياً — عاملها كإشارة اتجاه لا كقياس. "
    "التغطية الكاملة تحتاج اشتراك Algo Trader Plus."
)


class AlpacaError(RuntimeError):
    """خطأ من Alpaca برسالة مفهومة بدل أثر HTTP خام."""


def credentials() -> tuple[str, str]:
    """المفتاح والسرّ من البيئة.

    تُقبل ثلاث تسميات، وقبولها ليس ترفاً:

    ``ALPACA_API_KEY_ID``  / ``ALPACA_API_SECRET_KEY``   — الأصل هنا
    ``APCA_API_KEY_ID``    / ``APCA_API_SECRET_KEY``     — تسمية أدوات
                                                           Alpaca الرسمية
    ``ALPACA_API_KEY``     / ``ALPACA_SECRET_KEY``       — تسمية compose

    ═══ والثالثة أُضيفت بعد عطبٍ صامت ═══

    ``docker-compose.yml`` و‎.env.docker.example‎ يمرّران
    ``ALPACA_API_KEY`` — ولم يكن يُقرأ. فكان المفتاح **موجوداً**
    في الحاوية والمحوّل يقول «غير مضبوط»، والسوق الأمريكي بصفر
    شمعة على خادمٍ كل شيءٍ فيه يبدو سليماً.

    ولم يظهر محلّياً: ‎.env‎ على الجهاز مكتوبٌ بالتسمية الأولى.
    """
    key = (os.getenv("ALPACA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
           or os.getenv("ALPACA_API_KEY") or "").strip()
    secret = (os.getenv("ALPACA_API_SECRET_KEY")
              or os.getenv("APCA_API_SECRET_KEY")
              or os.getenv("ALPACA_SECRET_KEY") or "").strip()
    return key, secret


class AlpacaAdapter(MarketAdapter):
    name = "alpaca"

    _universe_cache: tuple[float, list[str], dict[str, float]] | None = None
    # تُكتشف مرة واحدة لكل عملية: كل طلب يعيد اكتشافها يهدر طلباً من
    # حصّة مئتي طلب في الدقيقة
    _feed_detected: str | None = None
    _snapshot_feed: str | None = None

    def __init__(self, feed: str | None = None, timeout: int = 25,
                 pause: float = 0.05, retries: int = 3):
        self.timeout = timeout
        self.pause = pause
        self.retries = retries
        self.key, self.secret = credentials()
        self._feed_override = feed
        self.last_volumes: dict[str, float] = {}
        # من أين جاء الكون هذه المرّة — يُعرَض ولا يُبتلع.
        self.last_universe_note: str = ""

    # ------------------------------------------------------------ المصادقة

    def trading_host(self) -> str:
        """مضيف التداول الصحيح لهذا المفتاح — ورقي أم حقيقي.

        العطب الذي يعالجه ظهر في أول تشغيل: مفاتيح الحساب الورقي تُرفض
        بـ 401 على ``api.alpaca.markets``. الحسابان منفصلان تماماً ولكل
        منهما مضيفه، بينما **بيانات السوق مضيفها واحد للاثنين** — ولذلك
        كان الفشل محيّراً: الشموع تصل والأصول لا.

        الاستدلال بالبادئة: مفاتيح الحساب الورقي تبدأ بـ ``PK`` والحقيقي
        بـ ``AK``. وهي عادة معلنة لا عقد موثّق، فلا يُعتمد عليها وحدها —
        ``_get`` يجرّب المضيف الآخر عند 401. البادئة توفّر الطلب الضائع
        في الحالة الغالبة لا أكثر.
        """
        override = (os.getenv("ALPACA_ENDPOINT") or "").strip()
        if override:
            # يُقبل ما يُنسخ من اللوحة كما هو: .../v2 في آخره
            base = override.rstrip("/")
            return base[:-3].rstrip("/") if base.endswith("/v2") else base
        flag = (os.getenv("ALPACA_PAPER") or "").strip().lower()
        if flag in ("1", "true", "yes", "نعم"):
            return PAPER_HOST
        if flag in ("0", "false", "no", "لا"):
            return TRADING_HOST
        return PAPER_HOST if self.key.upper().startswith("PK") else TRADING_HOST

    def _headers(self) -> dict:
        if not self.key or not self.secret:
            raise AlpacaError(
                "مفاتيح Alpaca غير مضبوطة.\n"
                "  محلّياً — في ملفّ .env:\n"
                "    ALPACA_API_KEY_ID=...\n"
                "    ALPACA_API_SECRET_KEY=...\n"
                "  بدوكر — في Environment variables بالمكدّس:\n"
                "    ALPACA_API_KEY=...\n"
                "    ALPACA_SECRET_KEY=...\n"
                "تُنشأ من لوحة Alpaca ← API Keys.")
        return {**UA, "APCA-API-KEY-ID": self.key,
                "APCA-API-SECRET-KEY": self.secret,
                "Accept": "application/json"}

    # -------------------------------------------------------- كشف التغذية

    @property
    def feed(self) -> str:
        """التغذية المستعملة فعلاً — تُكتشف بطلب واحد صغير عند الحاجة."""
        if self._feed_override:
            return self._feed_override
        if AlpacaAdapter._feed_detected:
            return AlpacaAdapter._feed_detected
        AlpacaAdapter._feed_detected = self._detect_feed()
        return AlpacaAdapter._feed_detected

    def _detect_feed(self) -> str:
        """يجرّب sip بطلب أدنى؛ رفضُه يعني اشتراكاً أساسياً.

        الكشف بالتجربة لا بقراءة خطة الحساب: الخطط تتغيّر أسماؤها،
        والسؤال الحقيقي «هل يعمل sip الآن» يجيب عنه sip نفسه.
        """
        try:
            self._get(DATA_HOST, "/v2/stocks/bars",
                      {"symbols": "AAPL", "timeframe": "1Day", "limit": 1,
                       "feed": "sip"})
            log.info("تغذية Alpaca: sip — تغطية كاملة للحجم")
            return "sip"
        except AlpacaError as exc:
            if "403" in str(exc) or "subscription" in str(exc).lower():
                log.warning("تغذية Alpaca: iex — %s", FEED_WARNING)
                return "iex"
            raise
        except Exception:  # noqa: BLE001
            # تعذّر الوصول أصلاً: لا نثبّت قراراً على فشل شبكة عابر
            return "iex"

    def snapshot_feed(self) -> str:
        """تغذية لقطات الأسعار — قد تختلف عن شموع الأرشيف.

        الخطة الأساسية تقبل sip في ``/bars`` (أرشيف مؤجَّل) لكن ترفض
        ``/snapshots`` الحديثة على sip بـ 403. استخدام sip هنا يُعطي
        جدولاً فارغاً بلا خطأ ظاهر — وهذا ما كان يعطّل السوق الأمريكي.
        """
        if AlpacaAdapter._snapshot_feed:
            return AlpacaAdapter._snapshot_feed
        primary = self.feed
        try:
            self._get(DATA_HOST, "/v2/stocks/snapshots",
                      {"symbols": "AAPL", "feed": primary})
            AlpacaAdapter._snapshot_feed = primary
            return primary
        except AlpacaError as exc:
            if "403" in str(exc) or "subscription" in str(exc).lower():
                log.warning("لقطات Alpaca: sip مرفوضة — iex للأسعار الحية")
                AlpacaAdapter._snapshot_feed = "iex"
                return "iex"
            raise
        except Exception:  # noqa: BLE001
            AlpacaAdapter._snapshot_feed = "iex"
            return "iex"

    def feed_notice(self, probe: bool = False) -> dict:
        """وصف التغذية للعرض.

        ``probe=False`` هو الافتراض عمداً، وهو تصحيح لعطب حقيقي:

        كانت هذه الدالة تجسّ الشبكة عند كل استدعاء، وكانت تُستدعى من
        عرض الصفحة الرئيسية. فمع مفاتيح خاطئة أو شبكة بطيئة صار كل
        فتح للّوحة ينتظر ثلاث محاولات × 25 ثانية — **تعليق يقارب
        الدقيقة والنصف** بلا رسالة تفسّره، ثم صفحة بلا بيانات.

        القاعدة التي انتُهكت: طبقة العرض لا تنتظر الشبكة أبداً. الجسّ
        ينتمي إلى المسح حيث الانتظار متوقَّع ومحسوب، والعرض يقرأ آخر
        ما عُرف. وإن لم يُعرف بعد فالجواب «غير محدَّد» — جواب صادق
        بلا تأخير خير من جواب دقيق بعد تسعين ثانية.
        """
        current = AlpacaAdapter._feed_detected or self._feed_override
        if current is None:
            if not probe:
                return {"feed": "unknown", "partial": False, "known": False,
                        "text": "تغذية Alpaca لم تُحدَّد بعد — تظهر بعد "
                                "أول مسح للسوق الأمريكي."}
            try:
                current = self.feed
            except Exception as exc:  # noqa: BLE001
                return {"feed": "unknown", "partial": True, "known": False,
                        "text": f"تعذّر تحديد تغذية Alpaca: {str(exc)[:120]}"}
        if current == "sip":
            return {"feed": "sip", "partial": False, "known": True,
                    "text": "تغطية كاملة (SIP) — 100٪ من حجم السوق"}
        return {"feed": current, "partial": True, "known": True,
                "text": FEED_WARNING}

    # ---------------------------------------------------------------- جلب

    def fetch(self, symbol: str, timeframe: str, limit: int = 1200
              ) -> pd.DataFrame:
        frames = self.fetch_many([symbol], timeframe, limit)
        df = frames.get(symbol)
        if df is None or df.empty:
            raise AlpacaError(
                f"{symbol}: لا بيانات. تحقّق من الرمز، أو أن التاريخ "
                f"المطلوب أقدم من 2016 (بداية أرشيف Alpaca).")
        return self.validate(df.tail(limit), symbol)

    def fetch_many(self, symbols: list[str], timeframe: str,
                   limit: int = 1200, start: str | None = None
                   ) -> dict[str, pd.DataFrame]:
        """شموع عدة رموز في أقلّ عدد طلبات ممكن.

        هذه الدالة هي ما يجعل الاكتشاف التلقائي ممكناً أصلاً. الخطة
        الأساسية تسمح بمئتي طلب في الدقيقة؛ وطلبٌ لكل رمز يعني أن مسح
        ألف سهم يستغرق خمس دقائق من الانتظار الصافي. مئة رمز في الطلب
        تجعلها عشرة طلبات.
        """
        tf = TIMEFRAME.get(timeframe)
        if tf is None:
            raise AlpacaError(
                f"فريم غير مدعوم في Alpaca: {timeframe}. "
                f"المتاح: {', '.join(TIMEFRAME)}")
        symbols = [s.strip().upper() for s in symbols if s and s.strip()]
        if not symbols:
            return {}

        start = start or self._start_for(timeframe, limit)
        rows: dict[str, list[dict]] = {}

        for i in range(0, len(symbols), SYMBOLS_PER_REQUEST):
            batch = symbols[i:i + SYMBOLS_PER_REQUEST]
            token: str | None = None
            while True:
                params = {
                    "symbols": ",".join(batch),
                    "timeframe": tf,
                    "start": start,
                    "limit": MAX_BARS_PER_REQUEST,
                    "adjustment": "split",
                    "feed": self.feed,
                    "sort": "asc",
                }
                if token:
                    params["page_token"] = token
                payload = self._get(DATA_HOST, "/v2/stocks/bars", params)
                for sym, bars in (payload.get("bars") or {}).items():
                    rows.setdefault(sym, []).extend(bars or [])
                token = payload.get("next_page_token")
                if not token:
                    break
                time.sleep(self.pause)

        out: dict[str, pd.DataFrame] = {}
        for sym, bars in rows.items():
            df = self.to_frame(bars, timeframe)
            if not df.empty:
                out[sym] = df.tail(limit)
        return out

    @staticmethod
    def to_frame(bars: list[dict], timeframe: str,
                 now: pd.Timestamp | None = None) -> pd.DataFrame:
        """استجابة Alpaca الخام ← الشكل الموحّد، بلا الشمعة الجارية.

        مفصولة عن الشبكة عمداً حتى تُختبر على حمولة حقيقية بلا اتصال.

        حذف الشمعة الجارية ليس تحسيناً بل شرط صحّة: القرار على شمعة لم
        تُغلق يعيد رسم نفسه — تبدو الإشارة ناجحة في الماضي وحده. وهذه
        قاعدة المشروع كله.
        """
        if not bars:
            return pd.DataFrame()
        df = pd.DataFrame(bars)
        needed = {"t", "o", "h", "l", "c", "v"}
        if not needed <= set(df.columns):
            return pd.DataFrame()

        df = df.rename(columns={"t": "time", "o": "open", "h": "high",
                                "l": "low", "c": "close", "v": "volume"})
        df["time"] = pd.to_datetime(df["time"], utc=True, format="ISO8601")
        df = df.set_index("time")
        df = df[~df.index.duplicated(keep="last")].sort_index()

        seconds = _timeframe_seconds(timeframe)
        if seconds and len(df):
            now = now if now is not None else pd.Timestamp.now("UTC")
            if now.tzinfo is None:
                now = now.tz_localize("UTC")
            closes_at = df.index + pd.Timedelta(seconds=seconds)
            df = df[closes_at <= now]

        cols = ["open", "high", "low", "close", "volume"]
        return df[cols].astype("float64") if len(df) else pd.DataFrame()

    @staticmethod
    def _start_for(timeframe: str, limit: int) -> str:
        """أقدم تاريخ نطلبه — بهامش يغطي العطل وأيام الإغلاق.

        السوق الأمريكي يفتح ~252 يوماً في السنة و6.5 ساعة يومياً، فعدد
        الشموع التقويمية أكبر بكثير من المتداولة. الهامش هنا سخيّ لأن
        النقص أسوأ من الزيادة: إطار قصير يُعطّل EMA200 وفلتر الفريم
        الأعلى فتُحجب الإشارات بلا سبب ظاهر.
        """
        seconds = _timeframe_seconds(timeframe) or 86400
        if seconds >= 86400:
            days = int(limit * 1.55) + 40          # 5/7 أيام تداول + عطل
        else:
            bars_per_day = max(1, int(6.5 * 3600 / seconds))
            days = int(limit / bars_per_day * 1.55) + 10
        start = pd.Timestamp.now("UTC") - pd.Timedelta(days=min(days, 3650))
        # 2016 بداية أرشيف Alpaca — طلب ما قبلها يعيد فراغاً لا خطأ
        floor = pd.Timestamp("2016-01-01", tz="UTC")
        return max(start, floor).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -------------------------------------------------------------- الرموز

    def usdt_universe(self, min_quote_volume: float = 20_000_000,
                      top_n: int | None = None,
                      diagnose: bool = False) -> list[str]:
        """الأسهم القابلة للتداول مرتّبة بحجم التداول الدولاري.

        الاسم موروث من عقد ``MarketAdapter`` الذي وُضع للكريبتو. ويُترك
        كما هو عمداً: تغييره يعني تعديل كل محوّل والمسح معاً لأجل
        تسمية، والعقد الموحّد هو ما يجعل إضافة سوق جديد ملفاً واحداً.

        الحجم يُحسب من الشموع اليومية لا من نداء جاهز: Alpaca لا يعطي
        «حجم 24 ساعة» كبينانس. ومتوسط عشرين يوماً لا يوم واحد — يوم
        الأرباح وحده يضاعف حجم السهم، فترتيبٌ على يوم واحد يعيد ترتيب
        السوق كل صباح.
        """
        from scanner import universe_cache as ucache

        self.last_universe_note = ""
        now = time.time()
        cached = AlpacaAdapter._universe_cache
        if cached and (now - cached[0]) < UNIVERSE_TTL:
            symbols, volumes = cached[1], cached[2]
        else:
            # ═══ القرص قبل الشبكة ═══
            #
            # ``_universe_cache`` متغيّر صنف — يعيش في الرام ويموت مع
            # العمليّة. وكل أمر سطر أوامر عمليّةٌ جديدة، فكان الحساب
            # الثقيل يُعاد في كل نداء: اثنا عشر ألفاً وخمسمئة أصل،
            # لكلٍّ شموع عشرين يوماً. فأرهقنا Alpaca بأنفسنا حتى
            # ردّت ``429``، وسقط الاكتشاف إلى عشرة رموز.
            disk = ucache.fresh_symbols(self.name)
            if disk:
                symbols, volumes = disk
                self.last_universe_note = (
                    f"من الكون المحفوظ ({ucache.describe(self.name)})")
            else:
                try:
                    symbols, volumes = self._compute_universe(diagnose=diagnose)
                    ucache.save(self.name, symbols, volumes)
                except Exception as exc:  # noqa: BLE001
                    # ═══ الدرجة الوسطى في السلّم ═══
                    #
                    # كان النزول من «اكتشاف فاشل» إلى «عشرة رموز في
                    # الملف» مباشرةً — بينما على القرص كونٌ كامل
                    # اكتُشف قبل ساعات. ورمي أربعمئة رمز معروف لأجل
                    # ``429`` عابر خسارةٌ بلا مقابل.
                    stale = ucache.load(self.name)      # مهما قدُم
                    if not stale:
                        raise
                    symbols = list(stale["symbols"])
                    volumes = dict(stale.get("volumes") or {})
                    self.last_universe_note = (
                        f"تعذّر الاكتشاف الحيّ ({str(exc)[:70]}) — "
                        f"استُعمل الكون المحفوظ: {ucache.describe(self.name)}")
            AlpacaAdapter._universe_cache = (now, symbols, volumes)

        kept = [(s, volumes.get(s, 0.0)) for s in symbols
                if volumes.get(s, 0.0) >= min_quote_volume]
        kept.sort(key=lambda p: p[1], reverse=True)

        if diagnose:
            print(f"\n  أصول قابلة للتداول: {len(symbols)}")
            print(f"  فوق عتبة {min_quote_volume:,.0f}$: {len(kept)}")
            for sym, qv in kept[:10]:
                print(f"    {sym:8} {qv:>18,.0f}$")

        self.last_volumes = dict(kept)
        out = [s for s, _ in kept]
        return out[:top_n] if top_n else out

    def _compute_universe(self, diagnose: bool = False
                          ) -> tuple[list[str], dict[str, float]]:
        assets = self.assets()
        symbols = [a["symbol"] for a in assets]
        volumes: dict[str, float] = {}

        # عشرون يوماً تقويمياً ≈ أربعة عشر يوم تداول — كافٍ لمتوسط
        # مستقرّ وصغير بما يكفي ألّا يثقل الطلب
        start = (pd.Timestamp.now("UTC") - pd.Timedelta(days=30)
                 ).strftime("%Y-%m-%dT%H:%M:%SZ")
        frames = self.fetch_many(symbols, "1d", limit=20, start=start)
        for sym, df in frames.items():
            if df.empty:
                continue
            tail = df.tail(20)
            volumes[sym] = float((tail["close"] * tail["volume"]).mean())

        if diagnose:
            print(f"  حُسب الحجم لـ {len(volumes)} من {len(symbols)}")
        return symbols, volumes

    def assets(self) -> list[dict]:
        """الأسهم وصناديق المؤشرات القابلة للتداول في البورصات الكبرى."""
        raw = self._get(self.trading_host(), "/v2/assets",
                        {"status": "active", "asset_class": "us_equity"})
        out = []
        for a in raw or []:
            if not a.get("tradable"):
                continue
            if a.get("exchange") not in EXCHANGES:
                continue
            sym = (a.get("symbol") or "").strip().upper()
            # الرموز ذات النقطة أو الشرطة (فئات الأسهم ووحدات SPAC)
            # ترجع بيانات متقطّعة، وتكسر أسماء الملفات على ويندوز
            if not sym or not sym.isalpha():
                continue
            out.append({"symbol": sym,
                        "name": a.get("name") or sym,
                        "exchange": a.get("exchange", ""),
                        "fractionable": bool(a.get("fractionable"))})
        return out

    def quote_volumes(self) -> dict[str, float]:
        """أحجام دولارية من آخر نداء لـ usdt_universe — قد تكون فارغة."""
        return dict(self.last_volumes)

    def search(self, query: str, limit: int = 12) -> list[dict]:
        """بحث بالرمز أو الاسم في قائمة الأصول المخزّنة مؤقتاً."""
        q = query.strip().upper()
        if not q:
            return []
        try:
            assets = self.assets()
        except Exception:  # noqa: BLE001
            return []

        exact, starts, contains = [], [], []
        for a in assets:
            sym, name = a["symbol"], a["name"].upper()
            if sym == q:
                exact.append(a)
            elif sym.startswith(q) or name.startswith(q):
                starts.append(a)
            elif q in name:
                contains.append(a)
        ordered = exact + starts + contains
        return [{"symbol": a["symbol"], "name": a["name"],
                 "exchange": a["exchange"], "type": "EQUITY", "market": "us"}
                for a in ordered[:limit]]

    # ------------------------------------------------------- الأسعار الآنية

    def quotes(self, symbols: list[str]) -> dict[str, dict]:
        """آخر سعر معروف — للعرض والمتابعة لا للحسم.

        الحسم يبقى من الشموع المغلقة حصراً في كل هذا المشروع: عيّنة كل
        بضع دقائق تُفوّت الفتيل الذي يلمس الوقف ثم يرتدّ، فتقلب خسارة
        حقيقية ربحاً في السجل.

        وعلى الخطة الأساسية هذه الأسعار من IEX أو مؤجَّلة ربع ساعة.
        """
        if not symbols:
            return {}
        out: dict[str, dict] = {}
        feed = self.snapshot_feed()
        for i in range(0, len(symbols), SYMBOLS_PER_REQUEST):
            batch = symbols[i:i + SYMBOLS_PER_REQUEST]
            try:
                payload = self._get(DATA_HOST, "/v2/stocks/snapshots",
                                    {"symbols": ",".join(batch),
                                     "feed": feed})
            except Exception:  # noqa: BLE001
                continue
            out.update(self.parse_snapshots(payload))
        return out

    @staticmethod
    def parse_snapshots(payload: dict) -> dict[str, dict]:
        """لقطات ← {رمز: {price, change_pct}}. مفصولة للاختبار بلا شبكة."""
        snaps = (payload or {}).get("snapshots") or payload or {}
        out: dict[str, dict] = {}
        for sym, snap in snaps.items():
            if not isinstance(snap, dict):
                continue
            trade = snap.get("latestTrade") or {}
            minute = snap.get("minuteBar") or {}
            daily = snap.get("dailyBar") or {}
            prev = snap.get("prevDailyBar") or {}
            price = trade.get("p") or minute.get("c") or daily.get("c")
            if price is None:
                continue
            base = prev.get("c") or daily.get("o")
            try:
                price = float(price)
                change = ((price - float(base)) / float(base) * 100
                          if base else None)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            out[sym] = {"price": price, "change_pct": change}
        return out

    # -------------------------------------------------------------- الشبكة

    @staticmethod
    def _other_host(host: str) -> str | None:
        """المضيف المقابل — للتداول فقط. بيانات السوق مضيفها واحد."""
        if host == TRADING_HOST:
            return PAPER_HOST
        if host == PAPER_HOST:
            return TRADING_HOST
        return None

    def _get(self, host: str, path: str, params: dict,
             _tried_alt: bool = False):
        query = urllib.parse.urlencode(params)
        url = f"{host}{path}" + (f"?{query}" if query else "")
        headers = self._headers()
        delay = 1.0
        last: Exception | None = None

        for attempt in range(self.retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last = exc
                body = _safe_body(exc)
                if exc.code == 401:
                    # الحساب الورقي والحقيقي مضيفان منفصلان، ومفتاح
                    # أحدهما يُرفض على الآخر. نجرّب البديل مرة واحدة
                    # قبل الاستسلام: الاستدلال بالبادئة عادة لا عقد.
                    other = self._other_host(host)
                    if other and not _tried_alt:
                        return self._get(other, path, params,
                                         _tried_alt=True)
                    raise AlpacaError(
                        f"مفاتيح Alpaca مرفوضة (401) على {host}.\n"
                        "الأسباب الشائعة بالترتيب:\n"
                        "  • مفتاح حساب ورقي (يبدأ بـ PK) على مضيف "
                        "الحساب الحقيقي أو العكس — أضف "
                        "ALPACA_PAPER=1 إلى .env للورقي.\n"
                        "  • السرّ ناقص: لوحة Alpaca تعرضه مرة واحدة "
                        "فقط، فالنسخ الجزئي شائع.\n"
                        "  • مفاتيح Broker بدل مفاتيح التداول."
                    ) from exc
                if exc.code == 403:
                    raise AlpacaError(f"403 subscription: {body}") from exc
                if exc.code == 429 and attempt < self.retries - 1:
                    # مئتا طلب في الدقيقة على الخطة الأساسية — التباعد
                    # التصاعدي أرخص من فقدان المسح كله
                    time.sleep(delay)
                    delay *= 3
                    continue
                if exc.code >= 500 and attempt < self.retries - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise AlpacaError(f"Alpaca {exc.code}: {body}") from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = exc
                if attempt == self.retries - 1:
                    break
                time.sleep(delay)
                delay *= 2

        raise AlpacaError(f"تعذّر الوصول لـ Alpaca: {last}")


def _safe_body(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:200]
    except Exception:  # noqa: BLE001
        return str(exc)[:200]


def _timeframe_seconds(timeframe: str) -> int:
    try:
        from ..live import timeframe_seconds

        return int(timeframe_seconds(timeframe) or 0)
    except Exception:  # noqa: BLE001
        return 0
