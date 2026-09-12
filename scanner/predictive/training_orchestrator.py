# -*- coding: utf-8 -*-
"""Prediction training orchestrator — dataset → train → quality gates."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from scanner.ml.label_store import LabelName

from .calibration import calibration_report
from .config import PredictionTrainingConfig, load_prediction_config
from .feature_importance import extract_importance
from .predictive_engine import ValidationMode
from .quality_gates import (
    PROMOTION_ACTIVE,
    PROMOTION_CANDIDATE,
    PROMOTION_NOT_PROMOTED,
    evaluate_promotion,
    naive_baseline_metrics,
)
from .services import PredictiveService
from .trainer import ModelArtifact, TrainingConfig, Trainer
from .trade_dataset import (
    DEFAULT_FEATURE_VERSION,
    FEATURE_COLUMNS,
    FEATURE_COLUMNS_V2,
    build_from_trade_dicts,
    chronological_split,
    columns_for_version,
    load_trades_from_django,
    persist_dataset_manifest,
)
from .training_jobs import (
    TrainingJob,
    TrainingJobStatus,
    TrainingJobStore,
    TrainingState,
    new_job_id,
)

log = logging.getLogger("scanner.predictive.orchestrator")

TRIGGER_TRADE_COUNT = "trade_count"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_MANUAL = "manual"
TRIGGER_RESEARCH = "research_validated"

UNAVAILABLE_REASON_AR = "لا يوجد نموذج اجتاز بوابة الجودة"


def _version_label(feature_version: str) -> str:
    if feature_version.startswith("2"):
        return "V2"
    return "V1"


def _rejection_reasons_ar(gate: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    improvement = gate.get("improvement")
    if improvement is not None and float(improvement) < 0:
        reasons.append("OOS أقل من Baseline")
    if gate.get("walk_forward_pass") is False:
        reasons.append("Walk-Forward instability")
    if gate.get("passed") is False and not reasons:
        reasons.append("لا توجد أفضلية إحصائية كافية")
    elif gate.get("passed") is False:
        if gate.get("improvement") is not None and float(gate.get("improvement", 0)) < 0.02:
            if "لا توجد أفضلية إحصائية كافية" not in reasons:
                reasons.append("لا توجد أفضلية إحصائية كافية")
    if gate.get("calibration_pass") is False:
        reasons.append("فشل المعايرة (CALIBRATION_FAILED)")
    return reasons


def _summarize_model(m: dict[str, Any], *,
                     job_metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    gate = (m.get("quality_gate_result") or
            (m.get("extra") or {}).get("promotion_gate") or {})
    if not gate and job_metrics:
        gate = job_metrics.get("promotion") or {}
    cols = m.get("feature_columns") or []
    fv = str(m.get("feature_version") or "1.0.0")
    if len(cols) > 11:
        fv = "2.0.0"
    version = _version_label(fv)
    oos = gate.get("test_accuracy")
    if oos is None:
        oos = (job_metrics or {}).get("test", {}).get("classification", {}).get("accuracy")
    if oos is None:
        oos = (m.get("evaluation_summary") or {}).get("classification", {}).get("accuracy")
    base = gate.get("baseline_accuracy")
    if base is None:
        base = (job_metrics or {}).get("baseline", {}).get("classification", {}).get("accuracy")
    cal = gate.get("calibration_status")
    if cal is None:
        cal = (job_metrics or {}).get("calibration", {}).get("calibration_status")
    wf_pass = gate.get("walk_forward_pass")
    if wf_pass is None and job_metrics:
        promo = job_metrics.get("promotion") or {}
        wf_pass = promo.get("walk_forward_pass")
    return {
        "model_id": m.get("model_id", ""),
        "version": version,
        "feature_version": fv,
        "oos_accuracy": oos,
        "baseline_accuracy": base,
        "promotion_status": gate.get("promotion_status", PROMOTION_NOT_PROMOTED),
        "walk_forward_pass": wf_pass,
        "walk_forward_status": "PASS" if wf_pass else "FAILED" if wf_pass is False else None,
        "calibration_status": cal,
        "passed": gate.get("passed", False),
    }


def _sort_models_newest(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        models,
        key=lambda m: str(m.get("training_timestamp") or ""),
        reverse=True,
    )


def _job_metrics_by_model(jobs: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for job in reversed(jobs):
        mid = getattr(job, "model_id", "") or (job.get("model_id") if isinstance(job, dict) else "")
        if mid and mid not in out:
            metrics = getattr(job, "metrics", None) or (job.get("metrics") if isinstance(job, dict) else {})
            out[mid] = metrics or {}
    return out


class PredictionTrainingOrchestrator:
    """Automatic prediction training — advisory only, never modifies trading."""

    def __init__(self,
                 config: PredictionTrainingConfig | None = None,
                 jobs: TrainingJobStore | None = None,
                 state: TrainingState | None = None,
                 service: PredictiveService | None = None,
                 trades_provider: Callable[[], list[dict[str, Any]]] | None = None) -> None:
        self._cfg = config or load_prediction_config()
        self._jobs = jobs or TrainingJobStore()
        self._state = TrainingState() if state is None else state
        self._service = service or PredictiveService()
        self._trades_provider = trades_provider
        self._lock = threading.Lock()
        self._worker_started = False

    def on_trade_closed(self, trade: Any = None) -> dict[str, Any] | None:
        if not self._cfg.auto_enabled:
            return None
        try:
            count = self._state.increment_trade_counter()
            if count < self._cfg.min_new_trades:
                return None
            job = self._queue_job(TRIGGER_TRADE_COUNT, reason=f"{count} trades since last training")
            self._maybe_start_worker()
            return {"queued_job": job.job_id} if job else None
        except Exception as exc:  # noqa: BLE001
            log.warning("prediction training hook: %s", str(exc)[:200])
            return None

    def run_manual(self) -> TrainingJob:
        job = self._queue_job(TRIGGER_MANUAL, reason="Manual training trigger")
        if not job:
            raise RuntimeError("failed to queue training job")
        return self._execute_job(job.job_id) or job

    def promote_model(self, model_id: str) -> dict[str, Any]:
        """Explicit human/policy promotion — sets active model."""
        data = self._state.load()
        candidates = set(data.get("candidate_model_ids") or [])
        models = {m["model_id"]: m for m in self._service.list_models()}
        if model_id not in models and model_id not in candidates:
            return {"ok": False, "error": "model not found or not a candidate"}
        data["active_model_id"] = model_id
        self._state.save(data)
        try:
            artifact = self._service.load_model(model_id)
            artifact.metadata.status = PROMOTION_ACTIVE
            artifact.metadata.extra["promotion_status"] = PROMOTION_ACTIVE
            self._service._engine._store.save(artifact)
        except Exception as exc:  # noqa: BLE001
            log.warning("promote metadata update: %s", str(exc)[:120])
        return {"ok": True, "active_model_id": model_id}

    def status(self) -> dict[str, Any]:
        cfg = self._cfg
        st = self._state.load()
        jobs = self._jobs.list_all()
        models = _sort_models_newest(self._service.list_models())
        active_id = st.get("active_model_id", "")
        candidates = list(st.get("candidate_model_ids") or [])

        dataset_info = self._dataset_eligibility()
        active_model = next((m for m in models if m.get("model_id") == active_id), None)
        job_metrics_map = _job_metrics_by_model(jobs)
        model_summaries = [
            _summarize_model(m, job_metrics=job_metrics_map.get(m.get("model_id", "")))
            for m in models
        ]

        return {
            "enabled": cfg.auto_enabled,
            "prediction_status": self._prediction_status(
                active_model, dataset_info, model_summaries),
            "dataset": dataset_info,
            "training": {
                "last_training_at": st.get("last_training_at", ""),
                "trades_since_last_training": int(st.get("trades_since_last_training") or 0),
                "next_trigger_trades": cfg.min_new_trades,
                "last_dataset_id": st.get("last_dataset_id", ""),
                "last_dataset_fingerprint": st.get("last_dataset_fingerprint", ""),
            },
            "models": {
                "active": active_id or None,
                "active_metrics": (active_model or {}).get("evaluation_summary"),
                "candidates": candidates,
                "trained_count": len(models),
                "rejected_count": sum(
                    1 for j in jobs if j.promotion_status == PROMOTION_NOT_PROMOTED),
                "registry": model_summaries,
            },
            "jobs": {
                "pending": sum(1 for j in jobs if j.status == TrainingJobStatus.PENDING.value),
                "completed": sum(1 for j in jobs if j.status == TrainingJobStatus.COMPLETED.value),
                "failed": sum(1 for j in jobs if j.status == TrainingJobStatus.FAILED.value),
                "insufficient_data": sum(
                    1 for j in jobs if j.status == TrainingJobStatus.INSUFFICIENT_DATA.value),
            },
            "config": {
                "min_eligible_trades": cfg.min_eligible_trades,
                "min_new_trades": cfg.min_new_trades,
            },
        }

    def _prediction_status(self, active_model: dict | None,
                           dataset_info: dict[str, Any],
                           model_summaries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if active_model:
            ev = active_model.get("evaluation_summary") or {}
            cls = ev.get("classification") or {}
            promo = (active_model.get("extra") or {}).get("promotion_status", "")
            gate = (active_model.get("quality_gate_result") or
                    (active_model.get("extra") or {}).get("promotion_gate") or {})
            baseline = (active_model.get("baseline_metrics") or
                        (active_model.get("extra") or {}).get("baseline_comparison") or {})
            base_acc = (baseline.get("classification") or {}).get("accuracy")
            oos = cls.get("accuracy")
            return {
                "status": "ACTIVE",
                "reason": "",
                "model_id": active_model.get("model_id"),
                "oos_accuracy": oos,
                "baseline_accuracy": base_acc,
                "improvement_over_baseline": (
                    round(float(oos) - float(base_acc), 4)
                    if oos is not None and base_acc is not None else None
                ),
                "calibration": (active_model.get("calibration_metrics") or {}).get(
                    "calibration_status") or cls.get("calibration", "unknown"),
                "walk_forward_pass": gate.get("walk_forward_pass"),
                "promotion_status": promo or PROMOTION_ACTIVE,
                "feature_count": len(active_model.get("feature_columns") or []),
            }

        # Check latest NOT_PROMOTED model for rejection details
        models = _sort_models_newest(self._service.list_models())
        jobs = self._jobs.list_all()
        job_metrics_map = _job_metrics_by_model(jobs)
        latest = models[0] if models else None
        rejection_detail: dict[str, Any] = {}
        gate: dict[str, Any] = {}
        if latest:
            mid = latest.get("model_id", "")
            jm = job_metrics_map.get(mid, {})
            gate = (latest.get("quality_gate_result") or
                    (latest.get("extra") or {}).get("promotion_gate") or
                    jm.get("promotion") or {})
            promo = gate.get("promotion_status", PROMOTION_NOT_PROMOTED)
            if promo == PROMOTION_NOT_PROMOTED or not gate.get("passed", False):
                cal = gate.get("calibration_status")
                if not cal:
                    cal = (jm.get("calibration") or {}).get("calibration_status")
                rejection_detail = {
                    "current_model_id": mid,
                    "oos_accuracy": gate.get("test_accuracy") or (
                        (jm.get("test") or {}).get("classification", {}).get("accuracy")),
                    "baseline_accuracy": gate.get("baseline_accuracy") or (
                        (jm.get("baseline") or {}).get("classification", {}).get("accuracy")),
                    "improvement": gate.get("improvement_pct"),
                    "quality_gate": promo,
                    "quality_gate_reason": gate.get("reason", ""),
                    "calibration": cal,
                    "calibration_status": cal,
                    "walk_forward_pass": gate.get("walk_forward_pass"),
                    "walk_forward_status": (
                        "PASS" if gate.get("walk_forward_pass") else "FAILED"
                    ),
                    "rejection_reasons": _rejection_reasons_ar(gate),
                    "feature_count": len(latest.get("feature_columns") or []),
                }

        registry = model_summaries or [
            _summarize_model(m, job_metrics=job_metrics_map.get(m.get("model_id", "")))
            for m in models
        ]

        eligible = dataset_info.get("eligible", 0)
        min_req = self._cfg.min_eligible_trades
        if eligible < min_req:
            return {
                "status": "UNAVAILABLE",
                "reason": f"insufficient eligible trades ({eligible}/{min_req})",
                **rejection_detail,
            }
        if eligible > 0 and not models:
            return {
                "status": "UNAVAILABLE",
                "reason": "eligible dataset exists but no model trained yet",
            }
        reason = UNAVAILABLE_REASON_AR if rejection_detail else (
            dataset_info.get("reason") or "no active model"
        )
        return {
            "status": "UNAVAILABLE",
            "reason": reason,
            "reason_ar": UNAVAILABLE_REASON_AR if rejection_detail else reason,
            "eligible_samples": dataset_info.get("eligible", 0),
            "model_registry": registry,
            **rejection_detail,
        }

    def _dataset_eligibility(self) -> dict[str, Any]:
        trades = self._get_trades()
        manifest = build_from_trade_dicts(trades, feature_version=DEFAULT_FEATURE_VERSION)
        eligible = manifest["sample_count"]
        rejected = manifest["rejected_count"]
        min_req = self._cfg.min_eligible_trades
        reason = ""
        if eligible < min_req:
            reason = f"only {eligible} eligible trades (need {min_req})"
        elif rejected:
            reason = f"{rejected} trades rejected: {manifest.get('rejection_reasons', {})}"
        splits = chronological_split(manifest["rows"])
        return {
            "samples": len(trades),
            "eligible": eligible,
            "rejected": rejected,
            "reason": reason,
            "train_count": len(splits["train"]),
            "validation_count": len(splits["validation"]),
            "test_count": len(splits["test"]),
            "fingerprint": manifest.get("fingerprint", ""),
            "label_definition": manifest.get("label_definition", {}),
        }

    def _queue_job(self, trigger_type: str, *, reason: str = "") -> TrainingJob | None:
        dataset_info = self._dataset_eligibility()
        if dataset_info["eligible"] < self._cfg.min_eligible_trades:
            job = TrainingJob(
                job_id=new_job_id(),
                trigger_type=trigger_type,
                status=TrainingJobStatus.INSUFFICIENT_DATA.value,
                reason=dataset_info["reason"] or "insufficient eligible trades",
                metrics={"dataset": dataset_info},
            )
            self._jobs.append(job)
            return job

        st = self._state.load()
        fp = dataset_info.get("fingerprint", "")
        if fp and fp == st.get("last_dataset_fingerprint"):
            job = TrainingJob(
                job_id=new_job_id(),
                trigger_type=trigger_type,
                status=TrainingJobStatus.COMPLETED.value,
                reason="dataset unchanged since last training",
                metrics={"dataset": dataset_info},
            )
            self._jobs.append(job)
            return job

        job = TrainingJob(
            job_id=new_job_id(),
            trigger_type=trigger_type,
            status=TrainingJobStatus.PENDING.value,
            reason=reason,
        )
        self._jobs.append(job)
        return job

    def _maybe_start_worker(self) -> None:
        with self._lock:
            if self._worker_started:
                return
            self._worker_started = True
        t = threading.Thread(target=self._process_pending, daemon=True)
        t.start()

    def _process_pending(self) -> None:
        try:
            for job in self._jobs.list_all():
                if job.status == TrainingJobStatus.PENDING.value:
                    self._execute_job(job.job_id)
        finally:
            with self._lock:
                self._worker_started = False

    def _execute_job(self, job_id: str) -> TrainingJob | None:
        job = self._jobs.get(job_id)
        if not job or job.status != TrainingJobStatus.PENDING.value:
            return job

        start = time.monotonic()
        job.status = TrainingJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc).isoformat()
        self._jobs.append(job)

        try:
            trades = self._get_trades()
            feature_version = DEFAULT_FEATURE_VERSION
            manifest = build_from_trade_dicts(
                trades, feature_version=feature_version, validate_leakage=True)
            rows = manifest["rows"]
            if len(rows) < self._cfg.min_eligible_trades:
                job.status = TrainingJobStatus.INSUFFICIENT_DATA.value
                job.reason = f"{len(rows)}/{self._cfg.min_eligible_trades} eligible"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.duration_ms = round((time.monotonic() - start) * 1000, 1)
                self._jobs.append(job)
                return job

            persist_dataset_manifest(manifest)
            job.dataset_id = manifest["dataset_id"]

            splits = chronological_split(rows)
            train_rows = splits["train"]
            val_rows = splits["validation"]
            test_rows = splits["test"] or val_rows
            feature_cols = list(manifest["feature_schema"]["columns"])

            def _period(rows_slice: list[dict]) -> dict[str, str]:
                dates = [r.get("signal_at", "")[:10] for r in rows_slice if r.get("signal_at")]
                return {"start": dates[0], "end": dates[-1]} if dates else {}

            config = TrainingConfig(
                feature_columns=feature_cols,
                label_column=LabelName.BINARY_WIN.value,
                task_type="classification",
                dataset_id=manifest["dataset_id"],
            )

            artifact = self._service.train(
                train_rows,
                feature_columns=feature_cols,
                label_column=LabelName.BINARY_WIN.value,
                dataset_id=manifest["dataset_id"],
                run_walk_forward=self._cfg.walk_forward_enabled,
                walk_forward_mode=ValidationMode.WALK_FORWARD.value,
            )

            test_eval = self._service.evaluate(artifact.model_id, test_rows) if test_rows else {}
            baseline = naive_baseline_metrics(test_rows)

            y_true = [int(r.get(LabelName.BINARY_WIN.value) or 0) for r in test_rows]
            y_proba = []
            if test_rows:
                try:
                    loaded = self._service.load_model(artifact.model_id)
                    X, _, _ = Trainer._extract(test_rows, config)
                    y_proba = loaded.model.predict_proba(X, feature_names=feature_cols)
                except Exception:  # noqa: BLE001
                    pass
            cal = calibration_report(y_true, y_proba) if y_proba else {}

            wf = artifact.metadata.walk_forward_summary or {}
            promotion = evaluate_promotion(
                test_metrics=test_eval,
                baseline_metrics=baseline,
                walk_forward=wf,
                calibration=cal,
                min_test_samples=self._cfg.min_test_samples,
                min_accuracy_improvement=self._cfg.min_accuracy_improvement,
            )

            importance = extract_importance(artifact, feature_columns=feature_cols)

            artifact.metadata.evaluation_summary = test_eval
            artifact.metadata.feature_version = feature_version
            artifact.metadata.feature_schema_hash = manifest["feature_schema"].get(
                "feature_schema_hash", "")
            artifact.metadata.training_period = _period(train_rows)
            artifact.metadata.validation_period = _period(val_rows)
            artifact.metadata.test_period = _period(test_rows)
            artifact.metadata.baseline_metrics = baseline
            artifact.metadata.calibration_metrics = cal
            artifact.metadata.quality_gate_result = promotion
            artifact.metadata.extra["promotion_status"] = promotion["promotion_status"]
            artifact.metadata.extra["promotion_gate"] = promotion
            artifact.metadata.extra["baseline_comparison"] = baseline
            artifact.metadata.extra["feature_importance"] = importance
            artifact.metadata.extra["automatic"] = job.trigger_type != TRIGGER_MANUAL
            artifact.metadata.status = (
                PROMOTION_CANDIDATE if promotion["passed"] else PROMOTION_NOT_PROMOTED
            )
            self._service._engine._store.save(artifact)

            job.model_id = artifact.model_id
            job.promotion_status = promotion["promotion_status"]
            job.metrics = {
                "test": test_eval,
                "baseline": baseline,
                "promotion": promotion,
                "walk_forward": wf,
                "calibration": cal,
                "feature_importance": importance,
                "train_count": len(train_rows),
                "test_count": len(test_rows),
                "feature_version": feature_version,
                "feature_count": len(feature_cols),
            }

            if promotion["promotion_status"] == PROMOTION_CANDIDATE:
                job.status = TrainingJobStatus.COMPLETED.value
                self._state.reset_trade_counter(
                    dataset_id=manifest["dataset_id"],
                    fingerprint=manifest["fingerprint"],
                    model_id=artifact.model_id,
                    promotion_status=PROMOTION_CANDIDATE,
                )
            else:
                job.status = TrainingJobStatus.NOT_PROMOTED.value
                job.reason = promotion.get("reason", "quality gates not passed")
                self._state.reset_trade_counter(
                    dataset_id=manifest["dataset_id"],
                    fingerprint=manifest["fingerprint"],
                )

            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._jobs.append(job)
            return job

        except Exception as exc:  # noqa: BLE001
            job.status = TrainingJobStatus.FAILED.value
            job.error = str(exc)[:300]
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._jobs.append(job)
            log.warning("training job %s failed: %s", job_id, job.error)
            return job

    def _get_trades(self) -> list[dict[str, Any]]:
        if self._trades_provider:
            return self._trades_provider()
        return load_trades_from_django()

    def predict_for_trade_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Inference for advisor layer — ACTIVE model only via PredictionAdapter."""
        from scanner.ai_fusion.prediction_adapter import PredictionAdapter
        result = PredictionAdapter().get_active_prediction(context)
        if not result.get("available"):
            return {
                "available": False,
                "status": "UNAVAILABLE",
                "reason": result.get("reason", "no active model — explicit promotion required"),
            }
        return {**result, "available": True, "status": "ACTIVE"}

    @staticmethod
    def _features_from_context(context: dict[str, Any]) -> dict[str, float]:
        """Build feature vector from knowledge/trade context — pre-decision only."""
        snap = context.get("feature_snapshot") or {}
        reg = snap.get("feature_registry") or {}
        if reg:
            return {k: float((v or {}).get("value", 0.0))
                    for k, v in reg.items() if isinstance(v, dict)}

        trade = context.get("trade") or context.get("recommendation") or {}
        row = _encode_trade_row_from_context(trade, context)
        return row.get("features", {}) if row else {}


def _encode_trade_row_from_context(trade: dict, context: dict) -> dict | None:
    from scanner.tracking import WON
    from .feature_engineering import encode_trade_row_v2
    merged = {
        **trade,
        "score": trade.get("score") or context.get("score") or context.get("final_score"),
        "confidence": trade.get("confidence") or context.get("confidence"),
        "grade": trade.get("grade") or context.get("grade") or context.get("final_grade"),
        "factors": trade.get("factors") or context.get("factors") or [],
        "market": trade.get("market") or context.get("market"),
        "timeframe": trade.get("timeframe") or context.get("timeframe"),
        "side": trade.get("side") or context.get("direction"),
        "feature_snapshot_id": trade.get("feature_snapshot_id") or context.get("feature_snapshot_id"),
        "signal_at": trade.get("signal_at") or context.get("signal_at") or "",
        "status": WON,
        "r_multiple": 0,
    }
    return encode_trade_row_v2(merged)
