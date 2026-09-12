# -*- coding: utf-8 -*-
"""AIA-09 AI Fusion tests — run: python tests_ai_fusion.py"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.unified_package import UnifiedDecisionPackage
from scanner.ai_fusion.agreement_analyzer import analyze as analyze_agreement
from scanner.ai_fusion.confidence_policy import separate_confidences
from scanner.ai_fusion.fusion_engine import FusionEngine
from scanner.ai_fusion.fusion_history import FusionHistory
from scanner.ai_fusion.outcome_evaluator import evaluate_outcome
from scanner.ai_fusion.prediction_adapter import PredictionAdapter, REASON_NO_ACTIVE

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool) -> None:
    results.append((cond, name))


def _pkg(**kwargs) -> UnifiedDecisionPackage:
    defaults = dict(
        package_id="pkg_test",
        event_id="evt_test",
        metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h"},
        recommendation={"action": "BUY", "confidence": 0.81},
        prediction={"available": False, "reason": REASON_NO_ACTIVE},
        evidence_index=(),
    )
    defaults.update(kwargs)
    return UnifiedDecisionPackage(**defaults)


# Prediction adapter — no active model
adapter = PredictionAdapter(state_loader=lambda: {"active_model_id": ""})
pred = adapter.get_active_prediction({"symbol": "BTCUSDT"})
check("no active model unavailable", pred["available"] is False)
check("reason no_active_model", pred.get("reason") == REASON_NO_ACTIVE)

# Rejected model blocked
adapter_blocked = PredictionAdapter(
    state_loader=lambda: {"active_model_id": "mdl_fake"},
    service=type("S", (), {
        "list_models": lambda self: [{
            "model_id": "mdl_fake",
            "status": "NOT_PROMOTED",
            "quality_gate_result": {"promotion_status": "NOT_PROMOTED", "passed": False},
            "feature_columns": ["score"],
        }],
        "predict": lambda *a, **k: None,
    })(),
)
blocked = adapter_blocked.get_active_prediction({"features": {"score": 70}})
check("NOT_PROMOTED blocked", not blocked.get("available"))

# Agreement — prediction unavailable
ag = analyze_agreement(
    platform_action="BUY",
    prediction={"available": False},
    llm_assessment={"agreement": "agree"},
)
check("fusion PREDICTION_UNAVAILABLE", ag["fusion_state"] == "PREDICTION_UNAVAILABLE")

# Agreement — aligned
ag2 = analyze_agreement(
    platform_action="BUY",
    prediction={"available": True, "prediction": "WIN", "probability_win": 0.68},
    llm_assessment={"agreement": "agree"},
)
check("aligned case", ag2["fusion_state"] == "ALIGNED")

# Agreement — LLM conflict
ag3 = analyze_agreement(
    platform_action="BUY",
    prediction={"available": True, "prediction": "WIN", "probability_win": 0.68},
    llm_assessment={"agreement": "disagree"},
)
check("llm conflict", ag3["fusion_state"] == "LLM_CONFLICT")

# Agreement — statistical conflict
ag4 = analyze_agreement(
    platform_action="BUY",
    prediction={"available": True, "prediction": "LOSS", "probability_win": 0.35},
    llm_assessment={"agreement": "disagree"},
)
check("statistical conflict", ag4["fusion_state"] == "STATISTICAL_CONFLICT")

# Confidence separation
sep = separate_confidences(
    recommendation={"confidence": 81},
    prediction={"probability_win": 0.68},
    llm_response={"confidence": 82},
)
check("three confidences separate", sep["platform_confidence"] == 0.81)
check("prediction prob win", sep["prediction_probability"]["win"] == 0.68)
check("llm conf", sep["llm_confidence"] == 0.82)

# Fusion engine
engine = FusionEngine(adapter=adapter)
fusion = engine.fuse(
    package=_pkg(),
    llm_response={"agreement": "agree", "confidence": 82, "prediction_assessment": "unavailable"},
    review_id="adv_test",
    provider="claude",
    model="claude-test",
)
check("fusion state unavailable", fusion.fusion_state == "PREDICTION_UNAVAILABLE")
check("policy no trading change", fusion.policy.get("modifies_trading") is False)

# History append-only
with tempfile.TemporaryDirectory() as tmp:
    hist = FusionHistory(path=Path(tmp) / "fusion.jsonl")
    fid = hist.append({"review_id": "r1", "fusion_state": "PREDICTION_UNAVAILABLE"})
    fid2 = hist.append({"review_id": "r2", "fusion_state": "ALIGNED"})
    check("history append", hist.count() == 2)
    check("history ids unique", fid != fid2)

# Outcome evaluation
out = evaluate_outcome(
    trade_result={"status": "won", "r_multiple": 2.0, "trade_id": "t1"},
    fusion_record={
        "prediction_available": True,
        "prediction_label": "WIN",
        "prediction_probability": 0.68,
        "llm_agreement": "agree",
        "fusion_state": "ALIGNED",
    },
    advisor_evaluation={"advisor_correct": True},
)
check("prediction correct", out["prediction"]["correct"] is True)
check("fusion pattern", out["fusion"]["pattern"] == "prediction_and_llm_agree_correct")

# UDP section unavailable
udp = adapter.to_udp_section({})
check("udp unavailable", udp.get("available") is False)

passed = sum(1 for ok, _ in results if ok)
failed = [n for ok, n in results if not ok]
print(f"\nAIA-09 Fusion Tests: {passed}/{len(results)} passed")
for ok, name in results:
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")
if failed:
    sys.exit(1)
print("All tests passed.")
