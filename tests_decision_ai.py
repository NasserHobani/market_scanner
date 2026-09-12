# -*- coding: utf-8 -*-
"""Unit tests for scanner.decision_ai — run: python tests_decision_ai.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.decision_ai import (
    ConfidenceFusion,
    ContextBuilder,
    DecisionAIService,
    EvidenceBuilder,
    FUSION_WEIGHTS,
    Guardrails,
    PromptBuilder,
    PromptType,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


# ── Sample layer outputs ─────────────────────────────────────────────────────

KNOWLEDGE = {
    "event_id": "evt_001",
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
    "recommendation_confidence": 0.75,
    "action": "now",
    "direction": "buy",
    "evidence": {
        "items": [
            {"evidence_id": "ev_trend", "label": "Bullish trend", "category": "trend",
             "direction": "supports", "confidence": 0.8, "source": "market_snapshot.trend",
             "facts": ["trend=bullish"], "trace": "market.trend_direction"},
            {"evidence_id": "ev_liquidity", "label": "Liquidity sweep", "category": "liquidity",
             "direction": "supports", "confidence": 0.7, "source": "feature.groups.liquidity",
             "facts": ["sweeps=1"], "trace": "feature.liquidity"},
        ],
    },
    "contradictions": {"items": []},
    "confidence": {"overall": 0.78, "categories": {"trend": 0.8}},
    "warnings": [],
    "missing_information": [],
}

SIMILARITY = {
    "available": True,
    "match_count": 8,
    "average_win_rate": 62.5,
    "average_r": 1.2,
    "historical_evidence": ["historical_match_count=8"],
    "historical_warnings": [],
}

PREDICTION = {
    "prediction": 1.0,
    "probability": 0.72,
    "confidence": 0.72,
    "model_id": "mdl_test",
    "model_version": "1.0.0",
    "feature_version": "1.0.0",
    "plugin": "lightgbm",
    "explainability": {"feature_columns": ["rsi", "score"], "feature_values": {"rsi": 55.0}},
    "timestamp": "2025-06-01T12:00:00+00:00",
}

RESEARCH = {
    "conclusions": ["HTF filter improves expectancy"],
    "warnings": ["Low sample size (n=15)"],
    "limitations": ["Historical performance does not guarantee future results"],
    "dataset_summary": {"closed_count": 15, "count": 15},
    "comparison": {"winner": "with_htf"},
    "methodology": {"version": "1.0.0", "hypothesis": {"filter_type": "factor", "filter_key": "htf"}},
    "metrics": {"treatment": {"expectancy": 0.9}},
}

FEATURE_INTEL = {
    "analysis_id": "fia_test",
    "version": "1.0.0",
    "ranking": [{"feature": "rsi", "composite_score": 0.75, "rank": 1}],
    "report": {"summary": {"top_feature": "rsi", "feature_count": 5}},
    "drift": [{"feature": "rsi", "drift_score": 0.2}],
}

# ── Context Builder ──────────────────────────────────────────────────────────

ctx = ContextBuilder().build(
    event_id="evt_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
    similarity_context=SIMILARITY,
    prediction=PREDICTION,
    research_report=RESEARCH,
    feature_analysis=FEATURE_INTEL,
)
check("Context event_id", ctx.event_id == "evt_001")
check("Context symbol", ctx.symbol == "BTCUSDT")
check("Context immutable", ctx.market == "crypto")
check("Context has knowledge", bool(ctx.knowledge))
check("Context has reasoning", ctx.reasoning.get("verdict") == "aligned")
check("Context has similarity", ctx.similarity.get("match_count") == 8)
check("Context has prediction", ctx.prediction.get("model_id") == "mdl_test")
check("Context to_dict", "built_at" in ctx.to_dict())

# ── Evidence Builder ─────────────────────────────────────────────────────────

ctx_dict = ctx.to_dict()
evidence = EvidenceBuilder().build(ctx_dict)
check("Evidence items", len(evidence.items) >= 3, str(len(evidence.items)))
check("Evidence sources present", "reasoning" in evidence.sources_present)
check("Evidence has source field", evidence.items[0].source == "reasoning")
check("Evidence has confidence", evidence.items[0].confidence > 0)
check("Evidence has timestamp", bool(evidence.items[0].timestamp))
check("Evidence has version", bool(evidence.items[0].version))
check("Evidence similarity", any(i.source == "similarity" for i in evidence.items))
check("Evidence prediction", any(i.source == "prediction" for i in evidence.items))
check("Evidence to_dict", evidence.to_dict()["item_count"] >= 3)

# ── Confidence Fusion ────────────────────────────────────────────────────────

fused = ConfidenceFusion().fuse(ctx_dict)
check("Fusion overall", fused.overall > 0, str(fused.overall))
check("Fusion components", "reasoning" in fused.components)
check("Fusion weights exposed", fused.weights == FUSION_WEIGHTS)
check("Fusion sources available", len(fused.sources_available) >= 3)
check("Fusion to_dict", "overall_pct" in fused.to_dict())

# ── Guardrails ───────────────────────────────────────────────────────────────

ev_dict = evidence.to_dict()
guard = Guardrails().validate(ctx_dict, evidence=ev_dict)
check("Guardrails passed", guard.passed)
check("Guardrails research sample warning",
      any(v.rule == "research_sample_small" for v in guard.violations))
check("Guardrails to_dict", "violation_count" in guard.to_dict())

# Missing prediction guardrail test
ctx_no_pred = ContextBuilder().build(
    event_id="evt_002", knowledge_context=KNOWLEDGE, reasoning_review=REASONING,
).to_dict()
ev_no_pred = EvidenceBuilder().build(ctx_no_pred).to_dict()
guard_missing = Guardrails().validate(ctx_no_pred, evidence=ev_no_pred)
check("Guardrails missing evidence", len(guard_missing.missing_evidence) > 0)

# ── Prompt Builder ───────────────────────────────────────────────────────────

prompt = PromptBuilder().build(PromptType.TRADE_REVIEW.value, ctx_dict,
                                evidence=ev_dict, guardrails=guard.to_dict())
check("Prompt type", prompt.prompt_type == "trade_review")
check("Prompt has content", len(prompt.content) > 100)
check("Prompt llm_ready false", prompt.to_dict()["llm_ready"] is False)
check("Prompt sections", len(prompt.sections) > 5)

for pt in PromptType:
    p = PromptBuilder().build(pt.value, ctx_dict, evidence=ev_dict)
    check(f"Prompt template {pt.value}", len(p.content) > 50)

check("Prompt available types", len(PromptBuilder().available_types()) == 5)

# ── DecisionAIService ────────────────────────────────────────────────────────

svc = DecisionAIService()

svc_ctx = svc.build_context(
    event_id="evt_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
    similarity_context=SIMILARITY,
    prediction=PREDICTION,
    research_report=RESEARCH,
    feature_analysis=FEATURE_INTEL,
)
check("Service build_context", svc_ctx.event_id == "evt_001")

summary = svc.decision_summary(svc_ctx)
check("Service decision_summary", summary.summary_id.startswith("dsum_"))
check("Summary strengths", len(summary.strengths) > 0)
check("Summary prediction", summary.prediction.get("available") is True)
check("Summary historical", summary.historical_support.get("available") is True)
check("Summary research", summary.research_support.get("available") is True)
check("Summary confidence", summary.overall_confidence > 0)
check("Summary disclaimer", "disclaimer" in summary.to_dict())
check("Summary JSON only", isinstance(summary.to_dict(), dict))

svc_prompt = svc.build_prompt("trade_review", svc_ctx)
check("Service build_prompt", svc_prompt.prompt_type == "trade_review")

trade_review = svc.review_trade(
    event_id="evt_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
    similarity_context=SIMILARITY,
    prediction=PREDICTION,
    research_report=RESEARCH,
    feature_analysis=FEATURE_INTEL,
)
check("Service review_trade", trade_review.review_id.startswith("airev_"))
check("Review type", trade_review.review_type == "trade_review")
check("Review has evidence", trade_review.evidence.get("item_count", 0) >= 3
      or len(trade_review.evidence.get("items", [])) >= 3)
check("Review has summary", bool(trade_review.summary))
check("Review has confidence", bool(trade_review.confidence))
check("Review has guardrails", bool(trade_review.guardrails))
check("Review llm not invoked", trade_review.to_dict()["llm_invoked"] is False)
check("Review disclaimer", "not a trading recommendation" in trade_review.to_dict()["disclaimer"])

market_review = svc.review_market(event_id="evt_001", knowledge_context=KNOWLEDGE)
check("Service review_market", market_review.review_type == "market_review")

risk_review = svc.review_risk(svc_ctx)
check("Service review_risk", risk_review.review_type == "risk_review")

research_review = svc.review_research(svc_ctx)
check("Service review_research", research_review.review_type == "research_review")

pred_review = svc.review_prediction(svc_ctx)
check("Service review_prediction", pred_review.review_type == "prediction_review")

weights = svc.fusion_weights()
check("Service fusion_weights", weights == FUSION_WEIGHTS)

# ── High drift guardrail ─────────────────────────────────────────────────────

fi_drift = {**FEATURE_INTEL, "drift": [{"feature": "rsi", "drift_score": 0.8}]}
ctx_drift = svc.build_context(
    event_id="evt_003", knowledge_context=KNOWLEDGE,
    feature_analysis=fi_drift,
).to_dict()
guard_drift = Guardrails().validate(ctx_drift)
check("Guardrails feature drift",
      any(v.rule == "feature_drift_high" for v in guard_drift.violations))

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Decision AI Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
