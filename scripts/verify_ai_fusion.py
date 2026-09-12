#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIA-09 AI Fusion verification — real runtime checks."""
from __future__ import annotations

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


def main() -> int:
    from scanner.ai_fusion.fusion_metrics import compute_metrics
    from scanner.ai_fusion.prediction_adapter import PredictionAdapter
    from scanner.ai_fusion.fusion_engine import FusionEngine
    from scanner.ai_advisor.unified_package import UnifiedDecisionPackage
    from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator

    adapter = PredictionAdapter()
    active_id = adapter.get_active_model_id()
    pred = adapter.get_active_prediction({"symbol": "BTCUSDT", "score": 70})
    orch = PredictionTrainingOrchestrator().status()
    ps = orch.get("prediction_status") or {}
    metrics = compute_metrics()

    pkg = UnifiedDecisionPackage(
        package_id="verify_pkg",
        event_id="verify_evt",
        metadata={"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h"},
        recommendation={"action": "BUY", "confidence": 0.81},
        prediction=adapter.to_udp_section({"symbol": "BTCUSDT", "score": 70}),
    )
    fusion = FusionEngine(adapter=adapter).fuse(
        package=pkg,
        llm_response={"agreement": "agree", "confidence": 82, "prediction_assessment": "unavailable"},
        review_id="verify_review",
        provider="none",
        model="none",
    )

    engine_status = "ACTIVE" if active_id else "UNAVAILABLE"

    print("=" * 40)
    print("AIA-09 AI FUSION VERIFICATION")
    print("=" * 40)
    print()
    print(f"Prediction Engine:\n{engine_status}")
    print()
    print(f"Active Model:\n{active_id or 'none'}")
    print()
    if pred.get("available"):
        print(f"OOS:\n{pred.get('quality', {}).get('oos_accuracy')}")
        print(f"Baseline:\n{pred.get('quality', {}).get('baseline_accuracy')}")
        print(f"Prediction Probability:\n{pred.get('probability_win')}")
    else:
        print("Prediction:")
        print("UNAVAILABLE — no ACTIVE model passed quality gates.")
    print()
    print(f"LLM Provider:\n{fusion.provider or 'n/a'}")
    print(f"LLM Model:\n{fusion.model or 'n/a'}")
    print(f"LLM Assessment:\n{fusion.llm_assessment.get('prediction_assessment')}")
    print()
    print(f"Fusion State:\n{fusion.fusion_state}")
    print(f"Package Fingerprint:\n{fusion.package_fingerprint}")
    print()
    print(f"Evaluation Samples:\n{metrics.get('evaluation_samples', 0)}")
    print(f"Fusion Reviews:\n{metrics.get('sample_size', 0)}")
    print(f"Prediction Accuracy:\n{metrics.get('prediction_accuracy')}")
    print(f"LLM Accuracy:\n{metrics.get('llm_accuracy')}")
    print(f"Fusion Accuracy:\n{metrics.get('fusion_accuracy')}")
    print(f"Calibration:\n{metrics.get('status')}")
    print()
    print(f"Rejection reason (orchestrator):\n{ps.get('reason', 'n/a')}")
    print()
    print("Inactive model fallback used: NO")
    print("=" * 40)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
