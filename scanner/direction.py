# -*- coding: utf-8 -*-
"""المنصّة شراءٌ فقط — سبوت أو لونغ، ولا بيع على المكشوف.

═══ لماذا قاعدةٌ لا خيار ═══

محرّك التوصية نفسه لا يُنتج بيعاً أصلاً: يعيد ``buy`` أو ``—``.
لكنّ **المداخل** تقبل اتّجاهاً من الخارج:

    advice_views      ``request.POST.get("side")``  ← من المتصفّح
    trades.open_*     ``reco.get("side", "buy")``   ← من قاموس
    scan (الأمر)      ``reco.get("side", "buy")``
    recobt · exits    ``tr.get("side", "buy")``

وكلٌّ منها يثق بما يُمرَّر إليه. فطلبٌ واحد بـ``side=sell`` يفتح
صفقة بيعٍ في نظامٍ بُني كلّه على الشراء: الوقف فوق الدخول،
و‏R محسوبة بالعكس، والمحفظة الورقية تشتري ما لا تملكه.

═══ والرفض لا التصحيح ═══

الإغراء أن يُحوَّل ``sell`` إلى ``buy`` بهدوء. وهو أسوأ ما يمكن
فعله: إشارةٌ هابطة تصير مركزاً صاعداً — أي أن يُفتح الشراء في
اللحظة التي قال فيها التحليل «اهبط».

فالمجهول والبيع كلاهما **يُرفض** ويُقال سببه. والصمت هنا يخفي
قراراً، والقرار المخفيّ لا يُراجَع.

═══ وأين لا ينطبق ═══

قياسُ الماضي ليس فتحَ صفقة. فالسجلّ التاريخي قد يحمل صفقات بيعٍ
قديمة، وقراءتها وحسمها وعرضها مسموح — والمنع على **الإنشاء**
وحده. ومحوُ التاريخ يجعل كل نسبةٍ قيست عليه كاذبة.
"""
from __future__ import annotations

#: الاتجاه الوحيد المسموح بإنشائه
LONG = "buy"

#: ما يُفهَم بيعاً — بالعربية والإنجليزية، وبأيّ حالة أحرف
SHORT_WORDS = frozenset({
    "sell", "short", "s", "بيع", "بيعي", "هبوط", "هابط",
})

#: ما يُفهَم شراءً
LONG_WORDS = frozenset({
    "buy", "long", "b", "spot", "شراء", "صعود", "صاعد",
})

#: ‏False يفتح الباب للبيع — ويُترك للمستقبل لا للتشغيل اليوم.
#: وتغييره وحده لا يكفي: نصف الحسابات تفترض الشراء.
LONG_ONLY = True


class ShortNotSupported(ValueError):
    """محاولة إنشاء صفقة بيع في منصّةٍ شرائية."""


def _norm(side) -> str:
    return str(side or "").strip().lower()


def is_short(side) -> bool:
    """هل هذا اتّجاه بيع؟ والمجهول ليس بيعاً — هو مجهول."""
    return _norm(side) in SHORT_WORDS


def is_long(side) -> bool:
    return _norm(side) in LONG_WORDS


def allowed(side) -> bool:
    """هل يُسمح بإنشاء صفقةٍ بهذا الاتّجاه؟

    والفارغ مسموح: كثيرٌ من المُنادين لا يمرّرون اتّجاهاً أصلاً،
    ومعناه الضمنيّ «الافتراضي» — وهو الشراء.
    """
    if not LONG_ONLY:
        return True
    s = _norm(side)
    return s == "" or is_long(s)


def ensure_long(side, *, where: str = "") -> str:
    """يعيد ``buy`` للمسموح، ويرمي لغيره.

    ``where`` يُذكر في الرسالة: «رُفض بيع» وحدها لا تقول من حاول،
    ومسارٌ واحدٌ من خمسة هو ما يحتاج الإصلاح.
    """
    s = _norm(side)
    if not LONG_ONLY:
        return s or LONG
    if s == "" or is_long(s):
        return LONG
    tail = f" ({where})" if where else ""
    if is_short(s):
        raise ShortNotSupported(
            f"البيع على المكشوف غير مدعوم — المنصّة شراءٌ فقط{tail}")
    # ═══ والمجهول يُرفض أيضاً ═══
    #
    # قبولُه «على أنّه شراء» يجعل خطأً إملائياً يفتح صفقة. وهو
    # الصنف نفسه الذي جعل «sell» تمرّ: الثقة بما يُمرَّر.
    raise ShortNotSupported(f"اتّجاه غير معروف: {side!r}{tail}")


def reject_reason(side, *, where: str = "") -> str:
    """سببُ الرفض نصّاً — لمن يريد تخطّي الصفّ لا إسقاط العملية."""
    try:
        ensure_long(side, where=where)
    except ShortNotSupported as exc:
        return str(exc)
    return ""


__all__ = ["LONG", "LONG_ONLY", "ShortNotSupported", "allowed",
           "ensure_long", "is_long", "is_short", "reject_reason",
           "SHORT_WORDS", "LONG_WORDS"]
