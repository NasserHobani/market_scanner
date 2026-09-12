# -*- coding: utf-8 -*-
"""Unit tests for Unified Decision Package — run: python tests_ai_unified_package.py"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.unified_package import UnifiedPackageBuilder, UNIFIED_PACKAGE_VERSION
from scanner.ai_advisor.unified_pipeline import build_unified_package
from scanner.ai_advisor.package_compression import compress_package
from scanner.ai_advisor.token_optimizer import estimate_tokens, optimize_tokens
from scanner.ai_advisor.package_validator import PackageValidator
from scanner.ai_advisor.package_cache import PackageCache
from scanner.ai_advisor.prompt_builder import PromptBuilder

KNOWLEDGE = {
    "event_id": "evt_uni_001",
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
            {"evidence_id": "ev_trend", "label": "Bullish trend", "direction": "supports",
             "confidence": 0.8, "source": "market_snapshot.trend", "facts": ["trend=bullish"]},
        ],
    },
    "contradictions": {"items": []},
    "warnings": [],
}

SIMILARITY = {"available": True, "match_count": 8, "average_win_rate": 62.5, "average_r": 1.2}
PREDICTION = {"probability": 0.72, "confidence": 0.72, "model_id": "mdl_test", "model_version": "1.0.0"}
GUARDRAILS = {"passed": True, "violations": []}
FUSED = {"overall": 0.76, "components": {"reasoning": 0.78, "prediction": 0.72}}

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool) -> None:
    results.append((cond, name))


LAYER_KWARGS = dict(
    event_id="evt_uni_001",
    metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h",
              "trade_id": "t1", "scan_id": "s1", "strategy": "default"},
    recommendation={"action": "now", "side": "buy", "confidence": 0.75, "grade": "A",
                    "entry": 100.0, "stop": 95.0, "rr": 2.0},
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
    similarity_context=SIMILARITY,
    prediction=PREDICTION,
    guardrails=GUARDRAILS,
    fused_confidence=FUSED,
    decision_ai={"verdict": "aligned"},
)

# ── Builder ──────────────────────────────────────────────────────────────────

builder = UnifiedPackageBuilder()
pkg = builder.build(**LAYER_KWARGS)

check("package has id", bool(pkg.package_id))
check("package version", pkg.schema_version == UNIFIED_PACKAGE_VERSION)
check("metadata symbol", pkg.metadata.get("symbol") == "BTCUSDT")
check("recommendation action", pkg.recommendation.get("action") == "now")
check("knowledge regime", pkg.knowledge.get("market_regime") == "uptrend")
check("reasoning evidence", len(pkg.reasoning.get("evidence", [])) > 0)
check("similarity available", pkg.similarity.get("available") is True)
check("decision_ai guardrails", pkg.decision_ai.get("guardrails", {}).get("passed") is True)
check("evidence indexed", len(pkg.evidence_index) > 0)
check("no ohlc", "ohlc" not in json.dumps(pkg.to_dict()).lower())
check("legacy trade accessor", pkg.trade.get("symbol") == "BTCUSDT")
check("shadow mode", pkg.shadow_mode is True)

# ── Evidence traceability ────────────────────────────────────────────────────

ev = pkg.evidence_index[0]
check("evidence has id", bool(ev.evidence_id))
check("evidence has source_layer", bool(ev.source_layer))
check("evidence has reference", bool(ev.reference or ev.section))

# ── Compression ──────────────────────────────────────────────────────────────

compressed, stats = compress_package(pkg)
check("compression stats", "compression_ratio" in stats)
check("compressed package id preserved", compressed.package_id == pkg.package_id)

# ── Token optimizer ─────────────────────────────────────────────────────────

tokens = estimate_tokens(pkg)
check("token estimate > 0", tokens > 0)
optimized, opt_stats = optimize_tokens(pkg, budget=50000)
check("optimizer within budget", estimate_tokens(optimized) <= 50000 or not opt_stats.get("sections_removed"))

# ── Validator ────────────────────────────────────────────────────────────────

validator = PackageValidator()
valid = validator.validate(pkg)
check("package valid", valid.valid)
check("no validation errors", len(valid.errors) == 0)

# ── Pipeline ─────────────────────────────────────────────────────────────────

start = time.monotonic()
result = build_unified_package(use_cache=False, **LAYER_KWARGS)
build_ms = (time.monotonic() - start) * 1000
check("pipeline produces package", result.package is not None)
check("pipeline diagnostics", "token_estimate" in result.diagnostics)
check("pipeline build time recorded", result.build_time_ms >= 0)

# ── Cache ───────────────────────────────────────────────────────────────────

cache = PackageCache(path=Path(__file__).parent / "data" / "test_package_cache.json")
key = cache.fingerprint(symbol="BTCUSDT", market="crypto", timeframe="4h",
                        recommendation=LAYER_KWARGS["recommendation"])
cache.put(key, pkg)
cached = cache.get(key)
check("cache hit", cached is not None)
check("cache package id", cached.package_id == pkg.package_id if cached else False)

# ── Prompt builder ───────────────────────────────────────────────────────────

prompt = PromptBuilder().build(pkg)
# ‏AIA-13.1: لم يعد يُرسَل تفريغ الحزمة، بل إحاطة سوق مضغوطة.
# الاختبار يحرس الغرض: أن يصل النموذج سياقاً لا JSON خاماً.
check("prompt sends compact briefing", "إحاطة السوق" in prompt.user_prompt)
check("prompt has no raw package dump", "```json" not in prompt.user_prompt)
check("prompt package id", prompt.package_id == pkg.package_id)

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"\n{'=' * 60}")
print(f"Unified Package Tests: {passed}/{total} passed")
print(f"{'=' * 60}")
for ok, name in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
print(f"\nBuild time (uncached): {build_ms:.1f} ms")
if passed < total:
    sys.exit(1)
print("\nAll tests passed.")
