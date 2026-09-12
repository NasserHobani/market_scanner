# -*- coding: utf-8 -*-
"""المستشار الجديد — أدلّةٌ مقيسة، حكمٌ مفحوص، ورفضٌ عند العجز.

═══ المسار كاملاً ═══

    صفقة/إعداد
        ↓
    evidence.py   ← يحسب الأرقام من سجلّك (٢٨٩ صفقة محسومة)
        ↓
    verdict.build_prompt   ← خمسة حقول، ومنعٌ صريح للاختراع
        ↓
    الموفّر (Ollama محلّي)
        ↓
    verdict.parse   ← يقبل أو يرفض بسببٍ مذكور
        ↓
    حكمٌ فيه رقم وقرار — أو إعلانٌ بأنّه لم يُنتَج

═══ محاولتان لا واحدة ═══

النموذج المحلّي يخطئ الصيغة أحياناً وهو قادر على الصواب. فالمحاولة
الثانية تُعطى **سبب الرفض نصّاً** — «حقلك الرقم فارغ» — فيُصلحه
غالباً. والثالثة لا تُجدي: النموذج الذي أخطأ مرّتين مع تصحيحٍ
صريح لا يعرف الجواب.

═══ ولماذا لا وضع ظلّ ═══

كانت ١٦٤ مراجعة كلّها ``shadow_mode=true`` — أي أنّها لا تُغيّر
شيئاً مهما قالت. ومستشارٌ لا يُسمَع ليس مستشاراً بل زينة.

والحكم هنا يُعرَض للمستخدم صراحةً بوصفه رأياً مسنداً بالأرقام،
ويبقى **هو** صاحب القرار. لكنّه يُعرَض لأنّه قابل للفحص: كل رقم
فيه من سجلّه، وكل قرارٍ من قائمة محدودة، وشرط الإبطال سعرٌ يمكن
مراقبته.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Sequence

from . import evidence as ev
from . import verdict as vd

log = logging.getLogger("scanner.advise")

MAX_ATTEMPTS = 2


@dataclass
class Advice:
    """نتيجة الاستشارة — ونصّها العربي جاهزاً للعرض."""

    verdict: vd.Verdict
    pack: ev.EvidencePack
    attempts: int
    latency_ms: float
    provider: str
    model: str

    @property
    def accepted(self) -> bool:
        return self.verdict.accepted

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.verdict.accepted,
            "kind": self.verdict.kind,
            "symbol": self.pack.symbol,
            "fields": self.verdict.fields,
            "rejected_because": self.verdict.rejected_because,
            "evidence": self.pack.as_prompt_block(),
            "rate": (None if self.pack.rate is None
                     else {"wins": self.pack.rate.wins,
                           "total": self.pack.rate.total,
                           "pct": round(self.pack.rate.pct, 1),
                           "low": round(100 * self.pack.rate.low),
                           "high": round(100 * self.pack.rate.high),
                           "baseline": round(self.pack.rate.baseline * 100),
                           "readable": self.pack.rate.readable,
                           "significant": self.pack.rate.significant,
                           "arabic": self.pack.rate.arabic()}),
            "attempts": self.attempts,
            "latency_ms": round(self.latency_ms, 1),
            "provider": self.provider,
            "model": self.model,
            "note": self.pack.note,
        }


def _call(provider, prompt: dict[str, str]) -> str:
    """نداء الموفّر — بواجهته الحالية، وبلا افتراض شكل الرد."""
    from .prompt_builder import AdvisorPrompt

    p = AdvisorPrompt(
        version="verdict_v1",
        system_prompt=prompt["system"],
        user_prompt=prompt["user"],
        package_id="",
        event_id="",
    )
    raw = provider.analyze(p, package=None)
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # الموفّرون يختلفون في اسم الحقل — تُجرَّب المعتادة ثمّ
        # يُسلَّم الكائن كاملاً ليجد الفاحص الـJSON داخله.
        for k in ("content", "text", "response", "raw", "message"):
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v
        import json as _json

        return _json.dumps(raw, ensure_ascii=False)
    return str(raw)


def advise(pack: ev.EvidencePack, *, provider_id: str = "ollama",
           kind: str | None = None) -> Advice:
    """يستشير النموذج على حزمة أدلّة، ويعيد حكماً مفحوصاً."""
    from .provider_registry import get_registry

    k = kind or pack.kind
    t0 = time.perf_counter()
    try:
        provider = get_registry().get(provider_id)
    except Exception as exc:  # noqa: BLE001
        return Advice(
            vd.Verdict(k, False,
                       rejected_because=f"تعذّر الموفّر {provider_id}: "
                                        f"{str(exc)[:80]}"),
            pack, 0, (time.perf_counter() - t0) * 1000, provider_id, "")

    prompt = vd.build_prompt(pack, k)
    last = vd.Verdict(k, False, rejected_because="لم تُجرَ محاولة")

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = _call(provider, prompt)
        except Exception as exc:  # noqa: BLE001
            last = vd.Verdict(k, False,
                              rejected_because=f"فشل النداء: {str(exc)[:80]}")
            break

        last = vd.parse(raw, pack, k)
        if last.accepted:
            break

        if attempt < MAX_ATTEMPTS:
            # ═══ التصحيح يُقال صراحةً ═══
            #
            # إعادة الموجّه نفسه تُنتج الخطأ نفسه. وذكر سبب الرفض
            # حرفياً يجعل النموذج يُصلحه غالباً من أوّل إعادة.
            prompt = dict(prompt)
            prompt["user"] += (
                f"\n\n— محاولتك السابقة رُفضت: {last.rejected_because}.\n"
                "أعد الجواب مصحَّحاً، بـ JSON فقط، بلا أي نصّ قبله "
                "أو بعده."
            )
            log.info("إعادة استشارة %s — %s", pack.symbol,
                     last.rejected_because)

    return Advice(last, pack, attempt, (time.perf_counter() - t0) * 1000,
                  provider_id, getattr(provider, "model_name", lambda: "")())


# ═══════════════════ مداخل جاهزة للواجهة ═══════════════════

def advise_settled(trade: dict, population: Sequence[dict],
                   *, provider_id: str = "ollama") -> Advice:
    """لماذا فازت هذه الصفقة أو خسرت."""
    return advise(ev.for_settled(trade, population),
                  provider_id=provider_id, kind="settled")


def advise_prospective(setup: dict, population: Sequence[dict],
                       *, provider_id: str = "ollama") -> Advice:
    """هل أدخل هذه الصفقة؟"""
    return advise(ev.for_prospective(setup, population),
                  provider_id=provider_id, kind="prospective")


__all__ = ["Advice", "advise", "advise_settled", "advise_prospective",
           "MAX_ATTEMPTS"]
