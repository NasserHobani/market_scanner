# -*- coding: utf-8 -*-
"""Production verification — run: python scripts/verify_ai_production.py"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()

from scanner.ai_advisor.provider_config import load_config, effective_provider_id
from scanner.ai_advisor.runtime import is_advisor_enabled as runtime_enabled
from scanner.ai_advisor import AIAdvisorService

KNOWLEDGE_FIXTURE = {
    "event_id": "evt_prod_verify",
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "market_snapshot": {"symbol": "BTCUSDT", "trend_direction": "bullish", "atr_pct": 2.1},
    "market_environment": {"regime": "uptrend", "breadth_pct": 62.0},
    "feature_snapshot": {"final_grade": "A", "final_score": 72.0},
    "recommendation_snapshot": {"action": "now", "side": "buy", "confidence": 0.75, "grade": "A"},
    "strategy_statistics": {"closed_trades": 50, "win_rate": 65.0, "expectancy": 0.8, "reliable": True},
}
REASONING_FIXTURE = {
    "verdict": "aligned",
    "agreement_score": 0.82,
    "engine_confidence": 0.78,
    "action": "now",
    "direction": "buy",
    "evidence": {
        "items": [
            {"evidence_id": "ev_trend", "label": "Bullish trend", "direction": "supports",
             "confidence": 0.8, "source": "market_snapshot.trend", "facts": ["trend=bullish"]},
        ],
    },
    "contradictions": {"items": []},
    "warnings": [],
    "missing_information": [],
}
GUARDRAILS = {"passed": True, "violations": []}
FUSED = {"overall": 0.76, "components": {"reasoning": 0.78}}


def main() -> int:
    cfg = load_config()
    pid = effective_provider_id(cfg)
    print("=== CONFIG ===")
    print(f"effective_provider: {pid}")
    print(f"claude_enabled: {cfg.claude_enabled}")
    print(f"api_key_configured: {cfg.api_key_configured}")
    print(f"is_advisor_enabled: {runtime_enabled()}")

    if not cfg.api_key_configured:
        print("\nFAIL: ANTHROPIC_API_KEY not set — cannot verify Claude call")
        return 1

    if not runtime_enabled():
        print("\nFAIL: advisor runtime disabled")
        return 1

    from scanner.ai_advisor import AIAdvisorService

    svc = AIAdvisorService()
    review = svc.review_trade(
        "evt_prod_verify",
        provider_id=pid,
        metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h", "trade_id": "verify_001"},
        recommendation={"action": "now", "side": "buy", "confidence": 0.75, "grade": "A"},
        knowledge_context=KNOWLEDGE_FIXTURE,
        reasoning_review=REASONING_FIXTURE,
        similarity_context={"available": True, "match_count": 5, "average_win_rate": 60.0, "average_r": 1.1},
        prediction={"probability": 0.72, "confidence": 0.72, "model_id": "mdl_test", "model_version": "1.0"},
        guardrails=GUARDRAILS,
        fused_confidence=FUSED,
        decision_ai={"verdict": "aligned"},
    )

    metrics = svc._engine.last_call_metrics
    print("\n=== REVIEW ===")
    print(f"accepted: {review.accepted}")
    print(f"provider: {review.provider_id}")
    print(f"review_id: {review.review_id}")
    print(f"tokens: {metrics.get('total_tokens')}")
    print(f"cost: ${metrics.get('estimated_cost')}")

    mem_path = ROOT / "data" / "advisor_memory.jsonl"
    hist_path = ROOT / "data" / "advisor_history.jsonl"
    state_path = ROOT / "data" / "advisor_runtime_state.json"

    print("\n=== FILES ===")
    print(f"memory exists: {mem_path.exists()}")
    print(f"history exists: {hist_path.exists()}")
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"runtime status: {state.get('status')}")
        print(f"successful_reviews: {state.get('successful_reviews')}")

    if review.provider_id != "claude":
        print("\nFAIL: provider is not claude")
        return 1
    if not review.accepted:
        print("\nFAIL: review rejected")
        return 1
    if int(metrics.get("total_tokens") or 0) <= 0:
        print("\nFAIL: zero tokens")
        return 1
    if not mem_path.exists():
        print("\nFAIL: advisor_memory.jsonl missing")
        return 1

    # Runtime path — updates dashboard state
    from scanner.ai_advisor.runtime import review_recommendation
    rt = review_recommendation(
        symbol="BTCUSDT", market="crypto", timeframe="4h",
        recommendation={"action": "now", "side": "buy", "confidence": 0.75, "grade": "A"},
        row={"decision": "aligned", "htf": 1, "atr_pct": 2.1},
        trade_id="verify_rt_001",
    )
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        print(f"\nruntime after scan hook: status={state.get('status')} reviews={state.get('successful_reviews')}")

    claude_hist = [
        json.loads(l) for l in hist_path.read_text(encoding="utf-8").strip().splitlines()
        if l.strip() and json.loads(l).get("provider") == "claude"
    ]
    if not claude_hist:
        print("\nFAIL: no claude entries in history")
        return 1

    eval_path = ROOT / "data" / "advisor_evaluations.jsonl"
    lessons_path = ROOT / "data" / "learning_lessons.jsonl"
    print(f"evaluations exists: {eval_path.exists()}")
    print(f"learning lessons exists: {lessons_path.exists()}")

    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("status") != "running":
            print(f"\nFAIL: runtime status is {state.get('status')}, expected running")
            return 1
        if int(state.get("successful_reviews") or 0) < 1:
            print("\nFAIL: successful_reviews < 1")
            return 1

    print("\nPASS: Production verification succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
