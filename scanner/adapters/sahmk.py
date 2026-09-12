# -*- coding: utf-8 -*-
"""محوّل سهمك — بيانات السوق السعودي (تاسي ونمو).

المرجع: https://www.sahmk.sa/developers/docs

    الأساس      https://api.sahmk.sa/api/v1
    المصادقة    ترويسة ``X-API-Key``
    الشركات     GET /companies/?market=TASI&limit=&offset=      (مجاني)
    التاريخية   GET /historical/{رمز}/?interval=&from=&to=&limit=&offset=
    الأسعار     GET /quotes/?symbols=2222,1120

═══ الفريمات: ما يتوفّر وما لا يتوفّر ═══

سهمك تعطي ``1d`` و``1w`` و``1m`` و``60m`` و``30m``. والمنصّة تعمل على
``15m`` و``1h`` و``4h`` و``1d`` و``1w``. فالمطابقة:

    1h  →  60m         مباشرة
    1d  →  1d          مباشرة
    1w  →  1w          مباشرة
    4h  →  60m ثمّ تجميع أربع ساعات
    15m →  **غير متاح**

و``15m`` تُرفَض برسالة صريحة لا بإرجاع فريم آخر. لأن إعطاء شموع ساعة
لمن طلب ربع ساعة يُنتج إشارات مبنيّة على زمن غير الذي ظنّه — وهو خطأ
صامت أسوأ من رسالة واضحة.

═══ الباقات ═══

    Free        لا بيانات تاريخية إطلاقاً
    Starter     1d · 1w · 1m
    Pro         + 60m حتى 90 يوماً
    Business    + 30m حتى 6 أشهر · 60m حتى سنة
    Enterprise  حسب الاتفاق

فـ``1h`` و``4h`` يحتاجان **Pro فأعلى**. وتجاوز حدّ الباقة يعيد
``403 PLAN_LIMIT``، ويُترجَم هنا إلى رسالة تقول أي باقة يلزم بدل رقم
خطأ غامض.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import pandas as pd

from .base import MarketAdapter

log = logging.getLogger(__name__)

BASE_URL = "https://api.sahmk.sa/api/v1"

# فريمات المنصّة ← فريمات سهمك. القيمة ``None`` تعني «لا يوجد مقابل».
TIMEFRAME: dict[str, str | None] = {
    "15m": None,        # سهمك تبدأ من 30m، ولا تجميع يُنتج ربع ساعة
    "30m": "30m",
    "1h": "60m",
    "4h": "60m",        # يُجمَّع من الساعة — انظر ``_RESAMPLE``
    "1d": "1d",
    "1w": "1w",
}

# فريمات تُبنى بالتجميع من فريم أصغر
_RESAMPLE: dict[str, str] = {"4h": "4h"}

# الحدّ الأقصى للصفوف في الطلب الواحد حسب التوثيق
MAX_LIMIT = 2000
PAGE_LIMIT = 2000

# مهلة الشبكة. الطلب الذي لا يعود لا يجوز أن يشغل خيطاً إلى الأبد —
# درسٌ تكرّر في هذا المشروع.
TIMEOUT = 25

# الباقة الدنيا لكل فريم — للرسالة لا للمنع. المنع من الخادم.
_PLAN_FOR: dict[str, str] = {
    "1d": "Starter", "1w": "Starter", "1m": "Starter",
    "60m": "Pro", "30m": "Business",
}

# قائمة الرموز لا تتغيّر خلال الجلسة؛ إعادة جلبها في كل مسح هدر.
UNIVERSE_TTL = 3600.0


def api_symbol(symbol: str) -> str:
    """رمز المنصّة ← رمز سهمك.

    ═══ لماذا ═══

    تاريخك المخزَّن تحت ``2222.SR`` (لاحقة ياهو)، وسهمك تستعمل ``2222``
    مجرّداً. وتبديل المحوّل بلا مطابقة يعني أن كل شمعة محفوظة تصير
    يتيمة — يُعاد تنزيل التاريخ كلّه، ويُقطَع الربط بالصفقات القديمة.

    فالمحوّل يقبل الصيغتين ويرسل المجرّدة. والمنصّة تُبقي أسماءها كما
    هي، فلا يُلمَس شيء من المخزون.
    """
    sym = str(symbol or "").strip().upper()
    for suffix in (".SR", ".SAU", ".TADAWUL"):
        if sym.endswith(suffix):
            return sym[: -len(suffix)]
    return sym


def local_symbol(symbol: str) -> str:
    """رمز سهمك ← رمز المنصّة — عكس :func:`api_symbol`.

    الصيغة المحلّية للسوق السعودي ``NNNN.SR``: هي ما على القرص، وما
    في القائمة الاحتياطية، وما يفهمه ياهو. وسهمك تُعيد ``2222``
    مجرّداً، فبلا هذا التحويل يُكتشَف السوق بأسماء لا يعرفها بقيّة
    النظام.
    """
    sym = str(symbol or "").strip().upper()
    if not sym:
        return ""
    if any(sym.endswith(s) for s in (".SR", ".SAU", ".TADAWUL")):
        return sym
    return f"{sym}.SR" if sym.isdigit() else sym


class SahmkError(RuntimeError):
    """خطأ من واجهة سهمك، برسالة عربية مفهومة."""


class SahmkAdapter(MarketAdapter):
    name = "sahmk"

    _universe_cache: tuple[float, list[str], dict[str, float]] | None = None

    def __init__(self, api_key: str = "", timeout: int = TIMEOUT) -> None:
        self.api_key = (api_key or self._key_from_settings()).strip()
        self.timeout = timeout
        self.last_volumes: dict[str, float] = {}
        # سبب تعذّر الترتيب إن تعذّر — يُعرَض ولا يُبتلع.
        self.last_universe_note: str = ""

    # ───────────────────────────────────────────── المفاتيح

    @staticmethod
    def _key_from_settings() -> str:
        """المفتاح من الإعدادات إن وُجد، وإلّا من البيئة.

        النمط نفسه الذي يتبعه محوّل Alpaca: المصدر العملي اليوم هو
        ملفّ ``.env``. والقراءة من الإعدادات مُهيَّأة سلفاً فإن أُضيف
        الحقل إلى صفحة الإعدادات عمل بلا تعديل هنا — والأسبقية له،
        وإلّا صار ضبطه في الواجهة بلا أثر.
        """
        try:
            from web.dashboard import appsettings  # type: ignore

            key = (appsettings.get("sahmk_api_key", "") or "").strip()
            if key:
                return key
        except Exception:  # noqa: BLE001
            pass
        return os.getenv("SAHMK_API_KEY", "")

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise SahmkError(
                "مفتاح سهمك غير مضبوط. أضفه في صفحة الإعدادات أو في "
                "متغيّر البيئة SAHMK_API_KEY — احصل عليه من "
                "https://www.sahmk.sa/developers/register")
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    # ───────────────────────────────────────────── الشبكة

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v not in (None, "")})
        url = f"{BASE_URL}{path}" + (f"?{query}" if query else "")
        req = urllib.request.Request(url, headers=self._headers())

        # تجاوز الوسيط للنداءات الصادرة: ``urllib`` يقرأ متغيّرات
        # البيئة ويوجّه عبر وسيط قد لا يكون مقصوداً — وهو ما عطّل
        # Ollama في هذا المشروع من قبل.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler(urllib.request.getproxies()))
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._translate(exc, path) from exc
        except urllib.error.URLError as exc:
            raise SahmkError(
                f"تعذّر الوصول إلى سهمك: {getattr(exc, 'reason', exc)}") from exc

    @staticmethod
    def _translate(exc: urllib.error.HTTPError, path: str) -> SahmkError:
        """يحوّل خطأ HTTP إلى رسالة تقول ما يُفعَل.

        «403» وحدها لا تقول شيئاً. والفرق بين مفتاح خاطئ وباقة لا تكفي
        هو الفرق بين علاجين مختلفين تماماً.
        """
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = {}
        code = str(body.get("code") or body.get("error") or "")
        detail = str(body.get("detail") or body.get("message") or "")[:160]

        if exc.code == 401:
            return SahmkError("مفتاح سهمك مرفوض (401) — تحقّق منه في الإعدادات.")
        if exc.code == 403:
            if "PLAN" in code.upper():
                return SahmkError(
                    f"باقة سهمك لا تشمل هذا الطلب (PLAN_LIMIT): {detail or path}. "
                    "الفريمات داخل اليوم تحتاج Pro فأعلى، والتاريخية "
                    "تحتاج Starter فأعلى.")
            return SahmkError(f"طلب مرفوض من سهمك (403): {detail or path}")
        if exc.code == 404:
            return SahmkError(f"غير موجود في سهمك: {path}")
        if exc.code == 429:
            return SahmkError(
                "تجاوزتَ حدّ الطلبات في سهمك (429) — أبطئ المسح أو ارفع الباقة.")
        return SahmkError(f"خطأ من سهمك ({exc.code}): {detail or path}")

    # ───────────────────────────────────────────── الشموع

    def fetch(self, symbol: str, timeframe: str, limit: int = 1200) -> pd.DataFrame:
        """آخر ``limit`` شمعة مغلقة."""
        if timeframe not in TIMEFRAME:
            raise SahmkError(
                f"فريم غير معروف: {timeframe}. "
                f"المتاح: {', '.join(k for k, v in TIMEFRAME.items() if v)}")
        native = TIMEFRAME[timeframe]
        if native is None:
            raise SahmkError(
                f"سهمك لا توفّر فريم {timeframe} — أصغر فريم لديها 30m. "
                "استعمل 1h أو 4h أو 1d.")

        # التجميع يحتاج شموعاً أكثر: أربع ساعات لكل شمعة أربع ساعات
        factor = 4 if timeframe == "4h" else 1
        rows = self._history(api_symbol(symbol), native, limit * factor + factor)
        if not rows:
            raise SahmkError(f"لا بيانات تاريخية لـ{symbol} على {timeframe}")

        df = self._to_frame(rows, symbol)
        if timeframe in _RESAMPLE:
            df = self._resample(df, _RESAMPLE[timeframe])
        df = self.validate(df, symbol)
        return df.tail(limit)

    def _history(self, symbol: str, interval: str, need: int) -> list[dict]:
        """صفحات ``/historical`` حتى يكتمل المطلوب.

        الترقيم بـ``offset`` لا بالتواريخ: التوثيق يضمن ``has_more``
        و``total``، وهما أوثق من حساب نافذة زمنية على سوق له عطل
        وإجازات — فالتقويم لا يخبرنا كم شمعة تداول فيه.
        """
        out: list[dict] = []
        offset = 0
        pages = 0
        while len(out) < need and pages < 12:
            payload = self._get(f"/historical/{symbol}/", {
                "interval": interval,
                "limit": min(PAGE_LIMIT, MAX_LIMIT),
                "offset": offset,
            })
            data = (payload or {}).get("data") or []
            if not data:
                break
            out.extend(data)
            pages += 1
            if not payload.get("has_more"):
                break
            offset += len(data)
        return out

    @staticmethod
    def _to_frame(rows: list[dict], symbol: str) -> pd.DataFrame:
        """صفوف سهمك ← إطار المنصّة.

        الطابع قد يصل ``date`` (يومي) أو ``datetime``/``timestamp``
        (داخل اليوم). ويُوحَّد إلى UTC لأن كل التخزين والحسم في هذا
        المشروع على UTC — واختلاف المنطقة بين مصدرين هو أصل أعطاب
        صامتة في المقارنات الزمنية.
        """
        stamps, o, h, low, c, v = [], [], [], [], [], []
        for r in rows:
            raw = r.get("datetime") or r.get("timestamp") or r.get("date")
            if raw is None:
                continue
            ts = pd.to_datetime(raw, errors="coerce", utc=True)
            if ts is pd.NaT:
                continue
            stamps.append(ts)
            o.append(r.get("open"))
            h.append(r.get("high"))
            low.append(r.get("low"))
            c.append(r.get("close"))
            v.append(r.get("volume", 0) or 0)

        if not stamps:
            raise SahmkError(f"صفوف سهمك بلا طوابع صالحة لـ{symbol}")

        df = pd.DataFrame(
            {"open": o, "high": h, "low": low, "close": c, "volume": v},
            index=pd.DatetimeIndex(stamps, name="open_time"),
        )
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df.astype("float64")

    @staticmethod
    def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
        """يجمّع شموعاً أصغر إلى أكبر.

        الشمعة الأخيرة تُحذف إن كانت ناقصة: التجميع لا يعرف أن الفترة
        انتهت، فيُنتج شمعة «مفتوحة» تتغيّر بعد قليل. والقرار عليها هو
        إعادة الرسم بعينها — وهي قاعدة محفوظة في هذا المشروع.
        """
        agg = df.resample(rule, label="left", closed="left").agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        }).dropna(subset=["open", "close"])

        if len(agg) == 0:
            return agg
        step = pd.Timedelta(rule)

        # ═══ الطرفان كلاهما قد يكون ناقصاً ═══
        #
        # ‏pandas يثبّت السلال على منتصف الليل بالتوقيت العالمي، وجلسة
        # تاسي تبدأ الساعة 07:00 UTC. فأوّل سلّة تضمّ ساعةً أو اثنتين
        # فقط من فترتها، وآخر سلّة قد تكون جارية.
        #
        # وكلاهما شمعة **ناقصة**: الأولى تبدو بمدى ضيّق فتُنتج إشارة
        # اختراق كاذبة، والأخيرة تتغيّر بعد قليل فالقرار عليها إعادة
        # رسم. فتُحذفان.
        if len(agg) and df.index[0] > agg.index[0] + pd.Timedelta(seconds=1):
            agg = agg.iloc[1:]
        if len(agg) and df.index[-1] < agg.index[-1] + step - pd.Timedelta(seconds=1):
            agg = agg.iloc[:-1]
        return agg

    # ───────────────────────────────────────────── الكون

    def companies(self, market: str = "") -> list[dict]:
        """الشركات النشطة — أسهم فقط، بلا صكوك ولا صناديق."""
        out: list[dict] = []
        # رمز واحد قد يظهر في أكثر من سوق أو صفحة. وتكراره يضاعف
        # الطلبات ويُدخل الرمز مرّتين في الكون — أي وزناً مضاعفاً في
        # كل إحصاء لاحق.
        seen: set[str] = set()
        for mk in ([market] if market else ["TASI", "NOMU"]):
            offset = 0
            while True:
                payload = self._get("/companies/", {
                    "market": mk, "limit": 200, "offset": offset,
                })
                rows = (payload or {}).get("results") or []
                if not rows:
                    break
                for r in rows:
                    if str(r.get("status", "")).lower() != "active":
                        continue
                    # الصكوك والصناديق تُستبعَد: تحليل فنّي على أداة
                    # دخل ثابت لا معنى له، وإدراجها يُلوّث الإحصاءات
                    if str(r.get("security_type", "Equity")) != "Equity":
                        continue
                    if r.get("is_etf"):
                        continue
                    # الصيغة المحلّية لا صيغة المنصّة: تاريخك مخزَّن
                    # تحت ``2222.SR``، وياهو لا يعرف ``2222`` مجرّداً.
                    # إعادة الرمز خاماً كانت ستجعل كل شمعة محفوظة
                    # يتيمة، وتقطع الربط بالصفقات القديمة.
                    sym = local_symbol(str(r.get("symbol") or "").strip())
                    if sym and sym not in seen:
                        seen.add(sym)
                        out.append({
                            "symbol": sym,
                            "name": r.get("name_ar") or r.get("name_en") or sym,
                            "market": r.get("market") or mk,
                        })
                offset += len(rows)
                if offset >= int(payload.get("count") or 0):
                    break
        return out

    def quotes(self, symbols: list[str]) -> dict[str, dict]:
        """أسعار لحظية مجمَّعة — طلب واحد لكل خمسين رمزاً."""
        out: dict[str, dict] = {}
        for i in range(0, len(symbols), 50):
            batch = [api_symbol(s) for s in symbols[i:i + 50]]
            try:
                payload = self._get("/quotes/", {"symbols": ",".join(batch)})
            except SahmkError as exc:
                log.debug("تعذّر جلب أسعار سهمك: %s", str(exc)[:100])
                continue
            rows = payload if isinstance(payload, list) else (
                payload.get("results") or payload.get("data") or [])
            for r in rows:
                # المفاتيح بالصيغة المحلّية كي تطابق ما تعيده
                # ``companies`` — وإلّا لم يجد ``usdt_universe`` حجماً
                # لأي رمز، فرتّب السوق كلّه على أصفار.
                sym = local_symbol(str(r.get("symbol") or "").strip())
                if not sym:
                    continue
                out[sym] = {
                    "price": r.get("price"),
                    "change_pct": r.get("change_percent"),
                    "volume": r.get("volume"),
                }
        return out

    def usdt_universe(self, min_quote_volume: float = 0.0,
                      top_n: int | None = None,
                      diagnose: bool = False) -> list[str]:
        """الرموز مرتّبة بحجم التداول الريالي.

        الاسم موروث من عقد ``MarketAdapter`` الموضوع للكريبتو، ويُترك
        كما هو: توحيد العقد هو ما يجعل إضافة سوق ملفاً واحداً.
        """
        from scanner import universe_cache as ucache

        now = time.time()
        cached = SahmkAdapter._universe_cache
        ranked = True
        disk = None if cached else ucache.fresh_symbols(self.name)
        if cached and (now - cached[0]) < UNIVERSE_TTL:
            symbols, volumes = cached[1], cached[2]
            ranked = bool(volumes)
        elif disk:
            # القرص قبل الشبكة: الذاكرة في الرام تموت مع العمليّة،
            # وكل أمر سطر أوامر عمليّةٌ جديدة.
            symbols, volumes = disk
            ranked = bool(volumes)
            self.last_universe_note = (
                f"من الكون المحفوظ ({ucache.describe(self.name)})")
        else:
            try:
                rows = self.companies()
            except Exception as exc:  # noqa: BLE001
                stale = ucache.load(self.name)          # مهما قدُم
                if not stale:
                    raise
                SahmkAdapter._universe_cache = (
                    now, list(stale["symbols"]), dict(stale.get("volumes") or {}))
                self.last_universe_note = (
                    f"تعذّر الاكتشاف الحيّ ({str(exc)[:70]}) — "
                    f"استُعمل الكون المحفوظ: {ucache.describe(self.name)}")
                out = list(stale["symbols"])
                self.last_volumes = dict(stale.get("volumes") or {})
                return out[:top_n] if top_n else out
            symbols = [r["symbol"] for r in rows]

            # ═══ لماذا لا يُسقط فشلُ الترتيب الاكتشافَ ═══
            #
            # ‏``/companies/`` مجاني و‏``/quotes/`` يحتاج Starter فأعلى.
            # وكان النداءان في مسار واحد بلا حاجز، فكان الحساب المجاني
            # يحصل على قائمة الشركات كاملةً ثمّ يفقدها كلّها عند سطر
            # الترتيب: ``403 PLAN_LIMIT`` يصعد فيُسقط الاكتشاف، ويرتدّ
            # النظام إلى عشرة رموز مكتوبة في ملف الإعداد.
            #
            # وهذا خلطٌ بين سؤالين: **من في السوق؟** و**من الأنشط؟**
            # الأوّل مجاني والثاني ليس كذلك. وحين يتعذّر الثاني فالجواب
            # الصحيح هو السوق كلّه بلا ترتيب — لا عشرة رموز.
            volumes: dict[str, float] = {}
            try:
                quotes = self.quotes(symbols)
                for sym, q in quotes.items():
                    try:
                        volumes[sym] = float(q.get("price") or 0) * \
                            float(q.get("volume") or 0)
                    except (TypeError, ValueError):
                        continue
            except Exception as exc:  # noqa: BLE001
                ranked = False
                self.last_universe_note = (
                    "تعذّر ترتيب الرموز بالحجم (‎/quotes/‎ يحتاج باقة "
                    f"Starter فأعلى) — أُدرج السوق كاملاً بلا ترتيب: {exc}"
                )
            SahmkAdapter._universe_cache = (now, symbols, volumes)
            ucache.save(self.name, symbols, volumes)

        if ranked and volumes:
            kept = [(s, volumes.get(s, 0.0)) for s in symbols
                    if volumes.get(s, 0.0) >= min_quote_volume]
            kept.sort(key=lambda p: p[1], reverse=True)
        else:
            # بلا أحجام لا تُطبَّق عتبة الحجم: تطبيقها على أصفار
            # يحذف السوق كلّه. عتبةٌ على بيانات غائبة ليست تصفية بل
            # محو.
            kept = [(s, 0.0) for s in symbols]

        if diagnose:
            print(f"\n  شركات نشطة: {len(symbols)}")
            if ranked and volumes:
                print(f"  فوق عتبة {min_quote_volume:,.0f} ريال: {len(kept)}")
                for sym, qv in kept[:10]:
                    print(f"    {sym:8} {qv:>18,.0f}")
            else:
                print("  الترتيب بالحجم متعذّر — السوق كاملاً بلا ترتيب")
                print(f"  {getattr(self, 'last_universe_note', '')}")

        self.last_volumes = dict(kept)
        out = [s for s, _ in kept]
        return out[:top_n] if top_n else out

    def quote_one(self, symbol: str) -> dict:
        """سعر شركة واحدة — ‎/quote/{symbol}/‎ متاح للباقة المجانية.

        ‏``/quotes/`` المجمَّع يحتاج Starter، والتوثيق يذكر هذا بديلاً
        صريحاً للمجانية. الثمن أنّه طلبٌ لكل رمز: ثلاثمئة طلب للسوق
        كلّه — مقبولٌ لعمليّة تُجرى مرّةً في اليوم، لا في كل مسح.
        """
        payload = self._get(f"/quote/{api_symbol(symbol)}/")
        row = payload if isinstance(payload, dict) else {}
        row = row.get("quote") or row.get("data") or row
        return {
            "price": row.get("price") or row.get("last"),
            "change_pct": row.get("change_percent") or row.get("change_pct"),
            "volume": row.get("volume"),
        }

    def company_info(self, symbol: str) -> dict:
        """ملفّ الشركة — الوصفيّ مجاني والأساسيات تحتاج Starter.

        لا يرمي عند نقص الباقة: يعيد ما توفّر ويترك الباقي ``None``.
        الصفر رقمٌ يُحسب عليه، والغياب حالةٌ تُعرَض — وتصفيرُ مكرّر
        ربحيةٍ غائب يجعل السهم يبدو رخيصاً بلا حدّ.
        """
        out: dict[str, Any] = {}
        try:
            payload = self._get(f"/company/{api_symbol(symbol)}/")
        except SahmkError:
            return out
        row = payload if isinstance(payload, dict) else {}
        row = row.get("company") or row.get("data") or row

        out["name_ar"] = row.get("name_ar") or ""
        out["name_en"] = row.get("name_en") or row.get("name") or ""
        out["sector"] = row.get("sector_name_ar") or row.get("sector_name") or ""
        out["security_type"] = row.get("security_type") or ""
        out["sub_market"] = str(row.get("market_id") or row.get("market") or "")

        def _num(*keys):
            for k in keys:
                v = row.get(k)
                if v not in (None, "", "-"):
                    try:
                        return float(v)
                    except (TypeError, ValueError):
                        continue
            return None

        out["pe"] = _num("pe", "pe_ratio", "price_earnings")
        out["eps"] = _num("eps", "earnings_per_share")
        out["book_value"] = _num("book_value", "bvps")
        out["week52_high"] = _num("week_52_high", "high_52w", "fifty_two_week_high")
        out["week52_low"] = _num("week_52_low", "low_52w", "fifty_two_week_low")
        return {k: v for k, v in out.items() if v not in ("", None)}

    def quote_volumes(self) -> dict[str, float]:
        return dict(self.last_volumes)

    # ───────────────────────────────────────────── الفحص

    def test_connection(self) -> dict[str, Any]:
        """فحص سريع يقول أين تقف بالضبط."""
        started = time.time()
        try:
            payload = self._get("/companies/", {"market": "TASI", "limit": 1})
            n = int((payload or {}).get("count") or 0)
        except SahmkError as exc:
            return {"ok": False, "stage": "companies", "error": str(exc),
                    "ms": round((time.time() - started) * 1000)}

        # الشركات مجانية؛ التاريخية تحتاج باقة. فحصها منفصل لأن نجاح
        # الأولى وفشل الثانية يعني «المفتاح سليم والباقة لا تكفي» —
        # وهي حالة يجب ألّا تُخلَط بمفتاح خاطئ.
        hist_ok, hist_err = True, ""
        try:
            self._get("/historical/2222/", {"interval": "1d", "limit": 1})
        except SahmkError as exc:
            hist_ok, hist_err = False, str(exc)

        # ‏/quotes/‎ يحتاج Starter فأعلى، وهو المستعمل لترتيب الكون
        # بالحجم. فحصه منفصلاً لأن فشله **لا يمنع** الاكتشاف — يمنع
        # الترتيب وحده. وخلطه بالبقيّة هو ما جعل حساباً مجانياً يفقد
        # السوق كلّه بدل أن يفقد ترتيبه.
        quotes_ok, quotes_err = True, ""
        try:
            self._get("/quotes/", {"symbols": "2222"})
        except SahmkError as exc:
            quotes_ok, quotes_err = False, str(exc)

        return {
            "ok": True, "companies": n, "historical": hist_ok,
            "historical_error": hist_err,
            "quotes": quotes_ok, "quotes_error": quotes_err,
            "ms": round((time.time() - started) * 1000),
            "timeframes": [k for k, v in TIMEFRAME.items() if v],
        }
