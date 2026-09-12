# -*- coding: utf-8 -*-
"""Dataset V3 continuous readiness — AIA-12."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scanner.feature_snapshots.config import DEFAULT_RUNTIME_CONFIG
from scanner.feature_snapshots.contract import SnapshotStatus

log = logging.getLogger("scanner.predictive.dataset_readiness")

_CACHE_PATH = Path("data/predictive/v3_readiness_cache.json")
_ALERT_PATH = Path("data/predictive/v3_readiness_alerts.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    tmp.replace(path)


def _snapshot_partition(snapshots: list[Any]) -> dict[str, Any]:
    """Separate legacy/historical vs runtime metrics — never mix."""
    legacy_total = 0
    legacy_reconstructed = 0
    legacy_unavailable = 0
    runtime_new = 0
    runtime_good = 0
    runtime_partial = 0
    runtime_failed = 0
    coverages: list[float] = []

    hist_statuses = {
        SnapshotStatus.HISTORICAL_RECONSTRUCTED.value,
        SnapshotStatus.HISTORICAL_UNAVAILABLE.value,
    }

    for s in snapshots:
        status = getattr(s, "status", "") or ""
        rq = getattr(s, "runtime_quality", "") or ""
        cov = float(getattr(s, "coverage", 0) or 0)
        if status in hist_statuses:
            legacy_total += 1
            if status == SnapshotStatus.HISTORICAL_RECONSTRUCTED.value:
                legacy_reconstructed += 1
            else:
                legacy_unavailable += 1
            continue
        runtime_new += 1
        coverages.append(cov)
        if rq == "GOOD" or (not rq and cov >= DEFAULT_RUNTIME_CONFIG.good_coverage_min):
            runtime_good += 1
        elif rq == "PARTIAL" or (not rq and cov >= DEFAULT_RUNTIME_CONFIG.partial_coverage_min):
            runtime_partial += 1
        else:
            runtime_failed += 1

    avg_cov = (sum(coverages) / len(coverages)) if coverages else 0.0
    return {
        "legacy_total": legacy_total,
        "legacy_reconstructed": legacy_reconstructed,
        "legacy_unavailable": legacy_unavailable,
        "runtime_new": runtime_new,
        "runtime_good": runtime_good,
        "runtime_partial": runtime_partial,
        "runtime_failed": runtime_failed,
        "runtime_coverage_pct": round(avg_cov * 100, 1),
        "good_snapshot_count": runtime_good,
        "partial_snapshot_count": runtime_partial,
        "failed_snapshot_count": runtime_failed,
        "runtime_snapshot_count": runtime_new,
    }


def _trade_linkage(trades: list[dict[str, Any]]) -> dict[str, Any]:
    from scanner.feature_snapshots.store import get_by_id, get_by_legacy, load_index

    idx = load_index()
    by_legacy = idx.get("by_legacy") or {}
    total = len(trades)
    linked = 0
    orphan = 0
    closed_linked = 0
    for t in trades:
        status = str(t.get("status") or "").lower()
        pit_id = t.get("pit_snapshot_id") or ""
        fs_id = t.get("feature_snapshot_id") or ""
        pit = None
        if pit_id:
            pit = get_by_id(pit_id)
        if not pit and fs_id:
            pit = get_by_legacy(fs_id) or (
                get_by_id(by_legacy[fs_id]) if fs_id in by_legacy else None
            )
        if pit:
            linked += 1
            if status in ("won", "lost"):
                closed_linked += 1
        else:
            orphan += 1
    return {
        "total": total,
        "linked": linked,
        "orphan": orphan,
        "linked_closed_trades": closed_linked,
    }


def _training_status(eligible: int, required: int, retrain_state: dict[str, Any]) -> dict[str, Any]:
    last_status = str(retrain_state.get("last_status") or "")
    job = str(retrain_state.get("job_status") or "IDLE")
    if job == "RUNNING" or last_status == "TRAINING":
        return {"status": "TRAINING", "label_ar": "جاري التدريب", "reason": "training_in_progress"}
    if eligible < required:
        return {
            "status": "COLLECTING",
            "label_ar": "جاري جمع البيانات",
            "reason": f"insufficient_eligible ({eligible}/{required})",
        }
    if not retrain_state.get("last_fingerprint"):
        return {
            "status": "READY_FOR_TRAINING",
            "label_ar": "جاهز للتدريب",
            "reason": "threshold_reached_auto_train",
        }
    if last_status in ("NOT_PROMOTED", "CANDIDATE_FOR_PROMOTION", "COMPLETED"):
        return {
            "status": last_status if last_status != "COMPLETED" else "COMPLETED",
            "label_ar": "اكتمل التقييم" if last_status != "NOT_PROMOTED" else "لم يُرقَّ — بوابة الجودة",
            "reason": last_status,
        }
    if last_status == "FAILED":
        return {"status": "FAILED", "label_ar": "فشل التدريب", "reason": "training_failed"}
    return {
        "status": "READY_FOR_TRAINING",
        "label_ar": "جاهز للتدريب",
        "reason": "eligible_ready",
    }


def compute_alerts(payload: dict[str, Any], *, previous: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Warnings only — NOT_PROMOTED is not an alert."""
    alerts: list[dict[str, Any]] = []
    cov = float(payload.get("runtime_coverage_pct") or 0)
    if cov and cov < 70:
        alerts.append({
            "code": "runtime_coverage_low",
            "severity": "warn",
            "message": f"runtime PIT coverage {cov}% < 70%",
        })
    prev_elig = int((previous or {}).get("eligible_rows") or 0)
    elig = int(payload.get("eligible_rows") or 0)
    stalled_checks = int((previous or {}).get("_stall_checks") or 0)
    if previous and elig == prev_elig and elig < int(payload.get("required_rows") or 100):
        stalled_checks += 1
    else:
        stalled_checks = 0
    payload["_stall_checks"] = stalled_checks
    if stalled_checks >= 5:
        alerts.append({
            "code": "eligible_rows_stalled",
            "severity": "warn",
            "message": f"eligible rows unchanged at {elig} across {stalled_checks} checks",
        })
    linkage = payload.get("trade_linkage") or {}
    orphan = int(linkage.get("orphan") or 0)
    total = max(1, int(linkage.get("total") or 1))
    if orphan / total > 0.25 and total >= 8:
        alerts.append({
            "code": "trade_linkage_failures",
            "severity": "warn",
            "message": f"orphan trades {orphan}/{total}",
        })
    ts = payload.get("training") or {}
    if ts.get("status") == "TRAINING":
        started = str((payload.get("retrain_state") or {}).get("job_started_at") or "")
        if started:
            alerts.append({
                "code": "training_running",
                "severity": "info",
                "message": f"training job running since {started}",
            })
    if payload.get("leakage_rejected", 0) > 0:
        alerts.append({
            "code": "leakage_detected",
            "severity": "critical",
            "message": f"leakage_rejected={payload.get('leakage_rejected')}",
        })
    return alerts


def build_readiness(*, trades: list[dict[str, Any]] | None = None,
                    persist: bool = True) -> dict[str, Any]:
    """Continuously measurable Dataset V3 readiness status."""
    from scanner.feature_snapshots.store import iter_snapshots
    from scanner.predictive.dataset_v3 import build_dataset_v3
    from scanner.predictive.v3_retrain import _load_state

    if trades is None:
        try:
            from scanner.predictive.trade_dataset import load_trades_from_django
            trades = load_trades_from_django()
        except Exception:  # noqa: BLE001
            trades = []

    required = int(DEFAULT_RUNTIME_CONFIG.v3_train_min_rows)
    smoke = int(DEFAULT_RUNTIME_CONFIG.v3_smoke_min_rows)

    snapshots = list(iter_snapshots())
    part = _snapshot_partition(snapshots)
    linkage = _trade_linkage(trades or [])

    manifest = build_dataset_v3(trades or [], reconstruct=False, validate_leakage=True)
    eligible = int(manifest.get("eligible_count") or 0)
    rejected = manifest.get("rejection_reasons") or {}
    leakage_rejected = sum(
        int(v) for k, v in rejected.items() if str(k).startswith("leakage")
    )
    fingerprint = str(manifest.get("fingerprint") or "")

    progress = round(min(100.0, (eligible / required) * 100.0), 1) if required else 0.0
    ready = eligible >= required

    retrain_state = _load_state()
    training = _training_status(eligible, required, retrain_state)

    status = training["status"]
    if ready and status == "COLLECTING":
        status = "READY_FOR_TRAINING"

    reason = training.get("reason") or (
        "ready_for_training" if ready else f"collecting ({eligible}/{required})"
    )

    # Prediction / fusion remain ACTIVE-only — readiness does not invent availability
    try:
        from scanner.ai_fusion.prediction_adapter import PredictionAdapter
        active = PredictionAdapter().get_active_model_id() or ""
    except Exception:  # noqa: BLE001
        active = ""

    prediction = "ACTIVE" if active else "UNAVAILABLE"
    fusion = "AVAILABLE" if active else "PREDICTION_UNAVAILABLE"

    previous = _load_json(_CACHE_PATH)
    payload: dict[str, Any] = {
        "ok": True,
        "eligible_rows": eligible,
        "required_rows": required,
        "smoke_min_rows": smoke,
        "progress_percent": progress,
        "runtime_snapshot_count": part["runtime_snapshot_count"],
        "good_snapshot_count": part["good_snapshot_count"],
        "partial_snapshot_count": part["partial_snapshot_count"],
        "failed_snapshot_count": part["failed_snapshot_count"],
        "runtime_coverage_pct": part["runtime_coverage_pct"],
        "linked_closed_trades": linkage["linked_closed_trades"],
        "leakage_rejected": leakage_rejected,
        "dataset_fingerprint": fingerprint,
        "ready_for_training": ready,
        "reason": reason,
        "status": status,
        "status_ar": training.get("label_ar") or status,
        "legacy": {
            "legacy_total": part["legacy_total"],
            "legacy_reconstructed": part["legacy_reconstructed"],
            "legacy_unavailable": part["legacy_unavailable"],
        },
        "runtime": {
            "runtime_new": part["runtime_new"],
            "runtime_good": part["runtime_good"],
            "runtime_partial": part["runtime_partial"],
            "runtime_failed": part["runtime_failed"],
            "runtime_coverage_pct": part["runtime_coverage_pct"],
        },
        "trade_linkage": linkage,
        "training": training,
        "retrain_state": {
            "last_fingerprint": retrain_state.get("last_fingerprint"),
            "last_eligible": retrain_state.get("last_eligible"),
            "last_status": retrain_state.get("last_status"),
            "last_dataset_id": retrain_state.get("last_dataset_id"),
            "last_result": retrain_state.get("last_result") or {},
            "job_status": retrain_state.get("job_status") or "IDLE",
            "job_started_at": retrain_state.get("job_started_at"),
            "successful_trains": retrain_state.get("successful_trains") or 0,
        },
        "prediction": prediction,
        "prediction_reason": "no_active_model" if not active else "active_model",
        "active_model_id": active or None,
        "fusion": fusion,
        "rejection_reasons": rejected,
        "measured_at": _utc_now(),
    }
    alerts = compute_alerts(payload, previous=previous)
    payload["alerts"] = alerts
    payload["_stall_checks"] = payload.get("_stall_checks", 0)

    if persist:
        cache = dict(payload)
        _save_json(_CACHE_PATH, cache)
        _save_json(_ALERT_PATH, {"alerts": alerts, "measured_at": payload["measured_at"]})

    # Public API shape (stable keys from spec)
    return {
        "eligible_rows": payload["eligible_rows"],
        "required_rows": payload["required_rows"],
        "progress_percent": payload["progress_percent"],
        "runtime_snapshot_count": payload["runtime_snapshot_count"],
        "good_snapshot_count": payload["good_snapshot_count"],
        "partial_snapshot_count": payload["partial_snapshot_count"],
        "failed_snapshot_count": payload["failed_snapshot_count"],
        "linked_closed_trades": payload["linked_closed_trades"],
        "leakage_rejected": payload["leakage_rejected"],
        "dataset_fingerprint": payload["dataset_fingerprint"],
        "ready_for_training": payload["ready_for_training"],
        "reason": payload["reason"],
        "status": payload["status"],
        "status_ar": payload["status_ar"],
        "runtime_coverage_pct": payload["runtime_coverage_pct"],
        "legacy": payload["legacy"],
        "runtime": payload["runtime"],
        "trade_linkage": payload["trade_linkage"],
        "training": payload["training"],
        "retrain_state": payload["retrain_state"],
        "prediction": payload["prediction"],
        "prediction_reason": payload["prediction_reason"],
        "active_model_id": payload["active_model_id"],
        "fusion": payload["fusion"],
        "alerts": alerts,
        "smoke_min_rows": smoke,
        "measured_at": payload["measured_at"],
        "rejection_reasons": rejected,
    }


def get_cached_readiness() -> dict[str, Any]:
    cached = _load_json(_CACHE_PATH)
    if cached.get("eligible_rows") is not None:
        return cached
    return build_readiness(persist=True)
