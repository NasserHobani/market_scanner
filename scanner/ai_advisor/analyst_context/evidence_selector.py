# -*- coding: utf-8 -*-
"""انتقاء الأدلّة — من 41 بنداً إلى ما يغيّر الحكم.

═══ لماذا الانتقاء لا الإرسال ═══

فهرس الأدلّة كان يُرسَل كاملاً بصيغة::

    - ev_003: [reasoning] [trend.direction] Trend direction = 'neutral'

وفيه ثلاث علل مجتمعة:

  ١. **التكرار.** «الاتجاه: محايد» مذكور أصلاً في متن السياق. وإعادته
     في الأدلّة لا تضيف معلومة، لكنها تضيف رموزاً — ويقرأ النموذج
     الحقيقة مرّتين فيرجّح أنها أهمّ مما هي.

  ٢. **الحشو البنيوي.** ``source_layer`` و``section.field`` و``repr``
     تفاصيل تنفيذ. المحلّل لا يبني حكماً على أن الحقيقة جاءت من طبقة
     ``reasoning`` أو ``knowledge``.

  ٣. **العدد.** أربعون بنداً تُغرق العشرة التي تهمّ. وقدرة الانتباه
     محدودة في النماذج كما في الناس.

═══ ما يبقى ═══

المعرّف يبقى دائماً — هو ما يُتحقّق به من استشهاد النموذج خادميّاً
(‏«الدليل الذي ذكره موجود فعلاً؟»). أما نصّ الحقيقة فيُختصر، ويُحذف
كلّه إن كان مكرّراً لما في المتن.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from .analyst_context import EvidenceItem

__all__ = ["select_evidence", "normalize_fact"]

# طبقات بترتيب أهمّيتها للحكم — تُستعمل عند الاضطرار للحذف.
_LAYER_PRIORITY = {
    "recommendation": 5, "decision_ai": 8, "reasoning": 10,
    "knowledge": 20, "prediction": 25, "similarity": 30,
    "research": 40, "feature_intelligence": 50, "feature_snapshot": 55,
    "optimization": 70, "metadata": 95, "diagnostics": 99,
}

# حقول لا تُرسَل مهما اتّسع السياق: معرّفات داخلية وأزمنة بناء ونُسَخ.
# لا يبني عليها محلّل حكماً، وتشغل رموزاً في كل مراجعة.
_NOISE_FIELDS = {
    "package_id", "event_id", "schema_version", "version", "built_at",
    "timestamp", "created_at", "saved_at", "generated_at", "scan_id",
    "trade_id", "snapshot_id", "record_id", "fingerprint", "cached_at",
}

_NOISE_SECTIONS = {"metadata", "diagnostics"}

# ‏``available`` راية بنيوية لا حقيقة سوق. و«طبقة الاستدلال متاحة: نعم»
# لا تُغيّر حكم محلّل، بينما غيابها يُذكر أصلاً في المتن («غير متاح»).
# كانت وحدها تستهلك أربعة بنود من اثني عشر في الملف السريع.
_STRUCTURAL_FLAGS = {"available", "status", "enabled", "ok", "passed"}

# ‏OHLC خام لا يُرسَل أبداً: النموذج لا يحسب مؤشّرات، والمنصّة حسبتها
# أصلاً. وإرسالها يُغري النموذج بحساب لا يُجيده ويستهلك رموزاً بلا مقابل.
_OHLC_FIELDS = {"open", "high", "low", "close", "volume", "ohlc",
                "candles", "bars", "prices", "series"}


def normalize_fact(text: str) -> str:
    """صيغة موحّدة للمقارنة — لكشف التكرار لا للعرض.

    التطبيع يشمل تجريد التشكيل وتوحيد الألف والياء، فـ«الاتجاه محايِد»
    و«الاتجاه محايد» حقيقة واحدة لا اثنتان.
    """
    s = unicodedata.normalize("NFKC", str(text or "")).lower()
    s = re.sub(r"[ً-ٰٟ]", "", s)          # التشكيل
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ة", "ه")
    s = re.sub(r"[^\w؀-ۿ]+", " ", s)
    return " ".join(s.split())


def _short_value(value: Any, limit: int = 60) -> str:
    """قيمة مقروءة بلا ``repr`` ولا اقتباسات."""
    if value is None:
        return "غير محدَّد"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, (list, tuple)):
        return "، ".join(_short_value(v, 20) for v in list(value)[:4])
    if isinstance(value, dict):
        return "، ".join(f"{k}={_short_value(v, 16)}"
                         for k, v in list(value.items())[:4])
    text = str(value).strip()
    return text[:limit] + "…" if len(text) > limit else text


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


# أقصر من هذا لا يُقارَن بالاحتواء: «4» موجودة في أي نصّ تقريباً،
# فحذفها بحجّة التكرار يحذف دليلاً صحيحاً.
_MIN_CONTAINMENT_LEN = 8


def select_evidence(evidence_index, *, max_items: int,
                    already_stated: list[str] | None = None,
                    stated_text: str = "",
                    covered_fields: set | None = None,
                    ) -> tuple[list[EvidenceItem], dict[str, int]]:
    """يختار الأدلّة ويعيد ``(القائمة, إحصاء)``.

    Parameters
    ----------
    evidence_index:
        ``package.evidence_index`` — آثار الأدلّة الكاملة.
    max_items:
        سقف العدد حسب الملف.
    already_stated:
        حقائق وردت في متن السياق؛ ما يطابقها تماماً يُحذف.
    stated_text:
        **متن السياق المعروض**. يُقارَن بالاحتواء لا بالمطابقة، لأن
        المتن يكتب «التغطية: 11.1%» والدليل يكتب «coverage: 11.1» —
        حقيقة واحدة بصياغتين، والمطابقة التامّة تعجز عن ربطهما.
    """
    stated = {normalize_fact(s) for s in (already_stated or []) if s}
    body = normalize_fact(stated_text)
    covered = covered_fields or set()
    stats = {"total": 0, "empty": 0, "noise": 0, "ohlc": 0,
             "duplicate": 0, "kept": 0}

    scored: list[tuple[int, EvidenceItem]] = []
    seen: set[str] = set()

    for ref in evidence_index or ():
        stats["total"] += 1
        section = str(getattr(ref, "section", "") or "").lower()
        field = str(getattr(ref, "field", "") or "").lower()
        layer = str(getattr(ref, "source_layer", "") or "").lower()
        label = str(getattr(ref, "label", "") or "")
        value = getattr(ref, "value", None)
        eid = str(getattr(ref, "evidence_id", "") or "")
        if not eid:
            continue

        if field in _OHLC_FIELDS or section in _OHLC_FIELDS:
            stats["ohlc"] += 1
            continue
        if field in _NOISE_FIELDS or section in _NOISE_SECTIONS:
            stats["noise"] += 1
            continue
        if field in _STRUCTURAL_FLAGS:
            stats["noise"] += 1
            continue
        if (section, field) in covered:
            # عُرض في المتن — إعادته هنا تكرار مهما اختلفت الصياغة
            stats["duplicate"] += 1
            continue
        if _is_empty(value):
            # الغياب يُذكر مرّة واحدة في المتن («غير متاح») لا أربعين
            # مرّة في الأدلّة
            stats["empty"] += 1
            continue

        fact = f"{label or field}: {_short_value(value)}".strip(": ")
        key = normalize_fact(fact)
        value_key = normalize_fact(_short_value(value))
        duplicate = (
            not key or key in seen or key in stated
            or (body and len(key) >= _MIN_CONTAINMENT_LEN and key in body)
            or (body and len(value_key) >= _MIN_CONTAINMENT_LEN
                and value_key in body)
        )
        if duplicate:
            stats["duplicate"] += 1
            continue
        seen.add(key)

        priority = _LAYER_PRIORITY.get(layer or section, 60)
        scored.append((priority, EvidenceItem(eid, fact, priority)))

    scored.sort(key=lambda pair: pair[0])
    kept = [item for _, item in scored[:max(0, max_items)]]
    stats["kept"] = len(kept)
    return kept, stats
