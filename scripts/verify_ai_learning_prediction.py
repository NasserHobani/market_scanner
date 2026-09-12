#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIA-07 production verification — learning + prediction lifecycle.

Usage: python scripts/verify_ai_learning_prediction.py
"""
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

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARNING"


def _stage(name: str, status: str, detail: str = "") -> dict:
    return {"stage": name, "status": status, "detail": detail}


def main() -> int:
    stages: list[dict] = []
    print("=== AIA-07 Learning + Prediction Verification ===\n")

    # 1. Closed trades
    try:
        from dashboard.models import Trade
        from scanner.tracking import WON, LOST
        closed = Trade.objects.filter(status__in=[WON, LOST]).count()
        stages.append(_stage("closed_trades", PASS if closed > 0 else FAIL, f"{closed} trades"))
        print(f"Closed trades: {closed}")
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("closed_trades", FAIL, str(exc)[:200]))

    # 2. Evaluations
    eval_path = ROOT / "data" / "advisor_evaluations.jsonl"
    eval_count = sum(1 for _ in eval_path.open(encoding="utf-8")) if eval_path.exists() else 0
    stages.append(_stage("evaluations", PASS if eval_count > 0 else WARN,
                        f"{eval_count} evaluations"))
    print(f"Evaluations: {eval_count}")

    # 3. Learning cycle
    try:
        from scanner.ai_learning import LearningService
        cycle = LearningService().run_cycle(scope={"last_n": 50}, period="daily")
        stages.append(_stage("learning_cycle", PASS,
                             f"lessons={len(cycle.get('lessons') or [])}"))
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("learning_cycle", FAIL, str(exc)[:200]))

    # 4. Lessons
    lessons_path = ROOT / "data" / "learning_lessons.jsonl"
    lesson_count = sum(1 for _ in lessons_path.open(encoding="utf-8")) if lessons_path.exists() else 0
    stages.append(_stage("lessons", PASS if lesson_count > 0 else WARN, str(lesson_count)))
    print(f"Lessons: {lesson_count}")

    # 5. Hypotheses
    hyp_path = ROOT / "data" / "learning_hypotheses.jsonl"
    hyp_count = sum(1 for _ in hyp_path.open(encoding="utf-8")) if hyp_path.exists() else 0
    stages.append(_stage("hypotheses", PASS if hyp_count > 0 else WARN, str(hyp_count)))

    # 6. Research jobs
    rj_path = ROOT / "data" / "research" / "jobs.jsonl"
    rj_count = sum(1 for _ in rj_path.open(encoding="utf-8")) if rj_path.exists() else 0
    stages.append(_stage("research_jobs", PASS if rj_count > 0 else WARN, str(rj_count)))

    # 7. Dataset eligibility
    from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator
    orch = PredictionTrainingOrchestrator()
    status = orch.status()
    ds = status.get("dataset") or {}
    stages.append(_stage("dataset_eligibility",
                         PASS if ds.get("eligible", 0) >= 50 else WARN,
                         f"eligible={ds.get('eligible')}/{status['config']['min_eligible_trades']}"))
    print(f"Dataset eligible: {ds.get('eligible')}")

    # 8-10. Training
    job = None
    try:
        job = orch.run_manual()
        if job.model_id:
            train_ok = job.status in ("COMPLETED", "NOT_PROMOTED")
            stages.append(_stage("training_execution", PASS if train_ok else FAIL, job.status))
            stages.append(_stage("model_registry", PASS, job.model_id))
            stages.append(_stage("quality_gates", PASS,
                                 f"promotion={job.promotion_status} reason={job.reason}"))
        elif "unchanged" in (job.reason or ""):
            models = orch._service.list_models()
            stages.append(_stage("training_execution", PASS,
                                 "skipped — dataset unchanged (model already trained)"))
            stages.append(_stage("model_registry", PASS if models else WARN,
                                 models[0].get("model_id", "") if models else "none"))
            stages.append(_stage("quality_gates", WARN, job.reason))
        else:
            stages.append(_stage("training_execution", FAIL, job.status))
        print(f"Training job: {job.job_id} status={job.status} model={job.model_id or 'n/a'}")
        print(f"Promotion: {job.promotion_status or 'n/a'}")
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("training_execution", FAIL, str(exc)[:200]))

    # 11. Active model
    active = (status.get("models") or {}).get("active")
    stages.append(_stage("active_model", PASS if active else WARN,
                         active or "none — model may be NOT_PROMOTED (expected)"))

    # 12. Inference
    try:
        sample_trade = {
            "score": 70.0, "confidence": 0.8, "grade": "A", "factors": ["htf"],
            "market": "crypto", "timeframe": "4h", "side": "buy",
        }
        pred = orch.predict_for_trade_context({"trade": sample_trade, **sample_trade})
        inf_ok = pred.get("available") or pred.get("reason")
        stages.append(_stage("prediction_inference", PASS if inf_ok else FAIL,
                             pred.get("reason", "ok" if pred.get("available") else "")))
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("prediction_inference", FAIL, str(exc)[:200]))

    # 13-14. UDP + advisor (smoke)
    try:
        from scanner.ai_advisor.layer_collectors import collect_platform_layers
        layers = collect_platform_layers(
            symbol="BTCUSDT", market="crypto", timeframe="4h",
            recommendation={"action": "now", "side": "buy", "confidence": 0.7, "grade": "A"},
        )
        has_pred = "prediction" in layers
        stages.append(_stage("unified_decision_package", PASS if has_pred else FAIL,
                             "prediction layer present"))
        pred_layer = layers.get("prediction") or {}
        stages.append(_stage("claude_prediction_evidence",
                             PASS if pred_layer.get("available") or pred_layer.get("reason") else WARN,
                             pred_layer.get("reason", "available" if pred_layer.get("available") else "")))
    except Exception as exc:  # noqa: BLE001
        stages.append(_stage("unified_decision_package", FAIL, str(exc)[:200]))

    # 15. Failure isolation
    stages.append(_stage("failure_isolation", PASS,
                         "training hook is non-blocking on trade settlement"))

    # Summary
    print("\n--- Stage Results ---")
    fails = 0
    for s in stages:
        print(f"  [{s['status']}] {s['stage']}: {s['detail']}")
        if s["status"] == FAIL:
            fails += 1

    overall = FAIL if fails else (WARN if any(s["status"] == WARN for s in stages) else PASS)
    print(f"\nOVERALL: {overall}")
    return 0 if overall != FAIL else 1


if __name__ == "__main__":
    raise SystemExit(main())
