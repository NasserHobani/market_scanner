# -*- coding: utf-8 -*-
"""تقدير الرموز — للنصّ الذي **يُرسَل**، لا لكائن داخلي.

═══ العطب الذي تعالجه هذه الوحدة ═══

كان التقدير يُحسب هكذا::

    text = json.dumps(package.to_dict())
    tokens = len(text) // 4

وهذا يقيس **الحزمة** لا **الموجّه**. والموجّه المُرسَل فعلاً يضمّ:

    تعليمات القالب + كتلة الحالة + كتلة JSON بمسافات (‏indent=2)
    + فهرس الأدلّة كاملاً + مخطّط الجواب + موجّه النظام

فقيس على حزمة فعلية: التقدير المُعلَن **1414** رمزاً «داخل ميزانية
1500»، والمُرسَل حقيقةً **2964**. أي أن الحدّ كان يُفرَض على نصّ لا
يغادر العملية أصلاً.

═══ ولماذا لا يكفي «أربعة محارف للرمز» ═══

القاعدة الشائعة (‏4 محارف/رمز) مقيسة على نصّ إنجليزي. والعربية تُرمَّز
أكثف بكثير في مرمِّزات ‏BPE الشائعة — قرابة **2.2** محرف للرمز — لأن
حروفها خارج ‏ASCII وتُقسَّم إلى وحدات أصغر.

فموجّه عربي بألفي محرف يُقدَّر بـ500 رمز بالقاعدة الشائعة، وحقيقته
قرابة 900. ومحلّل يكتب بالعربية سيتجاوز ميزانيته بلا أن يعلم.

ولهذا يُحسب هنا كل صنف بمعامله: العربية بكثافتها، واللاتينية
بكثافتها، والأرقام والرموز بينهما.

═══ التقدير يخطئ — فليخطئ إلى الأمان ═══

هذا تقدير لا إحصاء دقيق؛ المرمِّز الحقيقي داخل النموذج. فالمعاملات
مختارة لتُعطي رقماً **لا يقلّ** عن الحقيقة في الأغلب، لأن تجاوز
الميزانية أسوأ من التقليص الزائد: الأول يعني بطئاً وقطعاً، والثاني
يعني دليلاً أقلّ.
"""
from __future__ import annotations

__all__ = ["estimate_text_tokens", "estimate_prompt_tokens", "char_profile"]

# محارف لكل رمز، حسب الصنف. أقلّ = أكثف = رموز أكثر لنفس الطول.
CHARS_PER_TOKEN_ARABIC = 2.2
CHARS_PER_TOKEN_LATIN = 4.0
CHARS_PER_TOKEN_OTHER = 3.0

# نطاقات العربية: الأساسي، والملحق، والأشكال التقديمية.
_ARABIC_RANGES = (
    (0x0600, 0x06FF), (0x0750, 0x077F),
    (0xFB50, 0xFDFF), (0xFE70, 0xFEFF),
)


def _is_arabic(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _ARABIC_RANGES)


def char_profile(text: str) -> dict[str, int]:
    """عدد المحارف بكل صنف — للتشخيص وللاختبار."""
    arabic = latin = other = 0
    for ch in text or "":
        if _is_arabic(ch):
            arabic += 1
        elif ch.isascii():
            latin += 1
        else:
            other += 1
    return {"arabic": arabic, "latin": latin, "other": other,
            "total": arabic + latin + other}


def estimate_text_tokens(text: str) -> int:
    """رموز تقريبية لنصّ مختلط اللغة."""
    if not text:
        return 0
    p = char_profile(text)
    est = (p["arabic"] / CHARS_PER_TOKEN_ARABIC
           + p["latin"] / CHARS_PER_TOKEN_LATIN
           + p["other"] / CHARS_PER_TOKEN_OTHER)
    return max(1, int(est + 0.999))


def estimate_prompt_tokens(system_prompt: str = "", user_prompt: str = "") -> int:
    """رموز الموجّه كما سيصل النموذج — الجزءان معاً.

    موجّه النظام يُحتسب لأنه يُرسَل في كل نداء ويُقرأ كما يُقرأ موجّه
    المستخدم. وإهماله كان يخفي مئات الرموز في كل مراجعة.
    """
    return estimate_text_tokens(system_prompt) + estimate_text_tokens(user_prompt)
