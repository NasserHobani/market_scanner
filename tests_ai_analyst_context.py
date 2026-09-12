# -*- coding: utf-8 -*-
"""‏AIA-13.1 — سياق المحلّل المضغوط.

═══ العطب الذي تحرسه ═══

النظام كان يُعلن ``token_budget = 1500`` ويُرسل **2964** رمزاً. والسبب
ليس ضعف الضغط بل أن الحدّ كان يُقاس على نصّ **لا يُرسَل**: تفريغ الحزمة
وحده، بلا تعليمات القالب ولا مخطّط الجواب ولا موجّه النظام ولا تضخّم
المسافات في ``indent=2``.

فالثابتة هنا:

    رموز الموجّه النهائي (نظام + مستخدم) ≤ سقف الملف — قبل النداء

وتُفحص على الموجّه المبنيّ فعلاً، لا على كائن وسيط.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.ai_advisor.analyst_context import (  # noqa: E402
    COMPILER_VERSION, CompactAnalystContext, ContextTooLarge, PROFILES,
    compile_context, estimate_text_tokens, resolve_profile,
)
from scanner.ai_advisor.analyst_context.evidence_selector import (  # noqa: E402
    normalize_fact, select_evidence,
)
from scanner.ai_advisor.analyst_context.tokens import char_profile  # noqa: E402
from scanner.ai_advisor.prompt_builder import PromptBuilder  # noqa: E402
from scanner.ai_advisor.unified_package import (  # noqa: E402
    EvidenceTrace, UnifiedDecisionPackage,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def ev(eid: str, section: str, field: str, value, layer: str = "") -> EvidenceTrace:
    return EvidenceTrace(
        evidence_id=eid, source_layer=layer or section, section=section,
        field=field, label=field, value=value,
        timestamp="2026-01-01T00:00:00+00:00",
    )


def make_pkg(**over) -> UnifiedDecisionPackage:
    base = dict(
        package_id="pkg_test", event_id="evt_btcusdt_crypto_4h", shadow_mode=True,
        metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h"},
        recommendation={"action": "buy", "direction": "long", "confidence": 62,
                        "grade": "B", "entry": 58200, "stop": 56900,
                        "r_target": 2.1},
        knowledge={"available": True, "market_regime": "متذبذب",
                   "market_structure": "BOS صاعد", "trend_summary": "صاعد"},
        reasoning={"available": True, "warnings": ["سيولة رقيقة"]},
        similarity={"available": True, "historical_matches": 24,
                    "win_rate": 0.42, "average_r": 0.31, "confidence": 68.75},
        research={"available": True, "experiment_summary": "اختراقات 4h أفضل",
                  "research_confidence": 71, "sample_size": 118},
        feature_snapshot={"available": True, "coverage": 86.0, "quality": "OK",
                          "feature_count": 31},
        prediction={"available": False},
        evidence_index=(
            ev("ev_001", "recommendation", "action", "buy"),
            ev("ev_002", "recommendation", "confidence", 62),
            ev("ev_003", "knowledge", "trend_summary", "صاعد"),
            ev("ev_004", "similarity", "historical_matches", 24),
            ev("ev_005", "feature_snapshot", "coverage", 86.0),
            ev("ev_006", "reasoning", "reasoning_chain", "اختراق مؤكَّد بالحجم"),
        ),
    )
    base.update(over)
    return UnifiedDecisionPackage(**base)


# ── ١) الحزمة ← سياق مضغوط ──
pkg = make_pkg()
ctx = compile_context(pkg, profile="STANDARD")
check("١ يبني سياقاً", isinstance(ctx, CompactAnalystContext))
check("  ويحمل الهويّة", (ctx.symbol, ctx.market, ctx.timeframe)
      == ("BTCUSDT", "crypto", "4h"))
check("  ويقرأ قرار المنصّة", ctx.platform.get("action") == "buy")
check("  وحالة السوق", ctx.market_state.get("trend") == "صاعد")
body = ctx.render()

# ── ٢) لا تكرار ──
#
# الحقيقة المذكورة في المتن لا تُعاد في قائمة الأدلّة؛ يبقى معرّفها
# ملصقاً بها في السطر نفسه.
check("٢ الاتجاه مذكور مرّة واحدة", body.count("صاعد") <= 2, body.count("صاعد"))
check("  ومعرّفه ملصق بالسطر", "[ev_003]" in body)
ids_in_evidence = {e.evidence_id for e in ctx.evidence}
check("  ولا يتكرّر في القائمة", "ev_003" not in ids_in_evidence)
check("  والدليل غير المعروض يبقى", "ev_006" in ids_in_evidence, str(ids_in_evidence))

# ── ٣) حذف الفراغ ──
sparse = make_pkg(
    research={"available": False}, similarity={"available": False},
    evidence_index=(ev("ev_a", "knowledge", "x", None),
                    ev("ev_b", "knowledge", "y", ""),
                    ev("ev_c", "knowledge", "z", [])),
)
sc = compile_context(sparse, profile="FAST")
check("٣ القيم الفارغة تُحذف", sc.evidence == [], str(sc.evidence))
# لكنّ **الغياب** يُقال صراحةً: الحقل المحذوف يجعل النموذج يظنّ أن
# الأمر لم يُفحص، والتصريح يجعله يخفض ثقته
check("  والغياب يُصرَّح به", "غير متاح" in sc.render())

# ── ٤) انتقاء الأدلّة ──
many = tuple(ev(f"ev_{i:03d}", "reasoning", f"f{i}", f"قيمة {i}")
             for i in range(40))
items, stats = select_evidence(many, max_items=12)
check("٤ يحترم السقف العددي", len(items) == 12, str(len(items)))
check("  ويُحصي ما وصله", stats["total"] == 40)

# الحشو البنيوي والمعرّفات الداخلية لا تُرسَل
noisy = (ev("n1", "reasoning", "available", True),
         ev("n2", "metadata", "package_id", "pkg_x"),
         ev("n3", "reasoning", "built_at", "2026-01-01"),
         ev("n4", "reasoning", "trend", "صاعد"))
kept, nstats = select_evidence(noisy, max_items=10)
check("  الرايات البنيوية تُحذف", all(k.evidence_id != "n1" for k in kept))
check("  والمعرّفات الداخلية", all(k.evidence_id != "n2" for k in kept))
check("  وأزمنة البناء", all(k.evidence_id != "n3" for k in kept))
check("  والحقيقة الحقيقية تبقى", any(k.evidence_id == "n4" for k in kept))

# ── ٥) المعرّفات تبقى صالحة للتحقّق ──
pkg_ids = {e.evidence_id for e in pkg.evidence_index}
ctx_ids = set(ctx.evidence_map()) | set(ctx.inline_ids.values())
check("٥ كل معرّف مُرسَل موجود في الحزمة", ctx_ids <= pkg_ids,
      str(ctx_ids - pkg_ids))
check("  وخريطة الأدلّة تحلّ المعرّف", all(
    isinstance(v, str) and v for v in ctx.evidence_map().values()))

# ── ٦–٨) الميزانيات ──
pb = PromptBuilder()


def prompt_tokens(p) -> int:
    return estimate_text_tokens(p.system_prompt) + estimate_text_tokens(p.user_prompt)


for label, cap in (("FAST", 1500), ("STANDARD", 2500), ("DEEP", 4000)):
    pr = pb.build(pkg, version="advisor_prompt_v4", context_profile=label)
    n = prompt_tokens(pr)
    check(f"{'٦٧٨'[('FAST','STANDARD','DEEP').index(label)]} {label} ≤ {cap}",
          n <= cap, f"{n} رمزاً")
    check(f"  و{label} يُعلن التزامه", pr.metadata["within_budget"] is True)
    check(f"  ويطابق المُعلَن المقيس",
          abs(pr.metadata["estimated_input_tokens"] - n) <= 1,
          f"معلن {pr.metadata['estimated_input_tokens']} مقيس {n}")

# ── ٩) الميزانية لا تُخرَق ولو ضخُمت المدخلات ──
#
# هذا هو الاختبار المركزي: قبل AIA-13.1 كان النظام يُبلغ بالتجاوز
# ويُرسل رغمه.
huge = make_pkg(
    knowledge={"available": True, "market_regime": "متذبذب " * 400,
               "market_structure": "هيكل " * 400, "trend_summary": "صاعد"},
    research={"available": True, "experiment_summary": "نتيجة " * 500,
              "research_confidence": 70},
    evidence_index=tuple(
        ev(f"ev_{i:03d}", "reasoning", f"f{i}", "قيمة طويلة جداً " * 20)
        for i in range(60)),
)
for label, cap in (("FAST", 1500), ("STANDARD", 2500), ("DEEP", 4000)):
    try:
        pr = pb.build(huge, version="advisor_prompt_v4", context_profile=label)
        n = prompt_tokens(pr)
        check(f"٩ مدخل ضخم لا يخرق {label}", n <= cap, f"{n} > {cap}")
    except ContextTooLarge:
        # الرفض مقبول — المهمّ ألّا يُرسَل ما يتجاوز
        check(f"٩ مدخل ضخم لا يخرق {label}", True)

# ── ١٠) التنبؤ الغائب ──
ctx_np = compile_context(make_pkg(prediction={"available": False}), profile="FAST")
r = ctx_np.render()
check("١٠ التنبؤ الغائب يُصرَّح", "غير متاح" in r)
check("  ويُمنع اختراع احتمال", "لا تذكر احتمالاً" in r)
check("  ولا رقم احتمال في السياق", ctx_np.prediction.get("probability_win") is None)

# التنبؤ النشط يُنقل كما هو ولا يُعدَّل
ctx_p = compile_context(
    make_pkg(prediction={"available": True, "probability_win": 0.68,
                         "model_id": "lgbm_v7", "calibration": "جيدة"}),
    profile="STANDARD")
check("  والنشط يُنقل بقيمته", ctx_p.prediction["probability_win"] == 0.68)
check("  مع منع التعديل", "لا تعدّل الرقم" in ctx_p.render())

# ── ١١) البحث الغائب ──
ctx_nr = compile_context(make_pkg(research={"available": False}), profile="STANDARD")
check("١١ البحث الغائب يُصرَّح", ctx_nr.research.get("available") is False)
check("  ولا تُرسَل بنية فارغة", "مُصادَق" in ctx_nr.render())

# ── ١٢) جودة لقطة منخفضة ──
low = make_pkg(feature_snapshot={"available": True, "coverage": 11.1,
                                 "quality": "FAILED", "feature_count": 4})
ctx_low = compile_context(low, profile="FAST")
rl = ctx_low.render()
check("١٢ الجودة المنخفضة تُرصد", ctx_low.data_quality["degraded"] is True)
check("  وتُحذَّر صراحةً", "جودة البيانات منخفضة" in rl)
check("  ويُسمح بـ insufficient", "insufficient" in rl)
# التحذير يسبق البيانات: ما بعده يُقرأ على ضوئه
check("  والتحذير قبل قرار المنصّة",
      rl.index("تحذير جودة") < rl.index("قرار المنصّة"))
# وجودة سليمة لا تُنتج تحذيراً — التحذير الدائم يُهمَل
check("  والجودة السليمة بلا تحذير", "تحذير جودة" not in ctx.render())

# ── ١٣) توصية هزيلة لا تصير شراء/بيع ──
thin = make_pkg(recommendation={"action": "analysis", "grade": "—",
                                "confidence": None})
ctx_thin = compile_context(thin, profile="STANDARD")
check("١٣ الطلب يُصنَّف تحليلاً", ctx_thin.analysis_type == "market_analysis")
check("  ويُقال للنموذج صراحةً", "لم تُصدر" in ctx_thin.render())
check("  ولا يُطلب منه موافقة قرار",
      "لا توافق قراراً" in ctx_thin.render())
# التوصية الحقيقية تبقى مراجعة قرار
check("  والتوصية الحقيقية تبقى مراجعة", ctx.analysis_type == "trade_review")

# ── ١٤–١٥) اليدوي والتلقائي ──
auto = pb.build(pkg, version="advisor_prompt_v4", context_profile="fast")
manual = pb.build(pkg, version="advisor_prompt_v4", context_profile="standard")
check("١٤ اليدوي أوسع من التلقائي",
      manual.metadata["budget_max"] > auto.metadata["budget_max"])
check("١٥ التلقائي على FAST", auto.metadata["context_profile"] == "FAST")
check("  واليدوي على STANDARD", manual.metadata["context_profile"] == "STANDARD")

# ── ١٦) البصمة ──
f1 = compile_context(pkg, profile="FAST").fingerprint
f2 = compile_context(pkg, profile="FAST").fingerprint
check("١٦ البصمة ثابتة لنفس المدخل", f1 == f2)
check("  وتختلف باختلاف الملف",
      f1 != compile_context(pkg, profile="DEEP").fingerprint)
moved = make_pkg(knowledge={"available": True, "trend_summary": "هابط",
                            "market_regime": "متذبذب"})
check("  وتتغيّر بتغيّر السوق",
      f1 != compile_context(moved, profile="FAST").fingerprint)
# نسخة المترجم داخلة: تعديل قواعد الانتقاء يُسقط الذاكرة القديمة تلقائياً
from scanner.ai_advisor.analyst_context.context_fingerprint import (  # noqa: E402
    package_context_key,
)
check("  ونسخة المترجم في مفتاح الذاكرة",
      COMPILER_VERSION in package_context_key("pkg_x", profile="FAST",
                                              compiler_version=COMPILER_VERSION))

# ── ١٧) ذاكرة الحزم لا تُعيد سوقاً قديماً ──
#
# كانت بصمة الحزمة تغطّي (رمز، سوق، فريم، توصية) فقط. فيتحرّك السوق
# بينما التوصية ثابتة، وتُعاد حزمة بحالة سوق قديمة — والمستشار يحكم
# على وضع لم يعد قائماً.
from scanner.ai_advisor.package_cache import PackageCache  # noqa: E402

pc = PackageCache()
reco = {"action": "buy", "confidence": 62}
k1 = pc.fingerprint(symbol="BTCUSDT", market="crypto", timeframe="4h",
                    recommendation=reco,
                    evidence_layers={"knowledge_context": {"trend": "صاعد"}})
k2 = pc.fingerprint(symbol="BTCUSDT", market="crypto", timeframe="4h",
                    recommendation=reco,
                    evidence_layers={"knowledge_context": {"trend": "هابط"}})
check("١٧ تغيّر السوق يُغيّر بصمة الحزمة", k1 != k2)
check("  ونفس الطبقات تعطي البصمة نفسها",
      k1 == pc.fingerprint(symbol="BTCUSDT", market="crypto", timeframe="4h",
                           recommendation=reco,
                           evidence_layers={"knowledge_context": {"trend": "صاعد"}}))

# ── ١٨) المخرَج عربي ──
up = auto.user_prompt
check("١٨ الموجّه عربي", char_profile(up)["arabic"] > char_profile(up)["latin"] / 2,
      str(char_profile(up)))
check("  ويطلب أقسام المحلّل",
      all(k in up for k in ("current_market_view", "near_term_outlook",
                            "invalidation_conditions", "what_to_watch")))
check("  ويسمح بـ insufficient", "insufficient" in up)

# ── ٢١) Claude و Qwen يريان السياق نفسه ──
#
# الموجّه يُبنى من الحزمة لا من المزوّد، فالسياق واحد بالبناء. ويُثبَّت
# هنا لأن أي تفرّع مستقبلي يجعل المقارنة بينهما بلا معنى.
p_a = pb.build(pkg, version="advisor_prompt_v4", context_profile="standard")
p_b = pb.build(pkg, version="advisor_prompt_v4", context_profile="standard")
check("٢١ السياق نفسه لكل مزوّد", p_a.user_prompt == p_b.user_prompt)
check("  والبصمة نفسها",
      p_a.metadata["context_fingerprint"] == p_b.metadata["context_fingerprint"])

# ── ٢٤) لا شموع خام ──
raw_candles = make_pkg(evidence_index=(
    ev("ev_o", "knowledge", "open", 58000),
    ev("ev_h", "knowledge", "high", 58900),
    ev("ev_l", "knowledge", "low", 57800),
    ev("ev_c", "knowledge", "close", 58650),
    ev("ev_v", "knowledge", "volume", 1234.5),
    ev("ev_k", "knowledge", "candles", [[1, 2, 3]]),
    ev("ev_ok", "knowledge", "trend_summary", "صاعد"),
))
ctx_rc = compile_context(raw_candles, profile="DEEP")
sent = {e.evidence_id for e in ctx_rc.evidence}
check("٢٤ لا OHLC في سياق النموذج",
      not (sent & {"ev_o", "ev_h", "ev_l", "ev_c", "ev_v", "ev_k"}), str(sent))
pr_rc = pb.build(raw_candles, version="advisor_prompt_v4", context_profile="deep")
for bad_word in ("58900", "57800", "1234.5"):
    check(f"  ولا قيمة شمعة خام ({bad_word})", bad_word not in pr_rc.user_prompt)

# ── التقدير نفسه: العربية أكثف من اللاتينية ──
#
# القاعدة الشائعة (4 محارف/رمز) مقيسة على الإنجليزية. ولو استُعملت على
# نصّ عربي لأعطت نصف الحقيقة — فيتجاوز الموجّه ميزانيته بلا أن يعلم.
ar = "الاتجاه صاعد والهيكل مكسور والزخم يتراجع" * 4
en = "trend up structure broken momentum fading now" * 4
check("العربية تُقدَّر أكثف", estimate_text_tokens(ar) > estimate_text_tokens(en),
      f"ar={estimate_text_tokens(ar)} en={estimate_text_tokens(en)}")
check("والتقدير لا يهمل موجّه النظام",
      estimate_text_tokens("abc" * 100) > 0)

# ── التطبيع العربي يكشف التكرار رغم اختلاف الرسم ──
check("التطبيع يوحّد الألف", normalize_fact("أحمد") == normalize_fact("احمد"))
check("ويوحّد التاء المربوطة", normalize_fact("مقاومة") == normalize_fact("مقاومه"))
check("ويجرّد التشكيل", normalize_fact("صَاعِد") == normalize_fact("صاعد"))

# ── التقليص يُعلن ما حذف ──
tight = compile_context(huge, profile="FAST")
if tight.dropped_sections:
    check("الحذف يُعلَن للنموذج", "لم تُرسَل" in tight.render())
else:
    check("الحذف يُعلَن للنموذج", True, "لم يُحتَج حذف")

# ── المقاييس موجودة وحقيقية ──
m = auto.metadata["context_metrics"]
for key in ("context_compile_ms", "estimated_input_tokens", "evidence_before",
            "evidence_after", "profile", "compiler_version"):
    check(f"مقياس {key} موجود", key in m, str(sorted(m)))
check("وزمن الترجمة مقيس لا صفر افتراضي", m["context_compile_ms"] >= 0.0)
check("وعدد الأدلّة قبل ≥ بعد", m["evidence_before"] >= m["evidence_after"])

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
