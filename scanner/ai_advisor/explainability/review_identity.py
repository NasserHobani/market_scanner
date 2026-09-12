# -*- coding: utf-8 -*-
"""هويّة المراجعة — الرمز والسوق والفريم، من أوثق مصدر متاح.

═══ لماذا ═══

عمود «الرمز» في صفحة المراجعات ظهر فارغاً لأربع مراجعات، بينما
``event_id`` بجانبها يقول ``evt_btcusdt_crypto_4h``. أي أن المعلومة
كانت حاضرة والحقل الذي يقرأه العرض فارغ.

وسبب الفراغ عولج في المنبع (ختم الهويّة على الحزمة المستعادة من
الذاكرة). لكنّ السجلّ **الموجود أصلاً** لا يُصلحه تعديل المنبع، وإعادة
كتابة ملفّ تاريخ ملحَق-فقط لتصحيح حقل ليست خياراً سليماً: السجلّ يوثّق
ما جرى، لا ما نتمنّى أنه جرى.

فالاشتقاق هنا يقع **عند العرض**: الحقل المخزَّن أولاً، فإن غاب اشتُقّ
من ``event_id``، ويُعلَم أنه مشتقّ. لا كتابة على التاريخ ولا فراغ في
الشاشة.

═══ لماذا التفكيك من اليمين ═══

بنية المعرّف ``evt_{رمز}_{سوق}_{فريم}``. والرمز نفسه قد يحوي شرطة
سفلية (``BTC/USDT`` تصير ``btc_usdt``)، فالتفكيك من اليسار يقطعه.
أمّا السوق والفريم فمفردتان بلا فواصل، فالتفكيك من اليمين يصيب دائماً.
"""
from __future__ import annotations

from typing import Any

__all__ = ["parse_event_id", "identity_from"]

# أسواق النظام — تُستعمل للتحقّق لا للتخمين. وجود السوق في موضعه دليل
# على أن التفكيك صحيح؛ غيابه يعني معرّفاً بصيغة أخرى فلا نخترع منه شيئاً.
KNOWN_MARKETS = ("crypto", "us", "sa", "saudi", "forex")


def parse_event_id(event_id: str) -> tuple[str, str, str]:
    """``evt_btcusdt_crypto_4h`` ← ``("BTCUSDT", "crypto", "4h")``.

    يعيد ثلاثيّة فارغة إن لم تطابق البنية — الفراغ الصادق أفضل من
    رمز مخترَع من نصّ لا يحمله.
    """
    raw = str(event_id or "").strip()
    if not raw.lower().startswith("evt_"):
        return "", "", ""
    body = raw[4:]
    parts = body.rsplit("_", 2)
    if len(parts) != 3:
        return "", "", ""
    symbol, market, timeframe = parts
    if market.lower() not in KNOWN_MARKETS:
        return "", "", ""
    if not symbol or not timeframe:
        return "", "", ""
    # الرموز تُعرض بحروف كبيرة في كل الشاشات
    return symbol.upper(), market.lower(), timeframe.lower()


def identity_from(*sources: dict[str, Any] | None) -> tuple[str, str, str]:
    """أوّل قيمة غير فارغة عبر المصادر، ثمّ الاشتقاق من ``event_id``.

    المصادر تُمرَّر بترتيب الثقة: سجلّ التاريخ أولاً ثمّ البيانات
    الوصفية. والاشتقاق آخر شيء — لا يُستعمل ما دام حقل صريح موجوداً.
    """
    dicts = [d for d in sources if isinstance(d, dict)]

    def first(key: str) -> str:
        for d in dicts:
            val = d.get(key)
            if val:
                return str(val)
        return ""

    symbol = first("symbol") or first("pair")
    market = first("market")
    timeframe = first("timeframe") or first("tf")

    if symbol and market and timeframe:
        return symbol, market, timeframe

    for d in dicts:
        s, m, t = parse_event_id(d.get("event_id", ""))
        if s:
            return symbol or s, market or m, timeframe or t

    return symbol, market, timeframe
