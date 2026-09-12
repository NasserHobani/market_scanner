# -*- coding: utf-8 -*-
"""AIA-06.1 — Arabic explainability presentation tests."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.explainability.localized_presentation import (
    DEFAULT_LANGUAGE,
    agreement_label,
    build_presentation,
    build_presentations,
    localize_phrase,
    verdict_label,
)

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool) -> None:
    results.append((cond, name))


def sample_review(**overrides) -> dict:
    base = {
        "review_id": "adv_rt_001",
        "symbol": "VETUSDT",
        "timeframe": "15m",
        "agreement": "agree",
        "confidence": 82,
        "summary": "The platform's none action decision is well-supported by pervasive data gaps.",
        "reasoning": "Similarity win rate is 0%. Prediction unavailable.",
        "recommendation": {"side": "none", "action": "none"},
        "supporting_evidence": [
            {"evidence_id": "ev_013", "note": "data gaps in research layer", "href": "/x"},
            {"evidence_id": "ev_018", "note": "similarity win rate 0%", "href": "/y"},
        ],
        "contradicting_evidence": [
            {"evidence_id": "ev_021", "note": "bullish trend signal without confluence", "href": "/z"},
        ],
        "risks": ["Entering on direction alone without layer confirmation"],
        "missing_information": ["Prediction unavailable", "Optimization unavailable"],
        "review_type": "automatic",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "package_diagnostics": {"package_version": "udp-1", "evidence_count": 12},
    }
    base.update(overrides)
    return base


def test_arabic_rendering():
    p = build_presentation(sample_review(), "ar")
    check("arabic default language field", p["language"] == "ar")
    check("arabic title", "Claude" in p["title"] or "تحليل" in p["title"])
    check("arabic summary not raw english", "pervasive data gaps" not in p["executive_summary"])
    check("arabic has symbol", p["symbol"] == "VETUSDT")


def test_english_rendering():
    p = build_presentation(sample_review(), "en")
    check("english language field", p["language"] == "en")
    check("english agreement", p["agreement_label"] == "Agrees with platform")
    check("english summary uses raw", "well-supported" in p["executive_summary"].lower()
          or "data" in p["executive_summary"].lower())


def test_agreement_labels():
    check("agree ar", agreement_label("agree", "ar") == "متفق مع النظام")
    check("disagree ar", agreement_label("disagree", "ar") == "مختلف مع النظام")
    check("partial ar", agreement_label("partial", "ar") == "متفق جزئيًا")
    check("unknown ar", agreement_label("unknown", "ar") == "غير محدد")


def test_recommendation_labels():
    check("none ar", verdict_label("none", "ar") == "انتظار / عدم تداول")
    check("buy ar", verdict_label("buy", "ar") == "شراء")
    check("sell ar", verdict_label("sell", "ar") == "بيع")
    check("watch ar", verdict_label("watch", "ar") == "مراقبة")


def test_confidence_preservation():
    p = build_presentation(sample_review(confidence=82), "ar")
    check("confidence value", p["confidence"] == 82)
    check("confidence display", p["confidence_display"] == "82%")
    p2 = build_presentation(sample_review(confidence=None), "ar")
    check("missing confidence", p2["confidence_display"] == "غير متاح")


def test_evidence_id_preservation():
    p = build_presentation(sample_review(), "ar")
    ids = [s.get("evidence_id") for s in p["positive_signals"]]
    check("ev_013 preserved", "ev_013" in ids)
    check("no translated id", "معرف" not in str(p["positive_signals"]))


def test_no_hallucinated_evidence():
    p = build_presentation(sample_review(), "ar")
    all_ids = []
    for block in (p["positive_signals"], p["negative_signals"]):
        for s in block:
            if s.get("evidence_id"):
                all_ids.append(s["evidence_id"])
    check("only known ids", set(all_ids).issubset({"ev_013", "ev_018", "ev_021"}))


def test_empty_section_removal():
    r = sample_review(supporting_evidence=[], contradicting_evidence=[], risks=[], missing_information=[])
    p = build_presentation(r, "ar")
    check("no positive", "positive_signals" not in p["sections"] or not p["positive_signals"])
    check("no missing", "missing_information" not in p["sections"] or not p["missing_information"])
    check("always verdict", "final_verdict" in p["sections"])


def test_technical_evidence_visibility():
    p = build_presentation(sample_review(), "ar")
    tech = p["technical"]
    check("technical title ar", "أدلة" in tech["title"] or tech["title"] == "الأدلة التقنية")
    check("reasoning kept", "Similarity" in tech["reasoning"] or "Prediction" in tech["reasoning"])
    check("provider kept", tech["provider"] == "claude")


def test_manual_analysis():
    r = sample_review(review_type="manual")
    p = build_presentation(r, "ar")
    check("manual title", "يدوي" in p["title"] or p["title"] == "التحليل اليدوي")


def test_language_switching():
    both = build_presentations(sample_review())
    check("both langs", "ar" in both and "en" in both)
    check("same review id", both["ar"]["review_id"] == both["en"]["review_id"])


def test_no_duplicate_api_contract():
    """Presentations are derived locally — no extra fields on canonical review."""
    r = sample_review()
    canonical = copy.deepcopy(r)
    _ = build_presentations(r)
    check("canonical unchanged", r == canonical)


def test_cache_compatibility():
    from scanner.ai_advisor.explainability.manual_analysis_service import ManualAnalysisService
    svc = ManualAnalysisService()
    payload = {"ok": True, "report": sample_review()}
    out = svc._ensure_presentations(payload)  # noqa: SLF001
    check("presentations attached", "presentations" in out)
    check("ar in presentations", "ar" in out["presentations"])


def test_old_review_compatibility():
    old = {
        "review_id": "old_1",
        "agreement": "agree",
        "confidence": 70,
        "summary": "Legacy summary",
        "recommendation": {"side": "buy"},
        "symbol": "BTCUSDT",
        "timeframe": "4h",
    }
    p = build_presentation(old, "ar")
    check("old review renders", bool(p["executive_summary"]))
    check("old review verdict", "شراء" in p["final_verdict"])


def test_rtl_layout_fields():
    p = build_presentation(sample_review(), "ar")
    check("arabic lang code", p["language"] == "ar")


def test_long_arabic_text():
    long_risk = "مخاطرة " * 40
    p = build_presentation(sample_review(risks=[long_risk]), "ar")
    check("long risk kept", len(p["main_risks"][0]) > 100)


def test_mixed_technical_terms():
    r = sample_review(missing_information=["Prediction unavailable", "Optimization unavailable"])
    p = build_presentation(r, "ar")
    joined = " ".join(p["missing_information"])
    check("prediction term", "Prediction" in joined)
    check("optimization term", "Optimization" in joined)


def test_disagreement_rendering():
    r = sample_review(agreement="disagree", recommendation={"side": "buy", "action": "buy"})
    p = build_presentation(r, "ar")
    check("disagreement block", p["disagreement"] is not None)
    check("disagreement in sections", "disagreement" in p["sections"])


def test_partial_agreement_rendering():
    r = sample_review(agreement="partial")
    p = build_presentation(r, "ar")
    check("partial block", p["partial"] is not None)
    check("partial title", "جزئي" in p["partial"]["title"])


def test_missing_data_rendering():
    r = sample_review(confidence=None, supporting_evidence=[], risks=[])
    p = build_presentation(r, "ar")
    check("missing conf label", p["confidence_display"] == "غير متاح")
    check("still has summary", bool(p["executive_summary"]))


def test_localize_phrase():
    out = localize_phrase("no actionable edge in this setup", "ar")
    check("friendly arabic", "أفضلية تداول" in out)
    check("english unchanged", localize_phrase("no actionable edge", "en") == "no actionable edge")


def test_default_language():
    check("default ar", DEFAULT_LANGUAGE == "ar")


def main() -> int:
    test_arabic_rendering()
    test_english_rendering()
    test_agreement_labels()
    test_recommendation_labels()
    test_confidence_preservation()
    test_evidence_id_preservation()
    test_no_hallucinated_evidence()
    test_empty_section_removal()
    test_technical_evidence_visibility()
    test_manual_analysis()
    test_language_switching()
    test_no_duplicate_api_contract()
    test_cache_compatibility()
    test_old_review_compatibility()
    test_rtl_layout_fields()
    test_long_arabic_text()
    test_mixed_technical_terms()
    test_disagreement_rendering()
    test_partial_agreement_rendering()
    test_missing_data_rendering()
    test_localize_phrase()
    test_default_language()

    passed = sum(1 for ok, _ in results if ok)
    failed = [name for ok, name in results if not ok]
    print(f"\nAIA-06.1 Arabic Explainability: {passed}/{len(results)} passed")
    for ok, name in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print("\nFailed:", ", ".join(failed))
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
