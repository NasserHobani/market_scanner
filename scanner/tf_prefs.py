# -*- coding: utf-8 -*-
"""فريمات كل سوق — مصدرٌ واحد يقرؤه المزامِن والماسح معاً.

═══ لماذا وحدةٌ مستقلّة ═══

كان المحلّل داخل ``market_sync/service.py`` وحده. فالإعداد ضبط
**المزامنة** فقط: من كتب ``crypto=1h`` ظنّ أنّه فعّل فريم الساعة،
ثمّ ضغط «١ ساعة» في شاشة المسح فأعادته الشاشة إلى ‎4h‎ بلا سبب
ظاهر — لأنّ المسح يقرأ ``config/crypto.yaml`` لا الإعداد.

فصار الإعداد إعدادين بصيغةٍ واحدة ومحلّلٍ واحد:

    sync_timeframes    ما يُجلب من المنصّة
    scan_timeframes    ما يُمسح ويُعرض

═══ وقاعدةٌ تربطهما ═══

كلّ فريمٍ يُمسح **يجب** أن يُزامَن. وإلّا فالماسح يقرأ القرص
فيجده فارغاً: صفر نتائج، بلا خطأ ولا رسالة. فالمزامنة تضمّ فريمات
المسح إليها قسراً، والإعداد لا يستطيع نزعها.

═══ والفواصل ═══

صيغة الحقل سطرٌ واحد في خانةٍ واحدة. وأوّل ما كتبه المستخدم:

    crypto=4h,1d,1h,15m saudi=1d,4h gold=4h,1d us=1d,4h

وكان المحلّل يفصل بالسطر والنقطة والفاصلة المنقوطة **لا
بالمسافة**. فالسطر كلّه صار قيمةً واحدة لـ``crypto``، وضاع
``15m`` لأنّه التصق بـ``saudi=1d``، وبقيت الأسواق الثلاثة على
الافتراض. بلا خطأ ولا تنبيه — وهذا أسوأ ما في الأمر.

والمسافة الآن فاصلٌ كغيرها: الحدّ يُوضع قبل كل ``اسم=``، فلا
يهمّ أكُتبت الأسواق في سطرٍ أم في أربعة.
"""
from __future__ import annotations

import re

from scanner.live import UI_TIMEFRAMES

#: مفاتيح الإعدادات التي تُحلَّل بهذه الصيغة
SYNC_KEY = "sync_timeframes"
SCAN_KEY = "scan_timeframes"

# ‏اسم السوق يبدأ بحرف، والفريم يبدأ برقم (‎4h‎ · ‎15m‎ · ‎1d‎).
# فهذا النمط لا يلتقط فريماً أبداً مهما تشابهت الصيغتان.
_NAME_EQ = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")
_SPLIT = re.compile(r"[,\s]+")


def parse(raw: str) -> dict[str, list[str]]:
    """‏«سوق=فريمات» → ``{"crypto": ["4h", "1d"]}``.

    لا ترمي أبداً: إعدادٌ مكتوبٌ خطأً يجب أن يُهمَل ويعود النظام
    إلى الافتراض — لا أن يوقف المزامنة كلّها.
    """
    text = str(raw or "")
    if not text.strip():
        return {}
    # فواصل الأسواق: السطر · النقطة · الفاصلة المنقوطة — والمسافة
    # التي تسبق ``اسم=``
    text = text.replace("·", "\n").replace(";", "\n").replace("،", ",")
    text = _NAME_EQ.sub(lambda m: "\n" + m.group(1) + "=", text)

    out: dict[str, list[str]] = {}
    for part in text.split("\n"):
        if "=" not in part:
            continue
        name, _, tfs = part.partition("=")
        key = name.strip().lower()
        if not key:
            continue
        good: list[str] = []
        for tok in _SPLIT.split(tfs):
            tok = tok.strip()
            # الفريم المجهول يُهمَل ولا يُسقط الباقي
            if tok in UI_TIMEFRAMES and tok not in good:
                good.append(tok)
        # سوقٌ بلا فريمٍ صالح = لم يُذكر. وإفراغُه كان سيوقف
        # مزامنته بالكامل بسبب خطأٍ إملائيّ واحد.
        if good:
            out[key] = good
    return out


def review(raw: str) -> list[str]:
    """ما أُهمِل من الإعداد — كي لا يُهمَل صامتاً.

    التجاهل الصامت هو ما جعل ``15m`` يختفي بلا أثر. والرسالة هنا
    تُعرض في الشاشة وتُكتب في السجلّ.
    """
    text = str(raw or "")
    if not text.strip():
        return []
    notes: list[str] = []
    seen_any = False
    flat = text.replace("·", "\n").replace(";", "\n").replace("،", ",")
    flat = _NAME_EQ.sub(lambda m: "\n" + m.group(1) + "=", flat)
    for part in flat.split("\n"):
        if not part.strip():
            continue
        if "=" not in part:
            notes.append(f"«{part.strip()[:40]}» بلا علامة ‎=‎ — أُهمِل")
            continue
        seen_any = True
        name, _, tfs = part.partition("=")
        bad = [t.strip() for t in _SPLIT.split(tfs)
               if t.strip() and t.strip() not in UI_TIMEFRAMES]
        if bad:
            notes.append(f"{name.strip()}: فريمٌ مجهول {' · '.join(bad[:4])}"
                         f" — المتاح {' · '.join(UI_TIMEFRAMES)}")
        elif not [t for t in _SPLIT.split(tfs) if t.strip()]:
            notes.append(f"{name.strip()}: بلا فريمات — بقي على الافتراض")
    if not seen_any:
        notes.append("لا يوجد «سوق=فريمات» — أُهمِل الإعداد كلّه")
    return notes


def _setting(key: str) -> str:
    """قيمة الإعداد من قاعدة الويب — وفراغٌ إن تعذّر."""
    try:
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        if str(root / "web") not in sys.path:
            sys.path.insert(0, str(root / "web"))
        from dashboard import appsettings

        return str((appsettings.values() or {}).get(key, "") or "")
    except Exception:  # noqa: BLE001
        return ""


def for_market(market: str, key: str) -> list[str]:
    """فريمات هذا السوق من الإعداد ``key``، أو قائمةٌ فارغة."""
    name = (market or "").strip().lower()
    if not name:
        return []
    return list(parse(_setting(key)).get(name, []))


def sync_for(market: str) -> list[str]:
    return for_market(market, SYNC_KEY)


def scan_for(market: str) -> list[str]:
    return for_market(market, SCAN_KEY)
