# -*- coding: utf-8 -*-
"""Unit tests for scanner.ai_advisor — run: python tests_ai_advisor.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor import (
    AIAdvisorService,
    AdvisorEngine,
    AdvisorScore,
    DecisionPackageBuilder,
    PromptBuilder,
    ProviderRegistry,
    ResponseParser,
    ResponseParseError,
    ResponseValidator,
)
from scanner.ai_advisor.providers import MockProvider

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


# ── Fixtures (same layer outputs as tests_decision_ai.py) ────────────────────

KNOWLEDGE = {
    "event_id": "evt_aia_001",
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "market_snapshot": {"symbol": "BTCUSDT", "trend_direction": "bullish", "atr_pct": 2.1},
    "market_environment": {"regime": "uptrend", "breadth_pct": 62.0},
    "feature_snapshot": {"final_grade": "A", "final_score": 72.0},
    "recommendation_snapshot": {"action": "now", "side": "buy", "confidence": 0.75, "grade": "A"},
    "strategy_statistics": {"closed_trades": 50, "win_rate": 65.0, "expectancy": 0.8, "reliable": True},
}

REASONING = {
    "verdict": "aligned",
    "agreement_score": 0.82,
    "engine_confidence": 0.78,
    "action": "now",
    "direction": "buy",
    "evidence": {
        "items": [
            {"evidence_id": "ev_trend", "label": "Bullish trend", "category": "trend",
             "direction": "supports", "confidence": 0.8, "source": "market_snapshot.trend",
             "facts": ["trend=bullish"], "trace": "market.trend_direction"},
        ],
    },
    "contradictions": {"items": []},
    "warnings": [],
    "missing_information": ["out_of_sample_validation"],
}

SIMILARITY = {
    "available": True, "match_count": 8,
    "average_win_rate": 62.5, "average_r": 1.2,
}

PREDICTION = {
    "probability": 0.72, "confidence": 0.72,
    "model_id": "mdl_test", "model_version": "1.0.0",
}

VALID_RESPONSE = {
    "agreement": "agree",
    "confidence": 78,
    "summary": "Evidence layers align with platform decision.",
    "reasoning": "Trend and similarity support the buy setup per ev_trend.",
    "supporting_evidence": [
        {"evidence_id": "ev_trend", "section": "reasoning",
         "field": "market_snapshot.trend", "note": "Bullish trend supports buy"},
    ],
    "contradicting_evidence": [],
    "risks": ["Sample size may be insufficient for 4h timeframe"],
    "missing_information": ["out_of_sample_validation"],
    "suggested_experiment": {
        "hypothesis": "Edge persists on walk-forward",
        "method": "90-day out-of-sample test",
        "expected_outcome": "Expectancy above 0.3R",
    },
    "shadow_mode_acknowledged": True,
}

HALLUCINATED_RESPONSE = {
    **VALID_RESPONSE,
    "supporting_evidence": [
        {"evidence_id": "ev_FAKE_999", "section": "phantom",
         "field": "invented", "note": "Made up indicator"},
    ],
}


# ── Decision Package ─────────────────────────────────────────────────────────

builder = DecisionPackageBuilder()
pkg = builder.build(
    event_id="evt_aia_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
    similarity_context=SIMILARITY,
    prediction=PREDICTION,
)

check("Package has ID", bool(pkg.package_id))
check("Package event_id", pkg.event_id == "evt_aia_001")
check("Package shadow_mode", pkg.shadow_mode is True)
check("Package has trade section", pkg.trade.get("symbol") == "BTCUSDT")
check("Package has evidence index", len(pkg.evidence_index) > 0)
check("Package no OHLC", "ohlc" not in json.dumps(pkg.to_dict()).lower())
check("Package decision not overridable", pkg.decision.get("advisor_may_override") is False)

# Forbidden keys stripped
dirty = {**KNOWLEDGE, "ohlc": [{"open": 1}], "candles": [1, 2, 3]}
clean_pkg = builder.build(event_id="evt_dirty", knowledge_context=dirty)
check("OHLC stripped", "ohlc" not in json.dumps(clean_pkg.to_dict()).lower())

# ── Prompt Builder ───────────────────────────────────────────────────────────

pb = PromptBuilder()
check("Prompt versions exist", len(pb.list_versions()) >= 3)
check("v1 template", "advisor_prompt_v1" in pb.list_versions())
check("v4 arabic analyst template", "advisor_prompt_v4" in pb.list_versions())

prompt = pb.build(pkg, version="advisor_prompt_v1")
check("Prompt has system", bool(prompt.system_prompt))
check("Prompt has user", bool(prompt.user_prompt))
# ‏AIA-13.1: المعرّف الداخلي لم يعد يُرسَل للنموذج (لا يبني عليه حكماً
# ويستهلك رموزاً) — لكنه يبقى على الكائن للتتبّع والربط بالحزمة
check("Prompt carries package id for tracing", prompt.package_id == pkg.package_id)
check("Internal package id not sent to model", pkg.package_id not in prompt.user_prompt)
check("Prompt has rules", len(prompt.rules) > 0)
check("Prompt version", prompt.version == "advisor_prompt_v1")

# ── Provider Abstraction ─────────────────────────────────────────────────────

registry = ProviderRegistry()
registry.register_defaults()
check("Default providers registered", len(registry.list_all()) >= 6)
check("Claude provider exists", "claude" in [p["provider_id"] for p in registry.list_all()])

mock = MockProvider(response=VALID_RESPONSE)
registry.register(mock)
check("Mock provider health", mock.health()["healthy"] is True)
check("Mock model name", mock.model_name() == "mock-v1")

# ── Response Parser ──────────────────────────────────────────────────────────

parser = ResponseParser()
check("Parse dict", parser.parse(VALID_RESPONSE)["agreement"] == "agree")

fenced = '```json\n' + json.dumps(VALID_RESPONSE) + '\n```'
check("Parse fenced JSON", parser.parse(fenced)["confidence"] == 78)

try:
    parser.parse("not json at all")
    check("Parse invalid raises", False)
except ResponseParseError:
    check("Parse invalid raises", True)

# ── Response Validator ───────────────────────────────────────────────────────

validator = ResponseValidator()
valid_result = validator.validate(VALID_RESPONSE, pkg)
check("Valid response passes", valid_result.valid)
check("Valid not rejected", not valid_result.rejected)

hallucinated_result = validator.validate(HALLUCINATED_RESPONSE, pkg)
check("Hallucinated evidence rejected", hallucinated_result.rejected)
check("Hallucination detected", len(hallucinated_result.hallucinations) > 0)

no_shadow = {**VALID_RESPONSE, "shadow_mode_acknowledged": False}
no_shadow_result = validator.validate(no_shadow, pkg)
check("Missing shadow_mode rejected", no_shadow_result.rejected)

override_response = {**VALID_RESPONSE, "action_override": "sell"}
override_result = validator.validate(override_response, pkg)
check("Override field rejected", override_result.rejected)

# ── Advisor Engine (full pipeline) ──────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    mem_path = Path(tmpdir) / "test_memory.jsonl"
    from scanner.ai_advisor.memory import AdvisorMemory
    from scanner.ai_advisor.advisor_engine import AdvisorEngine

    mem = AdvisorMemory(path=mem_path)
    reg = ProviderRegistry()
    reg.register(MockProvider(response=VALID_RESPONSE))

    engine = AdvisorEngine(registry=reg, memory=mem)
    review = engine.review(pkg, provider_id="mock")

    check("Review has ID", bool(review.review_id))
    check("Review agreement", review.agreement == "agree")
    check("Review accepted", review.accepted is True)
    check("Review shadow_mode", review.shadow_mode is True)
    check("Review saved to memory", mem.count() == 1)

    # Multi-model dispatch
    reg.register(MockProvider(response={**VALID_RESPONSE, "agreement": "disagree"}))
    reg._providers["mock2"] = MockProvider(response={**VALID_RESPONSE, "agreement": "disagree"})
    reg._providers["mock2"]._id = "mock2"

    multi = engine.review_multi(pkg, provider_ids=["mock", "mock2"])
    check("Multi-model returns list", len(multi) == 2)

# ── Advisor Service ──────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    mem_path = Path(tmpdir) / "svc_memory.jsonl"
    from scanner.ai_advisor.memory import AdvisorMemory

    mem = AdvisorMemory(path=mem_path)
    reg = ProviderRegistry()
    reg.register(MockProvider(response=VALID_RESPONSE))
    svc = AIAdvisorService(
        engine=AdvisorEngine(registry=reg, memory=mem),
        registry=reg, memory=mem,
    )

    review = svc.review_trade(
        "evt_svc_001",
        knowledge_context=KNOWLEDGE,
        reasoning_review=REASONING,
        similarity_context=SIMILARITY,
        prediction=PREDICTION,
        provider_id="mock",
    )
    check("Service review_trade", review.accepted is True)

    ui = svc.to_ui_summary()
    check("UI summary available", ui["available"] is True)
    check("UI shadow_mode", ui["shadow_mode"] is True)
    check("UI has providers", ui["providers"]["total"] >= 1)

    providers = svc.list_providers()
    check("List providers", len(providers) >= 1)

    score = svc.advisor_score()
    check("Advisor score computed", "advisor_score" in score)
    check("Advisor grade", score.get("grade") in ("A", "B", "C", "D", "F"))

    history = svc.history(10)
    check("History returns records", len(history) >= 1)

    ui_model = review.to_ui_model()
    check("UI model has agreement", "agreement" in ui_model)
    check("UI model has evidence", "evidence" in ui_model)
    check("UI model no raw JSON key", "raw_response" not in ui_model)

# ── Grounding validation detail ──────────────────────────────────────────────

grounded = {
    **VALID_RESPONSE,
    "supporting_evidence": [
        {"evidence_id": pkg.evidence_index[0].evidence_id,
         "section": pkg.evidence_index[0].section,
         "field": pkg.evidence_index[0].field,
         "note": "Grounded reference"},
    ],
}
grounded_result = validator.validate(grounded, pkg)
check("Grounded evidence passes", grounded_result.valid)
check("No hallucinations in grounded", len(grounded_result.hallucinations) == 0)

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"AI Advisor Tests: {passed} passed, {failed} failed")
for ok, name, extra in results:
    tag = "PASS" if ok else "FAIL"
    line = f"  [{tag}] {name}"
    if extra:
        line += f" — {extra}"
    print(line)
if failed:
    sys.exit(1)
