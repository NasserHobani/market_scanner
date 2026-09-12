# -*- coding: utf-8 -*-
"""بصمة السياق — لتجنّب إعادة بناء ما لم يتغيّر.

═══ ما يدخل البصمة ولماذا ═══

كل ما يغيّر **ما يقرأه النموذج** يدخل؛ وما لا يغيّره يُستبعَد.

فالبصمة تضمّ الرمز والفريم وحالة السوق وقرار المنصّة والملف ونسخة
المترجم. ولا تضمّ زمن البناء ولا معرّف الحزمة: هذان يتغيّران في كل
نداء، فإدخالهما يجعل البصمة فريدة دائماً — أي ذاكرة لا تُصيب أبداً،
وهو عين العطب الذي أصاب ذاكرة الأسعار حين ساوت مهلتها فترة الاستعلام.

ونسخة المترجم داخلة عمداً: تعديل قواعد الانتقاء يعني سياقاً مختلفاً
من الحزمة نفسها، فيجب أن تسقط الذاكرة القديمة تلقائياً بلا مسح يدوي.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

__all__ = ["context_fingerprint", "package_context_key"]


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _stable(v) for k, v in sorted(value.items())
                if v not in (None, "", [], {})}
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    return value


def context_fingerprint(ctx, *, profile: str,
                        compiler_version: str) -> str:
    payload = {
        "symbol": getattr(ctx, "symbol", ""),
        "market": getattr(ctx, "market", ""),
        "timeframe": getattr(ctx, "timeframe", ""),
        "analysis_type": getattr(ctx, "analysis_type", ""),
        "platform": _stable(getattr(ctx, "platform", {})),
        "market_state": _stable(getattr(ctx, "market_state", {})),
        "historical": _stable(getattr(ctx, "historical", {})),
        "prediction": _stable(getattr(ctx, "prediction", {})),
        "data_quality": _stable(getattr(ctx, "data_quality", {})),
        "profile": profile,
        "compiler": compiler_version,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "ctx_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def package_context_key(package_fingerprint: str, *, profile: str,
                        compiler_version: str) -> str:
    """مفتاح ذاكرة السياق: بصمة الحزمة + الملف + نسخة المترجم."""
    return f"{package_fingerprint}:{profile}:{compiler_version}"
