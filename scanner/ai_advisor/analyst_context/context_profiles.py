# -*- coding: utf-8 -*-
"""ملفات السياق — ميزانيات وأولويات وأسقف صلبة.

الفرق بين ``target`` و ``hard_max`` مقصود: الأول ما نسعى إليه، والثاني
ما لا يُتجاوَز أبداً. فالمترجم يقلّص حتى يبلغ الهدف، ويرفض الإرسال إن
بقي فوق السقف.

الأولويات ترتّب ما يُحذف أولاً عند الضيق. وترتيبها ليس ذوقاً: القرار
والاتجاه والهيكل هي ما يُبنى عليه الحكم، والبيانات الوصفية وأزمنة
البناء لا تغيّر رأي محلّل.
"""
from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Profile", "PROFILES", "resolve_profile", "SECTION_PRIORITY"]


@dataclass(frozen=True)
class Profile:
    name: str
    target_tokens: int
    hard_max_tokens: int
    max_evidence: int
    similarity_detail: bool = False
    research_detail: bool = False


PROFILES: dict[str, Profile] = {
    # المراجعة التلقائية داخل المسح — تتكرّر عشرات المرّات
    "FAST": Profile("FAST", target_tokens=1200, hard_max_tokens=1500,
                    max_evidence=12),
    # زرّ «حلّل بالذكاء» — بطلب المستخدم، فيُحتمل سياق أوسع
    "STANDARD": Profile("STANDARD", target_tokens=2000, hard_max_tokens=2500,
                        max_evidence=18, research_detail=True),
    # تصعيد أو تدقيق — لا يُستعمل في المسح التلقائي
    "DEEP": Profile("DEEP", target_tokens=3000, hard_max_tokens=4000,
                    max_evidence=24, similarity_detail=True,
                    research_detail=True),
}

_ALIASES = {
    "fast": "FAST", "auto": "FAST", "automatic": "FAST", "scan": "FAST",
    "standard": "STANDARD", "manual": "STANDARD", "normal": "STANDARD",
    "deep": "DEEP", "full": "DEEP", "escalation": "DEEP", "audit": "DEEP",
}

DEFAULT_PROFILE = "STANDARD"


def resolve_profile(name: str | None) -> Profile:
    key = str(name or "").strip().lower()
    key = _ALIASES.get(key, key.upper())
    return PROFILES.get(key, PROFILES[DEFAULT_PROFILE])


# ترتيب الحذف عند الضيق — الأدنى يُحذف أولاً.
#
# «جودة البيانات» عالية عمداً رغم أنها ليست إشارة سوق: تغطية 11٪ تعني
# أن كل ما تحتها مشكوك فيه، فحذفها يُنتج تحليلاً واثقاً على أساس هشّ —
# وهو أسوأ من لا تحليل.
SECTION_PRIORITY: tuple[str, ...] = (
    "identity",        # الرمز والفريم — بلا هذا لا معنى لشيء
    "data_quality",    # هل يُوثَق بما تحته أصلاً؟
    "platform",        # قرار المنصّة — موضوع المراجعة
    "market",          # الاتجاه والنظام والهيكل والزخم والحجم والتقلّب
    "prediction",      # حالة النموذج الإحصائي
    "risk",
    "historical",      # التشابه والنتائج السابقة
    "research",
    "features",        # ذكاء الخصائص
    "contradictions",
    "notes",
)
