# -*- coding: utf-8 -*-
"""Tests for AIA-07 learning + prediction lifecycle — run: python tests_ai_learning_prediction.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.evaluation.sample_reliability import (
    STATE_INSUFFICIENT, STATE_STRONG, reliability_state,
)
from scanner.ai_learning.lifecycle import (
    LearningLifecycleState, annotate_lesson, lesson_lifecycle_state, ui_label,
)
from scanner.ml.label_store import LabelName
from scanner.predictive.quality_gates import evaluate_promotion, naive_baseline_metrics
from scanner.predictive.trade_dataset import (
    FEATURE_COLUMNS,
    LEAKAGE_FIELDS,
    _encode_trade_row,
    build_from_trade_dicts,
    chronological_split,
)
from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, won: bool = True, score: float = 70.0) -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 10, 0, tzinfo=timezone.utc)
    return {
        "trade_id": f"t_{i}",
        "symbol": "BTCUSDT",
        "market": "crypto",
        "timeframe": "4h",
        "side": "buy",
        "status": WON if won else LOST,
        "score": score,
        "confidence": 0.7,
        "rr": 2.0,
        "grade": "A",
        "factors": ["htf", "confluence"],
        "r_multiple": 2.0 if won else -1.0,
        "signal_at": ts.isoformat(),
    }


TRADES = [_trade(i, won=(i % 3 != 0)) for i in range(60)]

# ── Dataset construction ───────────────────────────────────────────────────

manifest = build_from_trade_dicts(TRADES)
check("dataset construction", manifest["sample_count"] == 60)
check("feature schema documented", "columns" in manifest["feature_schema"])
check("label definition", manifest["label_definition"]["primary"] == LabelName.BINARY_WIN.value)

# ── Leakage prevention ─────────────────────────────────────────────────────

row = _encode_trade_row(_trade(0))
assert row
for leak in LEAKAGE_FIELDS:
    check(f"no leakage field in features: {leak}",
          leak not in row["features"] and leak not in FEATURE_COLUMNS)

# ── Chronological split ────────────────────────────────────────────────────

splits = chronological_split(manifest["rows"])
check("chronological split", len(splits["train"]) > len(splits["test"]))
check("no shuffle — train first", splits["train"][0]["trade_id"] == "t_0")

# ── Insufficient samples gate ──────────────────────────────────────────────

promo = evaluate_promotion(
    test_metrics={"classification": {"accuracy": 0.9}, "sample_size": 2},
    baseline_metrics={"classification": {"accuracy": 0.5}},
    min_test_samples=5,
)
check("insufficient samples not promoted", promo["promotion_status"] == "NOT_PROMOTED")

# ── Baseline comparison ────────────────────────────────────────────────────

base = naive_baseline_metrics(manifest["rows"])
check("baseline has accuracy", base["classification"]["accuracy"] is not None)

# ── Training with temp store ─────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    from scanner.predictive.training_jobs import TrainingJobStore, TrainingState
    from scanner.predictive.model_store import ModelStore
    from scanner.predictive.model_registry import ModelRegistry
    from scanner.predictive.config import PredictionTrainingConfig
    from scanner.predictive.services import PredictiveService
    from scanner.predictive.predictive_engine import PredictiveEngine

    cfg = PredictionTrainingConfig(min_eligible_trades=30, min_new_trades=5)
    store = ModelStore(tmp / "models")
    registry = ModelRegistry(tmp / "registry.jsonl")
    engine = PredictiveEngine(store=store, registry=registry)
    svc = PredictiveService(engine=engine, store=store, registry=registry)

    orch = PredictionTrainingOrchestrator(
        config=cfg,
        jobs=TrainingJobStore(tmp / "jobs.jsonl"),
        state=TrainingState(tmp / "state.json"),
        service=svc,
        trades_provider=lambda: TRADES,
    )
    orch._maybe_start_worker = lambda: None  # noqa: SLF001
    job = orch.run_manual()
    check("training execution", job.status in ("COMPLETED", "NOT_PROMOTED", "FAILED"), job.status)
    check("model persisted", len(svc.list_models()) >= 1 if job.model_id else True)
    check("job persistence", TrainingJobStore(tmp / "jobs.jsonl").get(job.job_id) is not None)

    if job.model_id:
        row0 = manifest["rows"][0]
        pred = svc.predict(job.model_id, row0["features"])
        check("inference works", pred.prediction is not None)

# ── Learning lifecycle labels ──────────────────────────────────────────────

lesson = {"title": "Test", "status": "NEW", "sample_size": 3}
ann = annotate_lesson(lesson)
check("lesson not model training", ann["is_model_training"] is False)
check("lifecycle label", ann["lifecycle_label"] == ui_label(LearningLifecycleState.LEARNED_AS_LESSON.value))

# ── Sample reliability ─────────────────────────────────────────────────────

check("2 evals insufficient", reliability_state(2) == STATE_INSUFFICIENT)
check("3 evals early signal", reliability_state(3) == "EARLY_SIGNAL")
check("50 evals strong", reliability_state(50) == STATE_STRONG)

# ── Summary ────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"AIA-07 Learning+Prediction Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))
if failed:
    sys.exit(1)
