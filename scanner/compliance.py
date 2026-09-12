"""فرز أوّلي للتوافق مع الضوابط الشرعية.

حدّ يجب أن يُقرأ قبل أي استخدام:

هذه الوحدة **لا تُفتي ولا تحكم**. هي فرز آلي بقواعد مكتوبة في ملف
`config/compliance.yaml` يمكنك تعديله. الحكم الشرعي في الأسهم والعملات
مسألة اجتهادية تختلف فيها الهيئات، ويحتاج بيانات مالية تفصيلية (نسب
الدين والإيرادات المحرّمة) لا تتوفر في هذه الأداة.

ما تفعله: تصنيف مبدئي بثلاث حالات مع ذكر السبب والمصدر، ليوجّهك إلى ما
يحتاج تحققاً — لا ليغنيك عنه.

للتحقق الفعلي: الهيئة الشرعية للسهم نفسه، أو مؤشرات معتمدة مثل مؤشر
السوق السعودي المتوافق مع الضوابط الشرعية، أو معايير AAOIFI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

COMPLIANT = "compliant"
NON_COMPLIANT = "non_compliant"
REVIEW = "review"
UNKNOWN = "unknown"

LABELS = {
    COMPLIANT: "متوافق مبدئياً",
    NON_COMPLIANT: "غير متوافق",
    REVIEW: "يحتاج مراجعة",
    UNKNOWN: "غير مصنّف",
}


@dataclass
class Verdict:
    status: str
    reason: str = ""
    source: str = ""

    @property
    def label(self) -> str:
        return LABELS.get(self.status, LABELS[UNKNOWN])

    def as_dict(self) -> dict:
        return {"status": self.status, "label": self.label,
                "reason": self.reason, "source": self.source}


class Screener:
    """يقرأ قواعد الفرز من ملف قابل للتعديل."""

    def __init__(self, rules: dict | None = None):
        self.rules = rules or {}

    @classmethod
    def load(cls, path: str | Path) -> "Screener":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(yaml.safe_load(p.read_text(encoding="utf-8")) or {})

    def check(self, symbol: str, market: str) -> Verdict:
        base = self._base(symbol, market)

        # ١) قائمة صريحة لهذا الرمز — تسبق كل القواعد العامة
        explicit = (self.rules.get("symbols") or {}).get(symbol) \
            or (self.rules.get("symbols") or {}).get(base)
        if explicit:
            return Verdict(explicit.get("status", REVIEW),
                           explicit.get("reason", ""),
                           explicit.get("source", "قائمة يدوية"))

        # ٢) فئات معرّفة (عملات مستقرة، إقراض، ميسر…)
        for name, group in (self.rules.get("categories") or {}).items():
            members = set(group.get("members") or [])
            if base in members or symbol in members:
                return Verdict(group.get("status", REVIEW),
                               group.get("reason", name),
                               group.get("source", "تصنيف الفئة"))

        # ٣) قاعدة السوق الافتراضية
        market_rule = (self.rules.get("markets") or {}).get(market) or {}
        if market_rule:
            return Verdict(market_rule.get("default_status", UNKNOWN),
                           market_rule.get("default_reason", ""),
                           market_rule.get("source", ""))

        return Verdict(UNKNOWN, "لا قاعدة مطابقة", "")

    @staticmethod
    def _base(symbol: str, market: str) -> str:
        if market == "crypto" and symbol.endswith("USDT"):
            return symbol[:-4]
        if symbol.endswith(".SR"):
            return symbol[:-3]
        return symbol


_cache: dict[str, Screener] = {}


def get_screener(path: str | Path) -> Screener:
    key = str(path)
    if key not in _cache:
        _cache[key] = Screener.load(path)
    return _cache[key]


def clear_cache() -> None:
    _cache.clear()
