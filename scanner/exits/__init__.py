# -*- coding: utf-8 -*-
"""قواعد الخروج — قياسها على البيانات الحقيقية قبل تبنّيها.

    71٪ من الصفقات الخاسرة بلغت +0.5R قبل أن تنقلب
    39٪ منها بلغت +1.0R
    ووسيط ما أُعيد في الخاسرة: 1.70R

هذه أرقام مشروعك. والسؤال الذي تجيب عنه هذه الوحدة: هل قاعدة خروج
مختلفة كانت لتحوّلها إلى ربح — **بعد** احتساب كلفة التنفيذ، و**دون**
ملاءمة زائدة على الماضي؟
"""
from __future__ import annotations

from .simulator import (
    RULES, ExitRule, RuleStats, TradeResult, compare_rules, simulate,
)

__all__ = ["RULES", "ExitRule", "RuleStats", "TradeResult",
           "compare_rules", "simulate"]
