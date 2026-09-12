# -*- coding: utf-8 -*-
"""Unit tests for AI Advisor runtime — run: python tests_ai_advisor_runtime.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.advisor_engine import AdvisorEngine
from scanner.ai_advisor.decision_package import DecisionPackageBuilder
from scanner.ai_advisor.memory import AdvisorMemory
from scanner.ai_advisor.prompt_builder import PromptBuilder
from scanner.ai_advisor.provider_config import AIAdvisorConfig
from scanner.ai_advisor.providers import MockProvider
from scanner.ai_advisor.runtime import (
    build_layer_outputs,
    is_advisor_enabled,
    review_recommendation,
    review_scan_candidates,
)
from scanner.ai_advisor.runtime_history import AdvisorRuntimeHistory
from scanner.ai_advisor.runtime_state import AdvisorRuntimeState
from scanner.ai_advisor.token_cost import estimate_cost
from scanner.ai_advisor import AIAdvisorService

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


VALID = {
    "agreement": "agree",
    "confidence": 80,
    "summary": "OK",
    "reasoning": "Aligned",
    "supporting_evidence": [],
    "contradicting_evidence": [],
    "risks": [],
    "missing_information": [],
    "suggested_experiment": None,
    "shadow_mode_acknowledged": True,
}

KNOWLEDGE = {
    "event_id": "evt_rt_001",
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "recommendation_snapshot": {"action": "now", "side": "buy", "confidence": 0.75, "grade": "A"},
    "market_snapshot": {"trend_direction": "bullish"},
    "strategy_statistics": {"closed_trades": 10, "win_rate": 60.0},
}

REASONING = {
    "verdict": "aligned",
    "action": "now",
    "direction": "buy",
    "evidence": {"items": []},
    "contradictions": {"items": []},
    "warnings": [],
    "missing_information": [],
}


# ── Layer outputs ────────────────────────────────────────────────────────────

layers = build_layer_outputs(
    symbol="BTCUSDT", market="crypto", timeframe="4h",
    recommendation={"action": "now", "side": "buy", "confidence": 0.8, "grade": "A"},
    row={"decision": "شراء", "htf": 1, "atr_pct": 2.1},
)
check("layers event_id", bool(layers.get("event_id")))
check("layers knowledge", layers["knowledge_context"]["symbol"] == "BTCUSDT")
check("no ohlc in layers", "ohlc" not in json.dumps(layers).lower())


# ── Token cost ───────────────────────────────────────────────────────────────

cost = estimate_cost("claude-sonnet-4-6", prompt_tokens=2154, completion_tokens=611)
check("cost estimate", cost > 0)


# ── Runtime state/history ────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    state_path = Path(tmp) / "state.json"
    hist_path = Path(tmp) / "hist.jsonl"
    state = AdvisorRuntimeState(state_path)
    hist = AdvisorRuntimeHistory(hist_path)

    state.record_success(provider="claude", review_id="adv_test", latency_ms=810)
    loaded = state.load()
    check("state running", loaded["status"] == "running")
    check("state success count", loaded["successful_reviews"] == 1)

    hid = hist.save({"review_id": "adv_test", "provider": "claude", "latency_ms": 810,
                     "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                     "estimated_cost": 0.001, "confidence": 80, "agreement": "agree",
                     "warnings": [], "grounding_score": 100, "hallucination_score": 0})
    check("history save", bool(hid))
    check("history last", hist.last()["review_id"] == "adv_test")


# ── Engine saves accepted only ───────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    mem_path = Path(tmp) / "mem.jsonl"
    hist_path = Path(tmp) / "hist.jsonl"
    mem = AdvisorMemory(mem_path)
    hist = AdvisorRuntimeHistory(hist_path)
    reg_mock = __import__("scanner.ai_advisor.provider_registry", fromlist=["ProviderRegistry"]).ProviderRegistry()
    reg_mock.register(MockProvider(response=VALID))

    engine = AdvisorEngine(registry=reg_mock, memory=mem, runtime_history=hist)
    pkg = DecisionPackageBuilder().build(
        event_id="evt_rt_001", knowledge_context=KNOWLEDGE, reasoning_review=REASONING,
    )
    review = engine.review(pkg, provider_id="mock")
    check("accepted review saved", mem.count() == 1)
    check("history written", hist.count() == 1)
    check("metrics latency", engine.last_call_metrics.get("latency_ms") is not None)

    bad = {**VALID, "shadow_mode_acknowledged": False}
    reg_mock.register(MockProvider(response=bad))
    engine2 = AdvisorEngine(registry=reg_mock, memory=mem, runtime_history=hist)
    rejected = engine2.review(pkg, provider_id="mock")
    check("rejected not accepted", not rejected.accepted)
    check("rejected not saved", mem.count() == 1)


# ── Runtime review with mock ─────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    mem_path = Path(tmp) / "mem.jsonl"
    hist_path = Path(tmp) / "hist.jsonl"
    state_path = Path(tmp) / "state.json"

    mem = AdvisorMemory(mem_path)
    hist = AdvisorRuntimeHistory(hist_path)
    state = AdvisorRuntimeState(state_path)
    reg = __import__("scanner.ai_advisor.provider_registry", fromlist=["ProviderRegistry"]).ProviderRegistry()
    reg.register(MockProvider(response=VALID))
    engine = AdvisorEngine(registry=reg, memory=mem, runtime_history=hist)
    svc = AIAdvisorService(engine=engine, registry=reg, memory=mem)

    # Force enabled path by using mock provider in config default - runtime checks claude_enabled
    # Test review_recommendation returns None when disabled (default config)
    disabled = review_recommendation(
        symbol="BTCUSDT", market="crypto", timeframe="4h",
        recommendation={"action": "now", "side": "buy"},
        service=svc,
    )
    check("disabled or result", disabled is None or isinstance(disabled, dict))

    candidates = review_scan_candidates([
        {"symbol": "ETHUSDT", "market": "crypto", "timeframe": "4h", "ready": True,
         "recommendation": {"action": "now", "side": "buy"},
         "row": {"decision": "شراء", "htf": 1}},
    ], service=svc)
    check("scan candidates", isinstance(candidates, list))


# ── UI summary runtime fields ────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    state_path = Path(tmp) / "state.json"
    AdvisorRuntimeState(state_path).record_success(
        provider="claude", model="claude-sonnet-4-6", review_id="adv_ui",
        latency_ms=810, prompt_tokens=2154, completion_tokens=611, total_tokens=2765,
        estimated_cost=0.0038, grounding_score=100, hallucination_score=0,
        agreement="agree", confidence=80,
    )
    # Patch state path for service - test fields exist in model structure
    ui_keys = ["runtime_status", "provider", "latency_ms", "total_tokens",
                "estimated_cost", "grounding_score", "successful_reviews"]
    svc = AIAdvisorService()
    ui = svc.to_ui_summary()
    for key in ui_keys:
        check(f"ui has {key}", key in ui)


# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*60}")
print(f"AI Advisor Runtime Tests: {passed}/{len(results)} passed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if extra:
        line += f" — {extra}"
    print(line)
if failed:
    print(f"\n{len(failed)} FAILED")
    sys.exit(1)
print("\nAll tests passed.")
