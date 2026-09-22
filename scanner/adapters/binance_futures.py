# -*- coding: utf-8 -*-
"""تموضع المشتقّات من Binance — عامّ، بلا مفتاح، بلا تكلفة.

═══ ما هذا ولمَ ═══

سعر السوق الفوريّ يقول **ماذا** حدث. ومعدّل التمويل والمراكز
المفتوحة يقولان **من** دفعه وبأيّ رافعة. وهما شيئان مختلفان:

    ارتفاعٌ والتمويل قرب الصفر      = شراءٌ فوريّ يدفع السعر
    ارتفاعٌ والتمويل مرتفعٌ جدّاً     = رافعةٌ تدفعه — وهي تُصفّى

والثاني هشّ: المراكز المدينة تُغلق قسراً عند أوّل هبوط، فيتحوّل
التصحيح الصغير إلى شلّال. وهذا ما يجعل التموضع **حارس مخاطر**
لمنصّةٍ شرائية، لا مؤشّر اتجاه.

═══ وما لا يدّعيه ═══

لا التمويل ولا المراكز المفتوحة تتنبّأ بالاتجاه. كلاهما يصف
**تكلفة التموضع الحالي**، لا ما بعده. والمصادر التي راجعتُها
تقول ذلك صراحةً، وهذا الملفّ لا يقول غيره.

فالمخرَج هنا وصفٌ لا إشارة، ولا يدخل درجة PES بحالٍ حتى يُقاس.

═══ وحدود البيانات ═══

    fundingRate         تاريخٌ طويل — كل ٨ ساعات
    openInterestHist    ‏**٣٠ يوماً فقط** — حدُّ Binance نفسه

والثاني هو ما يقيّد أيّ قياسٍ تاريخيّ على المراكز المفتوحة. وهو
مذكورٌ هنا كي لا يُبنى عليه اختبارٌ خلفيّ طويل بحسن نيّة.

═══ ومضيفٌ آخر ═══

المشتقّات على ``fapi.binance.com`` لا على ``data-api.binance.vision``
— الأخير للسوق الفوريّ وحده ولا يعرف هذه المسارات.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("scanner.adapters.binance_futures")

HOSTS = ["https://fapi.binance.com"]
UA = {"User-Agent": "market-scanner/0.1"}

#: حدّ Binance على سجلّ المراكز المفتوحة
OI_HISTORY_DAYS = 30

#: التمويل ثلاث مرّاتٍ في اليوم على Binance
FUNDINGS_PER_DAY = 3

# والنتائج تُخبّأ: التمويل يتغيّر كل ثماني ساعات، والمراكز كل
# خمس دقائق. وطلبٌ لكل فتح صفحة إهدارٌ ومخاطرةٌ بالحدّ.
_CACHE: dict[str, tuple[float, object]] = {}
CACHE_TTL = 300.0


def _get(path: str, params: dict, timeout: int = 12):
    """طلبٌ عامّ — ويعيد ``None`` عند الفشل بدل أن يرمي.

    فشلُ الشبكة يجب أن يُنتج «غير متاح» في الشاشة، لا صفحةَ خطأ:
    التموضع إضافةٌ وصفية، وسقوط الصفحة كلّها بسببها خسارةٌ صافية.
    """
    qs = urllib.parse.urlencode(params)
    last = ""
    for host in HOSTS:
        url = f"{host}{path}?{qs}"
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError,
                json.JSONDecodeError) as exc:
            last = f"{type(exc).__name__}: {str(exc)[:80]}"
    if last:
        log.info("تعذّر جلب %s — %s", path, last)
    return None


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    now = time.time()
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    val = fn()
    # والفشل لا يُخبَّأ: محاولةٌ ثانية بعد دقائق قد تنجح، وتخبئةُ
    # ``None`` خمس دقائق تجعل عطباً عابراً يبدو دائماً.
    if val is not None:
        _CACHE[key] = (now, val)
    return val


def funding_history(symbol: str = "BTCUSDT", limit: int = 1000) -> list[dict]:
    """سجلّ معدّل التمويل — الأقدم أوّلاً.

    كلٌّ منها **مُحقَّق**: دفعةٌ تمّت في وقتها. فلا شمعةَ جارية
    هنا ولا إعادة رسم.
    """
    def go():
        return _get("/fapi/v1/fundingRate",
                    {"symbol": symbol, "limit": min(int(limit), 1000)})

    raw = _cached(f"fund:{symbol}:{limit}", go)
    if not isinstance(raw, list):
        return []
    out = []
    for r in raw:
        try:
            out.append({"time": int(r["fundingTime"]),
                        "rate": float(r["fundingRate"])})
        except (KeyError, TypeError, ValueError):
            continue
    return out


def open_interest_history(symbol: str = "BTCUSDT", period: str = "4h",
                          limit: int = 500) -> list[dict]:
    """سجلّ المراكز المفتوحة — ثلاثون يوماً كحدٍّ أقصى.

    و``sumOpenInterest`` بوحدة العملة (BTC)، و``…Value`` بالدولار.
    والأوّل هو الصحيح للمقارنة عبر الزمن: الثاني يرتفع بارتفاع
    السعر وحده، فيبدو تراكماً وهو إعادة تسعير.
    """
    def go():
        return _get("/futures/data/openInterestHist",
                    {"symbol": symbol, "period": period,
                     "limit": min(int(limit), 500)})

    raw = _cached(f"oi:{symbol}:{period}:{limit}", go)
    if not isinstance(raw, list):
        return []
    out = []
    for r in raw:
        try:
            out.append({
                "time": int(r["timestamp"]),
                "oi": float(r["sumOpenInterest"]),
                "oi_usd": float(r.get("sumOpenInterestValue") or 0.0),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return out


def premium_index(symbol: str = "BTCUSDT") -> dict:
    """المعدّل الجاري وموعد الدفعة القادمة.

    ``lastFundingRate`` تقديرٌ **متحرّك** للدفعة التي لم تُدفع
    بعد — فهو يعيد الرسم بطبيعته. ويُعرَض للسياق وحده، ولا يدخل
    أيّ حساب: الحسابات كلّها على السجلّ المُحقَّق.
    """
    raw = _cached(f"prem:{symbol}",
                  lambda: _get("/fapi/v1/premiumIndex", {"symbol": symbol}))
    if not isinstance(raw, dict):
        return {}
    try:
        return {
            "mark": float(raw.get("markPrice") or 0.0),
            "index": float(raw.get("indexPrice") or 0.0),
            "estimated_rate": float(raw.get("lastFundingRate") or 0.0),
            "next_time": int(raw.get("nextFundingTime") or 0),
        }
    except (TypeError, ValueError):
        return {}


__all__ = ["funding_history", "open_interest_history", "premium_index",
           "OI_HISTORY_DAYS", "FUNDINGS_PER_DAY"]
