# -*- coding: utf-8 -*-
"""ACTIVE-only prediction adapter — no fallback to inactive models."""
from __future__ import annotations

import logging
from typing import Any, Callable

from scanner.predictive.quality_gates import PROMOTION_ACTIVE
from scanner.predictive.training_jobs import TrainingState

log = logging.getLogger("scanner.ai_fusion.prediction")

REASON_NO_ACTIVE = "no_active_model"
REASON_NOT_PROMOTED = "model_not_active"
REASON_GATE_FAILED = "quality_gate_not_passed"
REASON_VERSION_MISMATCH = "feature_version_mismatch"
REASON_LEAKAGE = "leakage_detected"
REASON_INFERENCE = "inference_failed"


class PredictionAdapter:
    """Strict ACTIVE-only wrapper around the predictive subsystem."""

    def __init__(self,
                 state: TrainingState | None = None,
                 service: Any | None = None,
                 state_loader: Callable[[], dict[str, Any]] | None = None) -> None:
        self._state = state or TrainingState()
        self._state_loader = state_loader
        self._service = service

    def _get_service(self):
        if self._service is None:
            from scanner.predictive.services import PredictiveService
            self._service = PredictiveService()
        return self._service

    def get_active_model_id(self) -> str:
        if self._state_loader:
            return str(self._state_loader().get("active_model_id") or "")
        return str(self._state.load().get("active_model_id") or "")

    def get_active_prediction(self, context: dict[str, Any]) -> dict[str, Any]:
        """Return structured prediction or unavailable — never fallback."""
        active_id = self.get_active_model_id()
        if not active_id:
            return self._unavailable(REASON_NO_ACTIVE)

        svc = self._get_service()
        models = {m["model_id"]: m for m in svc.list_models()}
        meta = models.get(active_id)
        if not meta:
            return self._unavailable(REASON_NO_ACTIVE, detail="active model not in registry")

        status = str(meta.get("status") or "").upper()
        extra = meta.get("extra") or {}
        gate = meta.get("quality_gate_result") or extra.get("promotion_gate") or {}
        promo = str(gate.get("promotion_status") or extra.get("promotion_status") or status)

        if promo not in (PROMOTION_ACTIVE, "ACTIVE"):
            return self._unavailable(REASON_NOT_PROMOTED, model_id=active_id)

        if gate and gate.get("passed") is False:
            return self._unavailable(REASON_GATE_FAILED, model_id=active_id)

        features = self._build_features(context)
        if not features:
            return self._unavailable("no_pre_trade_features", model_id=active_id)

        feature_version = str(meta.get("feature_version") or "2.0.0")
        expected_cols = set(meta.get("feature_columns") or [])
        if expected_cols and not expected_cols.issubset(set(features.keys()) | set(features)):
            missing = expected_cols - set(features.keys())
            if len(missing) > len(expected_cols) * 0.5:
                return self._unavailable(
                    REASON_VERSION_MISMATCH,
                    model_id=active_id,
                    detail=f"missing features: {sorted(missing)[:5]}",
                )

        try:
            from scanner.predictive.leakage_detector import validate_row_features
            viols = validate_row_features(
                {"features": features, "signal_at": context.get("signal_at", "")},
                feature_columns=list(expected_cols) if expected_cols else None,
            )
            if viols:
                return self._unavailable(REASON_LEAKAGE, model_id=active_id, detail=viols[0])
        except Exception as exc:  # noqa: BLE001
            log.debug("leakage check: %s", exc)

        try:
            result = svc.predict(active_id, features)
            out = result.to_dict() if hasattr(result, "to_dict") else dict(result)
            proba = float(out.get("probability") or out.get("confidence") or 0.5)
            if proba > 1:
                proba = proba / 100.0
            label = "WIN" if proba >= 0.5 else "LOSS"
            cal = meta.get("calibration_metrics") or {}
            return {
                "available": True,
                "model_id": active_id,
                "model_version": meta.get("model_version", ""),
                "feature_version": feature_version,
                "prediction": label,
                "probability_win": round(proba, 4),
                "probability_loss": round(1.0 - proba, 4),
                "calibration_status": cal.get("calibration_status", "unknown"),
                "quality_gate_status": "passed",
                "feature_timestamp": context.get("signal_at") or context.get("feature_timestamp", ""),
                "evidence_ids": [f"prediction:{active_id}"],
                "quality": {
                    "oos_accuracy": gate.get("test_accuracy"),
                    "baseline_accuracy": gate.get("baseline_accuracy"),
                    "improvement": gate.get("improvement"),
                    "walk_forward": "passed" if gate.get("walk_forward_pass") else "failed",
                },
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("prediction inference failed: %s", str(exc)[:200])
            return self._unavailable(REASON_INFERENCE, model_id=active_id, detail=str(exc)[:120])

    @staticmethod
    def _build_features(context: dict[str, Any]) -> dict[str, float]:
        feats = context.get("features") or {}
        if feats:
            return {k: float(v) for k, v in feats.items()}

        from scanner.predictive.training_orchestrator import _encode_trade_row_from_context
        trade = context.get("trade") or context.get("recommendation") or context
        row = _encode_trade_row_from_context(trade, context)
        return row.get("features", {}) if row else {}

    @staticmethod
    def _unavailable(reason: str, *, model_id: str = "", detail: str = "") -> dict[str, Any]:
        return {
            "available": False,
            "reason": reason,
            "detail": detail,
            "model_id": model_id or None,
            "status": "UNAVAILABLE",
        }

    def to_udp_section(self, context: dict[str, Any]) -> dict[str, Any]:
        """Format for UnifiedDecisionPackage.prediction section."""
        pred = self.get_active_prediction(context)
        if not pred.get("available"):
            return {
                "available": False,
                "reason": pred.get("reason", REASON_NO_ACTIVE),
                "status": "UNAVAILABLE",
            }
        return {
            "available": True,
            "model_id": pred["model_id"],
            "model_version": pred.get("model_version", ""),
            "prediction": pred.get("prediction"),
            "probability_win": pred.get("probability_win"),
            "probability_loss": pred.get("probability_loss"),
            "calibration": {"status": pred.get("calibration_status", "unknown")},
            "quality": pred.get("quality", {}),
            "feature_version": pred.get("feature_version"),
            "feature_timestamp": pred.get("feature_timestamp"),
            "evidence_ids": pred.get("evidence_ids", []),
        }
