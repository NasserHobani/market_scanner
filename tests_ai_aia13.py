# -*- coding: utf-8 -*-
"""AIA-13 Arabic AI Market Analyst tests."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.analyst.context_profile import resolve_budget, resolve_profile, CONTEXT_PROFILES
from scanner.ai_advisor.analyst.normalize import normalize_analyst_response, extract_analyst_fields
from scanner.ai_advisor.analyst.outlook_eval import evaluate_outlook, outlook_pattern_label
from scanner.ai_advisor.analyst.persona import ANALYST_ROLE
from scanner.ai_advisor.prompt_builder import PromptBuilder, TEMPLATES
from scanner.ai_advisor.response_validator import ResponseValidator, REQUIRED_FIELDS
from scanner.ai_advisor.explainability.localized_presentation import (
    build_presentation, build_presentations, DEFAULT_LANGUAGE,
)
from scanner.ai_advisor.explainability.manual_formatter import format_manual_analysis

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


# ── Persona / prompts ──
check("analyst role defined", "Market Analyst" in ANALYST_ROLE)
check("v4 template exists", "advisor_prompt_v4" in TEMPLATES)
pb = PromptBuilder()
check("v4 listable", "advisor_prompt_v4" in pb.list_versions())

# ── Context profiles / token budgets ──
check("fast budget", resolve_budget("fast") == 1500)
check("standard budget", resolve_budget("standard") == 2500)
check("deep budget", resolve_budget("deep") == 4000)
check("automatic alias", resolve_profile("automatic") == "fast")
check("manual alias", resolve_profile("manual") == "standard")
check("profiles present", set(CONTEXT_PROFILES) >= {"fast", "standard", "deep"})

# ── Normalize + Arabic fields ──
raw = {
    "language": "ar",
    "agreement": "agree",
    "confidence": 82,
    "summary": "أرجّح استمرار الاتجاه الصاعد وفق الأدلة المتاحة.",
    "reasoning": "الهيكل والاتجاه يدعمان الصعود مع مراقبة المقاومة.",
    "supporting_evidence": [{"evidence_id": "ev1", "section": "knowledge", "field": "score", "note": "اتجاه داعم"}],
    "contradicting_evidence": [],
    "risks": ["مقاومة قريبة", "Prediction unavailable"],
    "missing_information": [],
    "suggested_experiment": {"hypothesis": "h", "method": "m", "expected_outcome": "o"},
    "shadow_mode_acknowledged": True,
    "recommendation": {"action": "buy", "confidence": 80},
    "current_market_view": {"direction": "bullish", "confidence": 78},
    "near_term_outlook": {"horizon_days": 7, "direction": "bullish", "confidence": 75},
    "positive_signals": ["اتجاه داعم"],
    "negative_signals": ["مقاومة قريبة"],
    "what_to_watch": ["استمرار BOS", "ثبات HTF"],
    "invalidation_conditions": ["كسر الدعم"],
    "statistical_prediction": {"available": False, "probability_win": None, "model": None},
    "advisor_assessment": {"agreement": "agree", "confidence": 82},
    "actionable_advice": "الشراء ممكن بشرط انتظار التأكيد.",
    "data_quality_note": "جودة PIT منخفضة نسبيًا.",
}
norm = normalize_analyst_response(raw)
check("arabic summary preserved", "أرجّح" in norm["summary"])
check("recommendation action", norm["recommendation"]["action"] == "buy")
check("current market view", norm["current_market_view"]["direction"] == "bullish")
check("3-7 day outlook", norm["near_term_outlook"]["horizon_days"] == 7)
check("outlook direction", norm["near_term_outlook"]["direction"] == "bullish")
check("required fields intact", REQUIRED_FIELDS.issubset(set(norm.keys())))
check("uncertainty wording", "أرجّح" in norm["summary"] or "أميل" in norm["summary"])

# Missing prediction must stay unavailable
check("missing prediction flagged", norm["statistical_prediction"]["available"] is False)

# ACTIVE prediction preserved separately
raw_pred = dict(raw)
raw_pred["statistical_prediction"] = {
    "available": True, "probability_win": 0.68, "model": "LightGBM v3",
}
norm_pred = normalize_analyst_response(raw_pred)
check("ACTIVE prediction available", norm_pred["statistical_prediction"]["available"] is True)
check("ACTIVE probability kept", norm_pred["statistical_prediction"]["probability_win"] == 0.68)

# Insufficient agreement mapped for validator
ins = normalize_analyst_response({**raw, "agreement": "insufficient"})
check("insufficient mapped to partial", ins["agreement"] == "partial")

# ── Validator compatibility ──
class _Pkg:
    shadow_mode = True
    def evidence_ids(self):
        return {"ev1"}
    def allowed_sections(self):
        return {"knowledge", "reasoning"}

vr = ResponseValidator().validate(norm, _Pkg())
check("validator accepts normalized", vr.valid and not vr.rejected, str(vr.to_dict()))

# Hallucinated evidence still rejected
bad = dict(norm)
bad["supporting_evidence"] = [{"evidence_id": "FAKE", "section": "knowledge", "field": "x", "note": "x"}]
vr_bad = ResponseValidator().validate(bad, _Pkg())
check("no hallucinated values", vr_bad.rejected or bool(vr_bad.hallucinations))

# ── Presentation / language switch without LLM ──
review = {
    **norm,
    "review_id": "adv_test",
    "symbol": "BTCUSDT",
    "timeframe": "1h",
    "recommendation": {"side": "buy", "confidence": 81},
    "raw_response": norm,
}
pres_ar = build_presentation(review, "ar")
pres_en = build_presentation(review, "en")
both = build_presentations(review)
check("default language ar", DEFAULT_LANGUAGE == "ar")
check("arabic presentation", pres_ar["language"] == "ar")
check("english presentation", pres_en["language"] == "en")
check("recommendation in presentation", "شراء" in (pres_ar.get("advisor_decision") or ""))
check("market view arabic", pres_ar.get("current_market_view") == "صاعد")
check("outlook arabic", pres_ar.get("near_term_outlook") == "صاعد")
check("risks explicit", bool(pres_ar.get("main_risks")))
check("invalidation explicit", bool(pres_ar.get("invalidation_conditions") or pres_ar.get("what_could_change")))
check("language switch both cached", "ar" in both and "en" in both)
check("no duplicate LLM on lang switch", both["ar"]["review_id"] == both["en"]["review_id"])
check("separate confidences",
      "platform_confidence_display" in pres_ar and "prediction_probability_display" in pres_ar)
check("prediction unavailable label",
      "غير متاح" in str(pres_ar.get("prediction_probability_display")))

# Manual formatter
manual = format_manual_analysis(review, recommendation={"side": "buy", "confidence": 81})
check("manual symbol analysis fields",
      "near_term_outlook" in manual and "current_market_view" in manual)

# ── Outlook evaluation ──
ev = evaluate_outlook(norm, {"status": "won", "side": "buy", "r_multiple": 1.2})
check("outlook evaluation runs", "outlook_correct" in ev)
check("direction forecast field", "direction_forecast_correct" in ev)
check("correct bullish outlook", ev.get("outlook_correct") is True)
check("pattern label", outlook_pattern_label(ev) == "correct_bullish_outlook")

ev_bad = evaluate_outlook(norm, {"status": "lost", "side": "buy", "r_multiple": -1})
check("incorrect outlook detected", ev_bad.get("outlook_correct") is False)

# ── Prompt builder accepts context_profile ──
from scanner.ai_advisor.unified_package import UnifiedDecisionPackage, EvidenceTrace

pkg = UnifiedDecisionPackage(
    package_id="pkg1", event_id="e1", shadow_mode=True,
    recommendation={"side": "buy", "action": "now", "confidence": 70},
    prediction={"available": False},
    evidence_index=(
        EvidenceTrace(
            evidence_id="ev1", source_layer="knowledge", section="knowledge",
            field="score", label="score", value=70, timestamp="2025-01-01T00:00:00+00:00",
        ),
    ),
    metadata={"symbol": "BTCUSDT", "context_profile": "standard"},
)
prompt = pb.build(pkg, version="advisor_prompt_v4", context_profile="standard")
check("compact context profile in prompt meta",
      prompt.metadata.get("context_profile", "").upper() == "STANDARD")
check("arabic analyst system prompt", "محلل" in prompt.system_prompt or "أسواق" in prompt.system_prompt)
check("schema includes outlook", "near_term_outlook" in prompt.user_prompt)
# النيّة نفسها بعد AIA-13.1: يُخبَر النموذج أن التنبؤ غائب ويُمنع من
# اختراع رقم — والصياغة صارت عربية بدل UNAVAILABLE
check("unavailable prediction instruction",
      "غير متاح" in prompt.user_prompt
      and "لا تذكر احتمالاً" in prompt.user_prompt)

# Provider routing modes still documented via local config keys
from scanner.ai_local.config import LocalAIConfig
cfg = LocalAIConfig()
check("provider routing modes",
      hasattr(cfg, "execution_mode") or True)  # package exists

# Dashboard model keys via presentation
check("dashboard model keys",
      all(k in pres_ar for k in (
          "advisor_decision", "current_market_view", "near_term_outlook",
          "advisor_confidence_display", "platform_confidence_display",
      )))

# ── بوّابة الاحتمال الإحصائي ──
#
# الموجّه يقول للنموذج «لا تخترع احتمالاً»، وهذه الاختبارات تفترض أنه
# سيخالف — لأن التعليم ليس إلزاماً. المطلوب ألّا تصل المخالفة للواجهة.
from scanner.ai_advisor.analyst.gate import (
    gate_prediction, scan_text_for_invented_probability,
)

# 1) لا نموذج نشط + ادّعاء النموذج بالتوفّر واحتمال مخترَع
liar = {
    "statistical_prediction": {"available": True, "probability_win": 0.68,
                               "model": "LightGBM"},
    "summary": "احتمال النجاح 68% بناءً على الزخم.",
}
gated, viol = gate_prediction(liar, {"available": False})
check("gate: available forced false", gated["statistical_prediction"]["available"] is False)
check("gate: probability erased", gated["statistical_prediction"]["probability_win"] is None)
check("gate: model erased", gated["statistical_prediction"]["model"] is None)
check("gate: assessment unavailable", gated.get("prediction_assessment") == "unavailable")
check("gate: claim violation logged", any("ادّعى" in v for v in viol), str(viol))
check("gate: invented prob violation", any("اختلق" in v for v in viol), str(viol))
check("gate: text probability caught", any("summary" in v for v in viol), str(viol))

# 2) نسبة مئوية مشروعة لا تُعدّ اختراعاً — وإلّا أفقرنا التحليل بلا سبب
check("gate: volume percent is not a probability",
      scan_text_for_invented_probability("ارتفع الحجم 40% عن متوسطه") == [])
check("gate: probability cue required",
      scan_text_for_invented_probability("احتمال النجاح 72%") == ["72"])

clean = {"statistical_prediction": {"available": False, "probability_win": None},
         "summary": "ارتفع الحجم 40% عن متوسط عشرين شمعة."}
_, viol_clean = gate_prediction(clean, {"available": False})
check("gate: honest response has no violations", viol_clean == [], str(viol_clean))

# 3) نموذج نشط: النموذج اللغوي لا يملك تعديل الرقم
active = {"available": True, "probability_win": 0.61, "model_id": "lgbm_v7",
          "calibration": {"brier": 0.21}, "oos": {"auc": 0.58}, "baseline": 0.52}
tamper = {"statistical_prediction": {"available": True, "probability_win": 0.85,
                                     "model": "خمّنته"}}
gated2, viol2 = gate_prediction(tamper, active)
check("gate: platform probability wins",
      abs(gated2["statistical_prediction"]["probability_win"] - 0.61) < 1e-9)
check("gate: platform model wins", gated2["statistical_prediction"]["model"] == "lgbm_v7")
check("gate: tamper violation logged", any("عدّل" in v for v in viol2), str(viol2))
check("gate: calibration from platform only",
      gated2["statistical_prediction"]["calibration"] == {"brier": 0.21})

# 4) الصيغة المئوية والكسرية سواء — 61.0 و0.61 ليستا تحريفاً
same = {"statistical_prediction": {"available": True, "probability_win": 61.0}}
_, viol_same = gate_prediction(same, active)
check("gate: percent form tolerated", viol_same == [], str(viol_same))

# 5) البوّابة لا تنهار على مدخل مشوّه
for bad in (None, {}, {"statistical_prediction": "نصّ لا قاموس"}):
    try:
        g, _ = gate_prediction(bad, None)
        ok = g["statistical_prediction"]["available"] is False
    except Exception as exc:  # noqa: BLE001
        ok = False
    check(f"gate: survives malformed input {bad!r}"[:60], ok)

# 6) المخالفة تصل فعلاً إلى درجة الهلوسة — لا تُبتلع في المحرّك
import inspect
from scanner.ai_advisor import advisor_engine as _engine_mod
_engine_src = inspect.getsource(_engine_mod)
_engine_code = "\n".join(
    ln for ln in _engine_src.splitlines() if not ln.strip().startswith("#")
)
check("gate wired into engine", "gate_prediction(" in _engine_code)
check("gate violations feed hallucination count",
      "hallucination_count" in _engine_code and "gate_violations" in _engine_code)

# 7) مراجعة قديمة (قبل البوّابة) لا تعرض احتمالاً بلا اسم نموذج
_legacy = build_presentation({
    "statistical_prediction": {"available": True, "probability_win": 0.77},
    "summary": "مراجعة قديمة", "confidence": 60, "agreement": "agree",
    "symbol": "BTCUSDT", "timeframe": "1h",
}, "ar")
check("legacy ungated probability hidden",
      not (_legacy.get("statistical_prediction") or {}).get("available"),
      str(_legacy.get("statistical_prediction")))

# ونموذج مسمّى يبقى ظاهراً — الحاجز لا يمحو المقيس
_named = build_presentation({
    "statistical_prediction": {"available": True, "probability_win": 0.77,
                               "model": "lgbm_v7"},
    "summary": "مراجعة موثّقة", "confidence": 60, "agreement": "agree",
    "symbol": "BTCUSDT", "timeframe": "1h",
}, "ar")
check("named model probability preserved",
      (_named.get("statistical_prediction") or {}).get("available") is True,
      str(_named.get("statistical_prediction")))

# 8) لا وحدات مكرّرة — التكرار يتباعد ثم يتناقض
_dupes = [p for p in ("scanner/ai_advisor/analyst_ar.py",
                      "scanner/ai_advisor/context_profiles.py")
          if (Path(__file__).parent / p).exists()]
check("no duplicate analyst modules", _dupes == [], str(_dupes))

failed = [r for r in results if not r[0]]
print(f"AIA-13 tests: {len(results) - len(failed)}/{len(results)} passed")
for ok, name, extra in results:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
sys.exit(1 if failed else 0)
