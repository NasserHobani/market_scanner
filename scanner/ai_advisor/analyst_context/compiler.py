# -*- coding: utf-8 -*-
"""المترجم: ‏UnifiedDecisionPackage ← CompactAnalystContext.

═══ الثابتة التي يحرسها هذا الملف ═══

    رموز الموجّه النهائي ≤ سقف الملف — **قبل** نداء المزوّد.

وكانت مخروقة بصمت: النظام يُعلن ``token_budget=1500`` ويُرسل 2964
رمزاً، لأن الحدّ كان يُقاس على تفريغ الحزمة لا على الموجّه.

والتقليص هنا يقع بالأولوية لا بالقصّ: القسم الذي لا يتّسع يُحذف
كاملاً ويُعلَن حذفه. ونصف جدول أسوأ من غيابه، لأن النموذج يقرأ ما وصله
ويبني عليه دون أن يعرف أن بقيّته حُذفت.

═══ ترتيب التقليص ═══

    ١. الأدلّة تُقلَّص عدداً (أرخص خسارة: الأقلّ أولويةً يذهب أوّلاً)
    ٢. ثمّ تُحذف الأقسام من أدنى الأولويات صعوداً
    ٣. فإن بقي فوق السقف بعد كل ذلك → يُرفَع خطأ ولا يُرسَل شيء

الخطوة الثالثة هي الفرق بين حدٍّ حقيقي وحدٍّ ديكوري.
"""
from __future__ import annotations

import time
from typing import Any

from .analyst_context import (
    ANALYST_CONTEXT_VERSION, CompactAnalystContext, EvidenceItem,
)
from .context_fingerprint import context_fingerprint
from .context_profiles import Profile, SECTION_PRIORITY, resolve_profile
from .evidence_selector import select_evidence
from .tokens import estimate_prompt_tokens, estimate_text_tokens

__all__ = ["compile_context", "ContextTooLarge", "COMPILER_VERSION"]

COMPILER_VERSION = "aia13.1"

# تغطية لقطة الخصائص التي تحتها تُعدّ البيانات غير كافية لتوصية واثقة.
#
# الرقم ليس اعتباطاً: تغطية 50٪ تعني أن نصف ما بُني عليه القرار مجهول،
# وأي حكم فوقه ترجيحٌ لا تحليل. والحدّ يُراجَع بالقياس حين تتوفّر عيّنة
# تربط التغطية بجودة المراجعة.
MIN_COVERAGE_PCT = 50.0

# هامش يُترك للجواب وللتقريب في التقدير
_SAFETY_TOKENS = 40


class ContextTooLarge(RuntimeError):
    """السياق تجاوز السقف بعد استنفاد كل تقليص ممكن."""


# ───────────────────────────────────────────── استخراج الحقائق

# أطول قيمة مفردة تُرسَل. لا محلّل يحتاج وصف «هيكل» بألف محرف؛ وحقل
# واحد منفلت الطول يكفي لخرق الميزانية وحده حتى بعد حذف كل قسم قابل
# للحذف — وهو ما وقع فعلاً في الاختبار.
MAX_FIELD_CHARS = 160


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    """يقصّ القيمة النصّية الطويلة ويُبقي علامة القصّ ظاهرة."""
    if isinstance(value, str) and len(value) > limit:
        return value[:limit].rstrip() + "…"
    return value


def _f(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    return _clip(value)


def _pick(src: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        if isinstance(src, dict) and src.get(k) not in (None, "", [], {}):
            return _clip(src[k])
    return default


def _platform(pkg) -> tuple[dict, str]:
    """قرار المنصّة، ونوع التحليل المستنتَج منه.

    ‏``action=analysis`` بلا اتجاه ولا ثقة ليست توصية تداول. وتمريرها
    كأنها توصية يدفع النموذج إلى «موافقة» أو «مخالفة» قرارٍ لم يصدر —
    فيخترع قراراً ثمّ يحكم عليه.
    """
    reco = dict(getattr(pkg, "recommendation", {}) or {})
    action = str(reco.get("action") or "").strip().lower()
    direction = _pick(reco, "direction", "side")
    confidence = reco.get("confidence")

    sparse = (action in ("", "analysis", "none")
              and not direction and confidence in (None, ""))
    analysis_type = "market_analysis" if sparse else "trade_review"

    return {
        "action": reco.get("action"), "direction": direction,
        "score": _f(_pick(reco, "score")), "confidence": _f(confidence),
        "grade": reco.get("grade"), "rr": _f(_pick(reco, "rr", "r_target")),
        "entry": _f(reco.get("entry")), "stop": _f(reco.get("stop")),
    }, analysis_type


def _market_state(pkg) -> dict:
    """حالة السوق من الأشكال التي تُنتجها المحوّلات فعلاً.

    المحوّلات (``layer_adapters``) تُعيد تسمية الحقول وتُسقط ما ليس في
    عقدها. فقراءة ``trend`` أو ``momentum`` مباشرةً لا تُصيب شيئاً —
    الأسماء الحقيقية ``trend_summary`` و``market_regime`` وما شابه.
    والأسماء البديلة مذكورة أيضاً لتحمّل مصادر أخرى (البتكوين، التحليل
    اليدوي) التي لا تمرّ بنفس المحوّلات.
    """
    reasoning = dict(getattr(pkg, "reasoning", {}) or {})
    knowledge = dict(getattr(pkg, "knowledge", {}) or {})
    merged = {**knowledge, **{k: v for k, v in reasoning.items()
                              if v not in (None, "", [], {})}}
    return {
        "trend": _pick(merged, "trend_summary", "trend", "trend_direction",
                       "direction"),
        "trend_strength": _f(_pick(merged, "trend_strength", "strength",
                                   "final_score")),
        "regime": _pick(merged, "market_regime", "regime"),
        "structure": _pick(merged, "market_structure", "structure"),
        "momentum": _pick(merged, "momentum", "rsi_state", "rsi"),
        "volume": _pick(merged, "volume", "volume_state", "rvol"),
        "volatility": _pick(merged, "volatility", "atr_pct"),
        "patterns": _pick(merged, "detected_patterns"),
        "facts": (merged.get("knowledge_facts") or [])[:4] or None,
    }


def _historical(pkg) -> dict:
    sim = dict(getattr(pkg, "similarity", {}) or {})
    # ‏adapt_similarity تُسمّيها historical_matches؛ والأسماء الأخرى
    # لمصادر لا تمرّ بالمحوّل
    matches = _pick(sim, "historical_matches", "matches", "match_count",
                    "count", default=0)
    try:
        matches = int(matches or 0)
    except (TypeError, ValueError):
        matches = 0
    out = {
        "matches": matches,
        "similarity_score": _f(_pick(sim, "confidence", "similarity_score",
                                     "score")),
        "win_rate": _f(_pick(sim, "win_rate", "historical_win_rate")),
        "expectancy": _f(_pick(sim, "average_r", "expectancy",
                               "historical_expectancy")),
    }
    # عيّنة صغيرة تُعلَن صغيرة: نسبة نجاح من ثلاث حالات ليست نسبة
    if 0 < matches < 20:
        out["sample_note"] = f"عيّنة غير كافية ({matches} < 20)"
    return out


def _research(pkg) -> dict:
    r = dict(getattr(pkg, "research", {}) or {})
    if not r or r.get("available") is False:
        return {"available": False,
                "reason": r.get("reason") or "لا نتائج مُصادَق عليها"}
    def _as_findings(value) -> list[str]:
        """يحوّل نتائج البحث إلى أسطر مقروءة.

        ‏``comparison_results`` قاموس، والتكرار عليه مباشرةً يُخرج أسماء
        المفاتيح («verdict»، «p_value») بلا قيمها — أي ضجيج بلا معنى.
        """
        if isinstance(value, dict):
            return [f"{k}: {v}" for k, v in value.items()
                    if v not in (None, "", [], {})]
        if isinstance(value, (list, tuple)):
            return [str(x) for x in value if x not in (None, "", [], {})]
        return [str(value)] if value not in (None, "", [], {}) else []

    findings = (_as_findings(r.get("validated_findings"))
                or _as_findings(r.get("hypothesis_evidence"))
                or _as_findings(r.get("findings"))
                or _as_findings(r.get("comparison_results")))
    summary = r.get("experiment_summary")
    if not findings and not summary:
        return {"available": False, "reason": "لا نتائج مُصادَق عليها"}
    # عيّنة صغيرة تُعلَن: نتيجة من عشر حالات ليست نتيجة
    sample = r.get("sample_size")
    out = {"available": True,
           "confidence": _f(_pick(r, "research_confidence", "confidence")),
           "findings": [str(x)[:140] for x in list(findings)[:5]]}
    if summary:
        out["findings"].insert(0, str(summary)[:140])
    try:
        if sample is not None and int(sample) < 20:
            out["findings"].append(f"عيّنة غير كافية ({sample} < 20)")
    except (TypeError, ValueError):
        pass
    return out


def _prediction(pkg) -> dict:
    p = dict(getattr(pkg, "prediction", {}) or {})
    if not p.get("available"):
        return {"available": False,
                "reason": p.get("reason") or "لا نموذج نشط اجتاز بوابة الجودة"}
    return {"available": True,
            "model": p.get("model_id") or p.get("model") or "LightGBM",
            "probability_win": _f(p.get("probability_win")),
            "calibration": p.get("calibration"), "oos": p.get("oos"),
            "baseline": _f(p.get("baseline"))}


def _features(pkg) -> dict:
    fi = dict(getattr(pkg, "feature_intelligence", {}) or {})
    if not fi or fi.get("available") is False:
        return {"available": False}
    top = fi.get("top_features") or fi.get("top") or []
    return {"available": True,
            "top": [str(x)[:40] for x in list(top)[:5]],
            "stability": _f(fi.get("stability")),
            "drift": _f(fi.get("drift")),
            "quality": fi.get("feature_quality"),
            "warnings": [str(x)[:80] for x in (fi.get("warnings") or [])[:3]]}


def _data_quality(pkg) -> dict:
    snap = dict(getattr(pkg, "feature_snapshot", {}) or {})
    coverage = snap.get("coverage")
    try:
        cov = float(coverage) if coverage is not None else None
    except (TypeError, ValueError):
        cov = None
    quality = str(snap.get("quality") or "").upper()
    degraded = bool(
        (cov is not None and cov < MIN_COVERAGE_PCT)
        or quality in ("FAILED", "POOR")
        or not snap.get("available", True)
    )
    return {
        "coverage": f"{cov:.1f}%" if cov is not None else None,
        "quality": quality or None,
        "feature_count": snap.get("feature_count"),
        "missing": [str(x)[:40] for x in (snap.get("missing_categories") or [])[:5]],
        "degraded": degraded,
        "coverage_pct": cov,
    }


def _risk(pkg) -> dict:
    dai = dict(getattr(pkg, "decision_ai", {}) or {})
    reasoning = dict(getattr(pkg, "reasoning", {}) or {})
    risks = (dai.get("key_risks") or dai.get("risks") or dai.get("warnings")
             or reasoning.get("risks") or reasoning.get("warnings") or [])
    return {"key_risks": [str(x)[:120] for x in list(risks)[:5]]}


def _contradictions(pkg, market: dict) -> list[str]:
    out: list[str] = []
    dai = dict(getattr(pkg, "decision_ai", {}) or {})
    for c in (dai.get("contradictions") or [])[:4]:
        out.append(str(c)[:120])
    trend = str(market.get("trend") or "").lower()
    momentum = str(market.get("momentum") or "").lower()
    if trend and momentum:
        up = {"bullish", "up", "صاعد"}
        down = {"bearish", "down", "هابط"}
        if (trend in up and momentum in down) or (trend in down and momentum in up):
            out.append(f"الاتجاه {market['trend']} بينما الزخم {market['momentum']}")
    return out


# ───────────────────────────────────────────── الترجمة

def compile_context(package, *, profile: str = "STANDARD",
                    system_prompt: str = "",
                    prompt_overhead_tokens: int = 0,
                    analysis_type: str | None = None) -> CompactAnalystContext:
    """يبني السياق المضغوط ويضمن دخوله السقف.

    Parameters
    ----------
    prompt_overhead_tokens:
        رموز ما يحيط بالسياق في الموجّه (تعليمات، مخطّط الجواب). تُحسب
        ضمن الميزانية لأن النموذج يقرأها كما يقرأ السياق — وإهمالها هو
        عين العطب الذي نعالجه.
    """
    t0 = time.monotonic()
    prof: Profile = resolve_profile(profile)
    meta = dict(getattr(package, "metadata", {}) or {})

    platform, inferred_type = _platform(package)
    market = _market_state(package)

    ctx = CompactAnalystContext(
        symbol=meta.get("symbol", ""), market=meta.get("market", ""),
        timeframe=meta.get("timeframe", ""),
        analysis_type=analysis_type or inferred_type,
        platform=platform, market_state=market,
        historical=_historical(package), research=_research(package),
        prediction=_prediction(package), features=_features(package),
        risk=_risk(package), data_quality=_data_quality(package),
        profile=prof.name, version=ANALYST_CONTEXT_VERSION,
    )
    ctx.contradictions = _contradictions(package, market)

    # الحقائق التي وردت في المتن — كي لا تتكرّر في الأدلّة
    ctx.inline_ids = _build_inline_ids(package, ctx)

    evidence, ev_stats = select_evidence(
        getattr(package, "evidence_index", ()) or (),
        max_items=prof.max_evidence,
        already_stated=_stated_facts(ctx),
        stated_text=ctx.render(),
        covered_fields=_covered_fields(ctx) | {
            ("knowledge", "knowledge_facts"), ("knowledge", "detected_patterns"),
        },
    )
    ctx.evidence = evidence

    ctx.fingerprint = context_fingerprint(
        ctx, profile=prof.name, compiler_version=COMPILER_VERSION)

    # ── فرض الميزانية ──
    ceiling = prof.hard_max_tokens - prompt_overhead_tokens - _SAFETY_TOKENS
    ctx = _fit(ctx, ceiling=ceiling, target=prof.target_tokens
               - prompt_overhead_tokens - _SAFETY_TOKENS)

    rendered = ctx.render()
    final_tokens = estimate_prompt_tokens(system_prompt, rendered)
    if final_tokens + prompt_overhead_tokens > prof.hard_max_tokens:
        raise ContextTooLarge(
            f"السياق {final_tokens + prompt_overhead_tokens} رمزاً يتجاوز سقف "
            f"{prof.name} ({prof.hard_max_tokens}) بعد استنفاد التقليص"
        )

    ctx.metrics = {
        "context_compile_ms": round((time.monotonic() - t0) * 1000, 2),
        "context_tokens": estimate_text_tokens(rendered),
        "system_tokens": estimate_text_tokens(system_prompt),
        "prompt_overhead_tokens": prompt_overhead_tokens,
        "estimated_input_tokens": final_tokens + prompt_overhead_tokens,
        "profile": prof.name,
        "budget_target": prof.target_tokens,
        "budget_max": prof.hard_max_tokens,
        "evidence_before": ev_stats["total"],
        "evidence_after": len(ctx.evidence),
        "evidence_dropped_empty": ev_stats["empty"],
        "evidence_dropped_duplicate": ev_stats["duplicate"],
        "evidence_dropped_noise": ev_stats["noise"],
        "evidence_dropped_ohlc": ev_stats["ohlc"],
        "sections_dropped": list(ctx.dropped_sections),
        "compiler_version": COMPILER_VERSION,
    }
    return ctx


# ربط (قسم، حقل) في الحزمة ← (قسم السياق، مفتاحه).
#
# المطابقة النصّية وحدها لا تكفي: المتن يكتب «القرار: buy» والدليل يكتب
# «recommendation.action: buy» — نفس الحقيقة بلغتين ولا تشابه حرفياً
# بينهما. فالمنع بالاسم البنيوي.
#
# والشرط أن تكون القيمة **معروضة فعلاً**، لا أن يكون القسم موجوداً:
# منعُ كل حقول قسمٍ لمجرّد وجوده يحذف أدلّة لم تُعرض قطّ — وهو ما جعل
# الأدلّة تنزل إلى صفر في أول محاولة.
_FIELD_TO_CONTEXT: dict[tuple[str, str], tuple[str, str]] = {
    ("recommendation", "action"): ("platform", "action"),
    ("recommendation", "direction"): ("platform", "direction"),
    ("recommendation", "side"): ("platform", "direction"),
    ("recommendation", "confidence"): ("platform", "confidence"),
    ("recommendation", "grade"): ("platform", "grade"),
    ("recommendation", "entry"): ("platform", "entry"),
    ("recommendation", "stop"): ("platform", "stop"),
    ("recommendation", "rr"): ("platform", "rr"),
    ("recommendation", "r_target"): ("platform", "rr"),
    ("recommendation", "score"): ("platform", "score"),

    ("knowledge", "trend_summary"): ("market_state", "trend"),
    ("knowledge", "market_regime"): ("market_state", "regime"),
    ("knowledge", "market_structure"): ("market_state", "structure"),
    ("knowledge", "final_score"): ("market_state", "trend_strength"),

    ("similarity", "historical_matches"): ("historical", "matches"),
    ("similarity", "win_rate"): ("historical", "win_rate"),
    ("similarity", "average_r"): ("historical", "expectancy"),
    ("similarity", "confidence"): ("historical", "similarity_score"),

    ("prediction", "probability_win"): ("prediction", "probability_win"),
    ("prediction", "model_id"): ("prediction", "model"),
    ("prediction", "calibration"): ("prediction", "calibration"),

    ("feature_snapshot", "coverage"): ("data_quality", "coverage"),
    ("feature_snapshot", "quality"): ("data_quality", "quality"),
    ("feature_snapshot", "feature_count"): ("data_quality", "feature_count"),

    ("research", "research_confidence"): ("research", "confidence"),
    ("research", "experiment_summary"): ("research", "findings"),
}


def _build_inline_ids(package, ctx: CompactAnalystContext) -> dict[str, str]:
    """مفتاح السياق ← معرّف الدليل، من فهرس الحزمة.

    يُبنى بالبحث عن (قسم، حقل) في ``evidence_index``. فما عُرض في المتن
    يحمل معرّفه، وما لم يُعرض يبقى في قائمة الأدلّة بنصّه.
    """
    by_field: dict[tuple[str, str], str] = {}
    for ref in getattr(package, "evidence_index", ()) or ():
        key = (str(getattr(ref, "section", "") or "").lower(),
               str(getattr(ref, "field", "") or "").lower())
        by_field.setdefault(key, str(getattr(ref, "evidence_id", "") or ""))

    out: dict[str, str] = {}
    for pkg_key, (attr, ctx_key) in _FIELD_TO_CONTEXT.items():
        eid = by_field.get(pkg_key)
        if not eid:
            continue
        section = getattr(ctx, attr, None)
        if isinstance(section, dict) and section.get(ctx_key) not in (None, "", [], {}):
            out.setdefault(f"{attr}.{ctx_key}", eid)
    # معالم المعرفة وأنماطها ليستا في الخريطة أعلاه لأنهما مجمَّعتان
    for pkg_key, ctx_path in (
        (("knowledge", "knowledge_facts"), "market_state.facts"),
        (("knowledge", "detected_patterns"), "market_state.patterns"),
    ):
        eid = by_field.get(pkg_key)
        if eid:
            out.setdefault(ctx_path, eid)
    return out


def _covered_fields(ctx: CompactAnalystContext) -> set[tuple[str, str]]:
    """‏(قسم، حقل) لما ظهر في المتن بقيمة فعلية — لا يُعاد في الأدلّة."""
    out: set[tuple[str, str]] = set()
    for pkg_key, (attr, key) in _FIELD_TO_CONTEXT.items():
        section = getattr(ctx, attr, None)
        if not isinstance(section, dict):
            continue
        if section.get(key) not in (None, "", [], {}):
            out.add(pkg_key)
    return out


def _stated_facts(ctx: CompactAnalystContext) -> list[str]:
    """ما ذُكر في المتن — أساس كشف التكرار في الأدلّة.

    يُقاس على **النصّ المعروض نفسه** لا على قائمة تُبنى يدوياً: القائمة
    اليدوية تتخلّف عن العرض كلّما أُضيف حقل، فيعود التكرار من حيث لا
    نشعر. والقيمة وحدها تُضاف كذلك، لأن «11.1» في المتن و«coverage:
    11.1» في الأدلّة حقيقة واحدة بصياغتين.
    """
    out: list[str] = []
    for src in (ctx.market_state, ctx.platform, ctx.data_quality,
                ctx.historical, ctx.prediction):
        for key, val in (src or {}).items():
            if val not in (None, "", [], {}, False):
                out.append(f"{key}: {val}")
                out.append(str(val))
    return out


_ALWAYS_KEEP = {"identity", "data_quality", "platform", "market"}

_SECTION_ATTR = {
    "platform": "platform", "market": "market_state",
    "historical": "historical", "research": "research",
    "prediction": "prediction", "features": "features",
    "risk": "risk", "data_quality": "data_quality",
    "contradictions": "contradictions", "notes": "notes",
}


def _fit(ctx: CompactAnalystContext, *, ceiling: int,
         target: int) -> CompactAnalystContext:
    """يقلّص حتى يبلغ الهدف، ولا يتجاوز السقف."""
    if ceiling <= 0:
        return ctx

    def size() -> int:
        return estimate_text_tokens(ctx.render())

    if size() <= target:
        return ctx

    # ١) الأدلّة أولاً — الأقلّ أولويةً يذهب أوّلاً
    while ctx.evidence and size() > target:
        ctx.evidence = sorted(ctx.evidence, key=lambda e: e.priority)[:-1]

    if size() <= ceiling:
        return ctx

    # ٢) ثمّ الأقسام، من أدنى الأولويات صعوداً
    for section in reversed(SECTION_PRIORITY):
        if size() <= ceiling:
            break
        if section in _ALWAYS_KEEP:
            continue
        attr = _SECTION_ATTR.get(section)
        if not attr:
            continue
        current = getattr(ctx, attr, None)
        if not current:
            continue
        setattr(ctx, attr, [] if isinstance(current, list) else {})
        ctx.dropped_sections.append(section)

    # ٣) قصّ أعمق للقيم قبل الاستسلام.
    #
    # حقل واحد منفلت الطول يكفي لخرق الميزانية وحده حتى بعد حذف كل
    # قسم قابل للحذف. والقصّ داخل القيمة أهون من رفض المراجعة كلّها،
    # وأصدق من حذف قسم صامتاً — فالقيمة تبقى ظاهرة بعلامة القصّ.
    for limit in (90, 50, 28):
        if size() <= ceiling:
            break
        for attr in ("market_state", "platform", "historical", "research",
                     "data_quality", "features", "risk"):
            section = getattr(ctx, attr, None)
            if isinstance(section, dict):
                setattr(ctx, attr,
                        {k: _clip(v, limit) for k, v in section.items()})
            elif isinstance(section, list):
                setattr(ctx, attr, [_clip(v, limit) for v in section])
        ctx.contradictions = [_clip(x, limit) for x in ctx.contradictions]
        ctx.evidence = [
            type(e)(e.evidence_id, str(_clip(e.fact, limit)), e.priority)
            for e in ctx.evidence
        ]

    return ctx
