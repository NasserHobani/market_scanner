# -*- coding: utf-8 -*-
"""V3 retraining trigger — async, locked, no auto-promotion (AIA-12)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json

log = logging.getLogger("scanner.predictive.v3_retrain")

_LOCK = threading.Lock()
_STATE_PATH = Path("data/predictive/v3_retrain_state.json")

# AIA-12: after a completed evaluation, require +N new eligible rows
_DEFAULT_RETRAIN_DELTA = 20


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict[str, Any]:
    if not _STATE_PATH.exists():
        return {}
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    tmp.replace(_STATE_PATH)


def maybe_trigger_v3_retrain(
    *,
    trades: list[dict[str, Any]] | None = None,
    trigger_new: int = _DEFAULT_RETRAIN_DELTA,
    force: bool = False,
    allow_smoke: bool = False,
) -> dict[str, Any]:
    """Non-blocking V3 evaluate when Dataset readiness threshold is met.

    Rules (AIA-12):
    - Real training threshold: v3_train_min_rows (default 100)
    - Smoke (20) is measurement-only unless allow_smoke=True (manual/dev)
    - After a successful evaluation: retrain only after +trigger_new eligible
      OR feature-version change OR force/manual
    - Fingerprint + lock prevent duplicate identical jobs
    - Never auto-promotes (CANDIDATE / NOT_PROMOTED only)
    """
    if not _LOCK.acquire(blocking=False):
        return {"ok": False, "reason": "v3_retrain_busy", "status": "RUNNING"}

    try:
        from scanner.feature_snapshots.config import DEFAULT_RUNTIME_CONFIG
        from scanner.predictive.dataset_v3 import build_dataset_v3, run_v3_experiment
        from scanner.predictive.feature_registry import FEATURE_VERSION_V3

        if trades is None:
            try:
                from scanner.predictive.trade_dataset import load_trades_from_django
                trades = load_trades_from_django()
            except Exception:
                trades = []

        state = _load_state()
        state["job_status"] = "RUNNING"
        state["job_started_at"] = _utc_now()
        _save_state(state)

        manifest = build_dataset_v3(trades or [], reconstruct=False, validate_leakage=True)
        eligible = int(manifest.get("eligible_count") or 0)
        fingerprint = str(manifest.get("fingerprint") or "")
        feature_version = str(
            (manifest.get("feature_schema") or {}).get("feature_version") or FEATURE_VERSION_V3
        )

        smoke = DEFAULT_RUNTIME_CONFIG.v3_smoke_min_rows
        train = DEFAULT_RUNTIME_CONFIG.v3_train_min_rows
        last_eligible = int(state.get("last_eligible") or 0)
        last_fp = str(state.get("last_fingerprint") or "")
        last_fv = str(state.get("last_feature_version") or "")
        successful_trains = int(state.get("successful_trains") or 0)
        delta = eligible - last_eligible

        def _finish_skip(reason: str, **extra: Any) -> dict[str, Any]:
            state["job_status"] = "IDLE"
            state["job_started_at"] = None
            state["last_skip_reason"] = reason
            _save_state(state)
            out = {"ok": True, "skipped": True, "reason": reason, "eligible": eligible,
                   "status": "IDLE", **extra}
            return out

        if fingerprint and fingerprint == last_fp and not force:
            return _finish_skip("duplicate_fingerprint", fingerprint=fingerprint)

        if eligible < smoke and not force:
            return _finish_skip(f"below_smoke ({eligible}/{smoke})")

        # Expensive train only at real threshold (unless forced / allow_smoke experiment)
        if eligible < train and not force and not allow_smoke:
            return _finish_skip(
                f"below_train_threshold ({eligible}/{train})",
                status="COLLECTING",
            )

        # After at least one completed evaluation: require +N new rows unless FV changed
        fv_changed = bool(last_fv) and last_fv != feature_version
        if successful_trains > 0 and not force and not fv_changed:
            if delta < trigger_new:
                return _finish_skip(
                    f"waiting_for_new_eligible ({delta}/{trigger_new})",
                    status="IDLE",
                )

        result = run_v3_experiment(manifest)
        gate = result.get("quality_gate") or {}
        status = gate.get("promotion_status") or result.get("status") or "NOT_PROMOTED"
        # Normalize lifecycle — never ACTIVE from this path
        if status == "ACTIVE":
            status = "CANDIDATE_FOR_PROMOTION"
        if status not in (
            "NOT_PROMOTED",
            "CANDIDATE_FOR_PROMOTION",
            "TRAINING",
            "FAILED",
            "INSUFFICIENT_DATA",
        ):
            # Keep distinct completed evaluation result
            if str(status).upper() in ("PASS", "PASSED"):
                status = "CANDIDATE_FOR_PROMOTION"
            else:
                status = "NOT_PROMOTED"

        state.update({
            "last_fingerprint": fingerprint,
            "last_eligible": eligible,
            "last_status": status,
            "last_dataset_id": manifest.get("dataset_id"),
            "last_feature_version": feature_version,
            "successful_trains": successful_trains + 1,
            "job_status": "COMPLETED",
            "job_finished_at": _utc_now(),
            "last_result": {
                "promotion_status": status,
                "reason": gate.get("reason"),
                "test_accuracy": gate.get("test_accuracy"),
                "baseline_accuracy": gate.get("baseline_accuracy"),
                "improvement": gate.get("improvement"),
                "walk_forward_pass": gate.get("walk_forward_pass"),
                "calibration_pass": gate.get("calibration_pass"),
                "expectancy_pass": gate.get("expectancy_pass"),
                "leakage_pass": gate.get("leakage_pass"),
                "dataset_quality_pass": gate.get("dataset_quality_pass"),
            },
            "auto_promoted": False,
        })
        # Leave job_status as COMPLETED briefly; next idle callers can reset
        state["job_status"] = "IDLE"
        _save_state(state)
        log.info("V3 retrain evaluated: eligible=%s status=%s", eligible, status)
        return {
            "ok": True,
            "skipped": False,
            "eligible": eligible,
            "promotion_status": status,
            "status": status,
            "auto_promoted": False,
            "fingerprint": fingerprint,
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("V3 retrain failed: %s", str(exc)[:160])
        try:
            state = _load_state()
            state["job_status"] = "FAILED"
            state["last_status"] = "FAILED"
            state["last_error"] = str(exc)[:200]
            state["job_finished_at"] = _utc_now()
            _save_state(state)
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "reason": str(exc)[:200], "status": "FAILED"}
    finally:
        _LOCK.release()


def schedule_v3_retrain_async(**kwargs: Any) -> None:
    """Fire-and-forget — must not block settlement."""
    threading.Thread(
        target=maybe_trigger_v3_retrain,
        kwargs=kwargs,
        name="v3-retrain",
        daemon=True,
    ).start()


def schedule_if_ready_async(**kwargs: Any) -> dict[str, Any]:
    """Check readiness then enqueue — used by scan/settlement hooks."""
    try:
        from scanner.predictive.dataset_readiness import build_readiness
        readiness = build_readiness(persist=True)
        if readiness.get("ready_for_training"):
            schedule_v3_retrain_async(**kwargs)
            return {"scheduled": True, "readiness": readiness}
        return {"scheduled": False, "readiness": readiness}
    except Exception as exc:  # noqa: BLE001
        log.debug("schedule_if_ready: %s", str(exc)[:120])
        return {"scheduled": False, "reason": str(exc)[:160]}
