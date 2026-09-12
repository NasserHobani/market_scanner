# -*- coding: utf-8 -*-
"""قائمة الحظر — تُقرأ مرّة وتُطبَّق في كل مسار.

═══ أين تُطبَّق ═══

الحظر عند **قائمة الرموز** قبل أوّل نداء شبكة. والإخفاء في العرض
لا يكفي: الرمز يُجلب ويُحلَّل فيستهلك وقت المسح، ويبقى قابلاً
لفتح صفقة من مسارٍ آخر (زرّ يدوي، مراقبة مسلّحة سابقة، توصية
مخزّنة).

فالمسارات المحروسة:

    ١) قائمة رموز المسح            — لا يُجلب أصلاً
    ٢) تسليح المراقبة               — لا تُنشأ مراقبة جديدة
    ٣) فتح الصفقة (آلية ويدوية)     — لا تُفتح
    ٤) صفحة الصفقات الذهبية         — لا يُرشَّح

═══ والنظام لا يفتي ═══

هذه القائمة قرار المستخدم وحده. ولا يضيف البرنامج إليها رمزاً من
تلقائه أبداً — لا من فرز ``scanner/compliance.py`` ولا من غيره.
ذاك يفرز ويقول «يحتاج مراجعة»، وهذا ينفّذ حكماً حكمَه صاحبه.

═══ والذاكرة قصيرة عمداً ═══

القائمة تُقرأ من القاعدة وتُحفظ ثوانيَ معدودة. فحظرٌ يضيفه
المستخدم يسري على المسح التالي بلا إعادة تشغيل — وهذا هو الفرق
العملي عن ملفّ ‏YAML الذي يحتاج تحريراً وإقلاعاً.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger("dashboard.blocklist")

# ثوانٍ قبل إعادة القراءة. المسح يمرّ على مئات الرموز فلا يُستعلَم
# لكلٍّ منها، والحظر الجديد يسري خلال هذه المدّة على أبعد تقدير.
CACHE_SECONDS = 20

_cache: dict = {"at": 0.0, "data": {}}
_lock = threading.Lock()


def base_of(symbol: str, market: str) -> str:
    """أصل الرمز بلا لاحقة التسعير.

    ``AAVEUSDT`` → ``AAVE`` و``2222.SR`` → ``2222``. فمن حظر
    الأصل حظر كل أزواجه — ولو لزم تكرار الحظر لكل زوج لأفلت
    الزوج الجديد بلا أن ينتبه أحد.
    """
    s = str(symbol or "").strip().upper()
    if market == "crypto":
        for quote in ("USDT", "USDC", "BUSD", "FDUSD", "TUSD", "BTC", "ETH"):
            if s.endswith(quote) and len(s) > len(quote):
                return s[: -len(quote)]
    if s.endswith(".SR"):
        return s[:-3]
    return s


def _load() -> dict:
    """‏{market: {"exact": set, "base": set}} — ولا يرمي أبداً.

    جدولٌ غير مهاجَر يجب ألّا يمنع مسحاً: الفشل يعني «لا حظر»، لا
    توقّف. والعكس (منع كل شيء عند العطب) يوقف النظام صامتاً.
    """
    out: dict[str, dict[str, set]] = {}
    try:
        from .models import BlockedSymbol

        for row in BlockedSymbol.objects.filter(active=True).values(
                "market", "symbol", "scope"):
            m = out.setdefault(str(row["market"]),
                               {"exact": set(), "base": set()})
            sym = str(row["symbol"]).strip().upper()
            if row["scope"] == "exact":
                m["exact"].add(sym)
            else:
                m["base"].add(base_of(sym, str(row["market"])))
    except Exception as exc:  # noqa: BLE001
        log.warning("تعذّرت قراءة قائمة الحظر: %s", str(exc)[:120])
        return {}
    return out


def _table() -> dict:
    now = time.time()
    with _lock:
        if now - _cache["at"] > CACHE_SECONDS:
            _cache["data"] = _load()
            _cache["at"] = now
        return _cache["data"]


def refresh() -> None:
    """يُبطل الذاكرة فوراً — يُنادى بعد كل تعديل من الواجهة."""
    with _lock:
        _cache["at"] = 0.0


def is_blocked(market: str, symbol: str) -> bool:
    t = _table().get(str(market)) or {}
    if not t:
        return False
    s = str(symbol or "").strip().upper()
    return s in t["exact"] or base_of(s, market) in t["base"]


def filter_symbols(market: str, symbols) -> tuple[list, list]:
    """يفصل المسموح عن المحظور — ويعيد الاثنين.

    المحظور يُعاد ليُذكر عدده في مخرَج المسح. وحذفٌ صامت يجعل
    المستخدم يرى «٣٢٠ رمزاً» بدل ٣٢٦ ولا يعرف أين ذهبت الستّة.
    """
    allowed, blocked = [], []
    for s in symbols or []:
        (blocked if is_blocked(market, s) else allowed).append(s)
    return allowed, blocked


def drop_blocked(rows, *, market_key: str = "market",
                 symbol_key: str = "symbol", market: str = ""):
    """يُسقط المحظور من قائمة صفوفٍ معروضة.

    ═══ لماذا هذا لازم رغم الحرس عند المسح ═══

    الحرس يمنع **المسح القادم**. أمّا ما مُسح قبل الحظر فمخزّنٌ في
    القاعدة ويُعرض كما هو — وقع هذا فعلاً: حُظر رمزٌ وبقيت له ثلاثة
    عشر صفّاً ظاهرة، فبدا الحظر معطّلاً.

    فالقاعدة: يُحجب من **شاشات الاكتشاف** (الماسح · الذهبية ·
    الانضغاط · PES). ولا يُحجب من **مراكزك** — صفقةٌ مفتوحة عليه
    مالُك، وإخفاؤها يمنعك من إدارتها.
    """
    out = []
    for r in rows or []:
        m = market or (r.get(market_key) if isinstance(r, dict)
                       else getattr(r, market_key, ""))
        sym = (r.get(symbol_key) if isinstance(r, dict)
               else getattr(r, symbol_key, ""))
        if not is_blocked(str(m or ""), str(sym or "")):
            out.append(r)
    return out


def count(market: str = "") -> int:
    t = _table()
    if market:
        m = t.get(market) or {}
        return len(m.get("exact", ())) + len(m.get("base", ()))
    return sum(len(v.get("exact", ())) + len(v.get("base", ()))
               for v in t.values())


__all__ = ["is_blocked", "filter_symbols", "drop_blocked", "refresh",
           "base_of", "count",
           "CACHE_SECONDS"]
