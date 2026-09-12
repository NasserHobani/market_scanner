# -*- coding: utf-8 -*-
"""المراجعة التلقائية — بالمسار الجديد.

═══ ما استُبدل ولماذا ═══

المسار القديم أنتج ٧٥ قراراً::

    wait          65
    insufficient   5   ← عُرضت «مراقبة»
    avoid          4
    watch          1
    buy            0

و``buy`` **موجودة** في مفرداته ويمرّرها التطبيع سليمة — فليست
قيداً في القاموس. ومع ذلك لم تخرج ولا مرّة.

وأشدّ من ذلك أنّ الرفض لم يكن يُرى: المخرَج المرفوض يُسقَط صامتاً،
فيبدو السجلّ نظيفاً وهو ناقص. و``actionable_advice`` فارغ في ١٦٤
من ١٦٤.

═══ والمسار هنا ═══

    صفّ الماسح
        ↓
    evidence   ← أرقام من سجلّ الصفقات المحسومة
    why        ← أسباب الإشارة مقيسةً على السجلّ نفسه
        ↓
    verdict    ← خمسة حقول، ورفضٌ **يُحفظ** بسببه
        ↓
    verdict_store

═══ ولمن تُجرى ═══

للمرشّح القابل للتنفيذ وحده. المسح يمرّ على مئات الرموز، ونداء
النموذج على كلٍّ منها يعني ساعاتٍ على رموزٍ لن تُتَّخذ عليها خطوة.
والحدّ ``max_items`` قائمٌ لهذا: نداءٌ محلّيّ يكلّف ثوانٍ، ومئتا
نداء تُعلّق المسح.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from . import verdict_store

log = logging.getLogger("scanner.auto_review")

# سقفٌ لكل جولة مسح
MAX_ITEMS = 25

# ما يُعدّ قابلاً للتنفيذ
ACTIONABLE = ("now", "pending")


def is_actionable(row: dict[str, Any]) -> bool:
    """هل يستحقّ هذا الصفّ نداءً للنموذج؟"""
    if not row:
        return False
    if row.get("ready"):
        return True
    return str(row.get("action") or "").lower() in ACTIONABLE


def setup_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """صفّ الماسح → إعداداً للأدلّة.

    ``reasons`` يُنقَل كما هو: هو مدخل ``why`` الذي يقيس كل سببٍ
    مزعوم على السجلّ. وإسقاطه هنا يُفقد التفسير كلَّه.
    """
    def num(*keys):
        for k in keys:
            v = row.get(k)
            if v in (None, ""):
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    grade = str(row.get("grade") or "").strip()
    return {
        "symbol": str(row.get("symbol") or ""),
        "market": str(row.get("market") or ""),
        "timeframe": str(row.get("timeframe") or ""),
        "side": str(row.get("side") or row.get("direction") or "buy"),
        "action": str(row.get("action") or row.get("decision") or ""),
        "grade": "" if grade in ("—", "-") else grade,
        "source": str(row.get("source") or "auto"),
        "score": num("score"),
        "rr": num("rr", "r_target"),
        "confidence": num("confidence"),
        "entry": num("entry", "entry_price"),
        "stop": num("stop"),
        "target1": num("target1"),
        "close": num("close"),
        "reasons": str(row.get("reasons") or ""),
    }


def review_one(row: dict[str, Any], population: Sequence[dict],
               *, provider_id: str = "ollama") -> dict[str, Any]:
    """يراجع صفّاً واحداً ويحفظ الحكم — مقبولاً كان أو مرفوضاً."""
    from .advise import advise_prospective

    setup = setup_from_row(row)
    t0 = time.perf_counter()
    adv = advise_prospective(setup, population, provider_id=provider_id)
    pack = adv.pack
    why = pack.why

    rec: dict[str, Any] = {
        "id": "v_" + uuid.uuid4().hex[:16],
        "at": datetime.now(timezone.utc).isoformat(),
        "kind": "prospective",
        "type": "automatic",
        "symbol": setup["symbol"],
        "market": setup["market"],
        "timeframe": setup["timeframe"],
        "provider": adv.provider,
        "model": adv.model,
        "attempts": adv.attempts,
        "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        "accepted": adv.accepted,
        "fields": adv.verdict.fields if adv.accepted else {},
        # ═══ الرفض يُحفظ بسببه ═══
        #
        # معدّل الرفض أصدق مقياسٍ لصلاحية النموذج للمهمّة.
        # وإسقاطه صامتاً يجعل السجلّ يبدو سليماً وهو ناقص.
        "rejected_because": "" if adv.accepted
                            else adv.verdict.rejected_because,
        "evidence": pack.as_prompt_block(),
        "population": len(population),
        "note": pack.note,
        "rate": (None if pack.rate is None or not pack.rate.readable else {
            "wins": pack.rate.wins, "total": pack.rate.total,
            "pct": round(pack.rate.pct), "edge": round(pack.rate.edge),
            "baseline": round(pack.rate.baseline * 100),
            "significant": pack.rate.significant,
            "arabic": pack.rate.arabic(),
        }),
        "why": (None if why is None else {
            "headline": why.headline(),
            "tested": why.tested, "survived": why.survived,
            "supporting": [r.arabic() for r in why.supporting],
            "opposing": [r.arabic() for r in why.opposing],
            "untested": len(why.untested),
        }),
    }
    verdict_store.append(rec)
    return rec


def review_candidates(rows: Sequence[dict[str, Any]],
                      population: Sequence[dict],
                      *, provider_id: str = "ollama",
                      max_items: int = MAX_ITEMS,
                      on_step=None) -> list[dict[str, Any]]:
    """يراجع مرشّحي جولة مسح — ولا يرمي أبداً.

    عطبُ النموذج أو انقطاع الشبكة يجب ألّا يُسقط المسح: المراجعة
    إضافةٌ على المسح لا شرطٌ له.
    """
    todo = [r for r in rows if is_actionable(r)][:max_items]
    out: list[dict[str, Any]] = []
    for i, row in enumerate(todo, 1):
        try:
            rec = review_one(row, population, provider_id=provider_id)
            out.append(rec)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّرت مراجعة %s: %s",
                        row.get("symbol"), str(exc)[:120])
            continue
        if on_step:
            try:
                on_step(i, len(todo), rec)
            except Exception:  # noqa: BLE001
                pass
    return out


def summarize(records: Sequence[dict[str, Any]]) -> str:
    """سطرٌ للطرفية — والرفض معلنٌ فيه."""
    if not records:
        return "لا مرشّح قابل للتنفيذ — لم يُنادَ النموذج"
    acc = [r for r in records if r.get("accepted")]
    counts: dict[str, int] = {}
    for r in acc:
        d = str((r.get("fields") or {}).get("القرار") or "—")
        counts[d] = counts.get(d, 0) + 1
    parts = " · ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    return (f"أحكام: {len(acc)} من {len(records)}"
            + (f" · {parts}" if parts else "")
            + (f" · مرفوض {len(records) - len(acc)}"
               if len(records) > len(acc) else ""))


__all__ = ["review_candidates", "review_one", "setup_from_row",
           "is_actionable", "summarize", "MAX_ITEMS", "ACTIONABLE"]
