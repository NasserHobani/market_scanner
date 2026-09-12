# -*- coding: utf-8 -*-
"""مقاييس الأداء — أين يذهب الوقت والرموز.

═══ لماذا مفصولة ═══

«المراجعة استغرقت 116 ثانية» لا تقول شيئاً قابلاً للتصرّف. أهو جمع
البيانات؟ أم بناء السياق؟ أم النموذج نفسه؟ الأول يُحلّ بذاكرة، والثاني
بترجمة أخفّ، والثالث بنموذج أصغر أو موجّه أقصر — وعلاجات لا تتشابه.

فالتفصيل هنا ليس زينة لوحة، بل هو ما يجعل التحسين موجَّهاً بدل أن يكون
تخميناً.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

__all__ = ["RequestMetrics", "Stopwatch"]


@dataclass
class RequestMetrics:
    data_collection_ms: float = 0.0
    context_compile_ms: float = 0.0
    prompt_build_ms: float = 0.0
    provider_latency_ms: float = 0.0
    total_request_ms: float = 0.0

    estimated_input_tokens: int = 0
    actual_input_tokens: int = 0
    output_tokens: int = 0

    profile: str = ""
    context_fingerprint: str = ""
    compiler_version: str = ""

    tokens_before: int = 0          # قبل الترجمة — للمقارنة
    tokens_after: int = 0
    evidence_before: int = 0
    evidence_after: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def token_reduction_pct(self) -> float:
        if not self.tokens_before:
            return 0.0
        return round((1 - self.tokens_after / self.tokens_before) * 100, 1)

    @property
    def evidence_reduction_pct(self) -> float:
        if not self.evidence_before:
            return 0.0
        return round((1 - self.evidence_after / self.evidence_before) * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["token_reduction_pct"] = self.token_reduction_pct
        out["evidence_reduction_pct"] = self.evidence_reduction_pct
        # الفارق بين التقدير والحقيقة يُعرَض: تقدير يخطئ بانتظام يجب
        # أن يُعاير، ولا يُعرف خطؤه إلا بمقارنته بما أعاده المزوّد
        if self.actual_input_tokens and self.estimated_input_tokens:
            out["estimate_error_pct"] = round(
                (self.estimated_input_tokens - self.actual_input_tokens)
                / self.actual_input_tokens * 100, 1)
        return out


class Stopwatch:
    """قياس مرحلة واحدة::

        with Stopwatch() as sw:
            ...
        metrics.context_compile_ms = sw.ms
    """

    def __init__(self) -> None:
        self.ms = 0.0
        self._t0 = 0.0

    def __enter__(self) -> "Stopwatch":
        self._t0 = time.monotonic()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ms = round((time.monotonic() - self._t0) * 1000, 2)
