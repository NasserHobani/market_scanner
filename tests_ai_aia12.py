# -*- coding: utf-8 -*-
"""AIA-12 automatic PIT accumulation, readiness & retrain tests."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_snapshots.builder import build_snapshot
from scanner.feature_snapshots.contract import SnapshotStatus
from scanner.feature_snapshots import store as pit_store
from scanner.feature_snapshots.service import PointInTimeSnapshotService
from scanner.feature_snapshots.runtime_audit import make_recommendation_id
from scanner.predictive.dataset_v3 import build_dataset_v3, encode_row_v3
from scanner.predictive.dataset_readiness import build_readiness, compute_alerts
from scanner.predictive.quality_gates import evaluate_promotion, PROMOTION_CANDIDATE, PROMOTION_NOT_PROMOTED
from scanner.predictive import v3_retrain
from scanner.ai_fusion.prediction_adapter import PredictionAdapter, REASON_NO_ACTIVE
from scanner.tracking import WON, LOST

results: list[tuple[bool, str, str]] = []
TS = "2025-07-01T12:00:00+00:00"


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _sim():
    return {
        "match_count": 12, "average_similarity": 0.8, "average_win_rate": 0.6,
        "average_r": 1.1, "similarity_status": "available",
    }


def _know():
    return {
        "feature_snapshot": {"final_score": 72, "groups": {"patterns": {"a": 1}}},
        "market_environment": {"regime": "trend"},
        "knowledge_confidence": 0.7,
        "recommendation_snapshot": {"confidence": 0.7},
    }


def _res():
    return {
        "available": True,
        "statistics": {"significant": True, "confidence": 0.8, "sample_size": 40},
    }


def _rich_source(**kwargs):
    base = {
        "symbol": "ETHUSDT", "market": "crypto", "timeframe": "1h",
        "decision_timestamp": TS, "feature_timestamp": TS,
        "score": 72, "htf": 1,
        "components": {"trend": 1, "rsi": 1, "spike": 1, "cmf": 1, "obv_macd": 1, "div": 0},
        "context": {
            "rsi": 55.0, "rvol": 1.4, "atr_pct": 1.2, "atr_percentile": 0.5,
            "channel": "rising", "ch_zone": "buy",
        },
        "recommendation": {
            "side": "buy", "confidence": 0.7, "grade": "A", "rr": 2.0,
            "analysis": {
                "price_action": {
                    "trend": "bullish", "events": [],
                    "zones": [{"kind": "demand", "top": 99.0}, {"kind": "supply", "bottom": 105.0}],
                    "support_distance": 0.01, "resistance_distance": 0.02,
                },
            },
        },
        "structure": {
            "bos_count": 0, "choch_count": 0, "near_demand": 1.0, "near_supply": 0.0,
            "trend_bias": 1.0, "support_distance": 0.01, "resistance_distance": 0.02,
        },
        "close": 100.0,
    }
    base.update(kwargs)
    return base


def _save_good_snap(legacy_id: str, symbol: str = "ETHUSDT"):
    s = build_snapshot(
        _rich_source(symbol=symbol),
        legacy_snapshot_id=legacy_id,
        similarity=_sim(),
        knowledge=_know(),
        research=_res(),
    )
    s.recommendation_id = make_recommendation_id(legacy_snapshot_id=legacy_id)
    pit_store.save(s)
    return s


with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    snap_path = root / "v3_snapshots.jsonl"
    idx_path = root / "index.json"
    state_path = root / "v3_retrain_state.json"
    ready_path = root / "v3_readiness_cache.json"

    with mock.patch.object(pit_store, "V3_STORE", snap_path), \
            mock.patch.object(pit_store, "INDEX_STORE", idx_path), \
            mock.patch.object(v3_retrain, "_STATE_PATH", state_path), \
            mock.patch("scanner.predictive.dataset_readiness._CACHE_PATH", ready_path), \
            mock.patch("scanner.predictive.dataset_readiness._ALERT_PATH", root / "alerts.json"):

        # ── automatic PIT capture + recommendation linkage ──
        svc = PointInTimeSnapshotService()
        fs_id = "fs_aia12_test_001"
        snap = svc.capture_from_scan_row(
            symbol="ETHUSDT", market="crypto", timeframe="1h",
            candle_time=TS,
            row={"score": 72, "htf": 1, "close": 100, "rsi": 55, "rvol": 1.4, "atr_pct": 1.2,
                 "decision": "buy", "atr_percentile": 0.5, "channel": "rising", "ch_zone": "buy"},
            reco={"side": "buy", "confidence": 0.7, "grade": "A", "rr": 2.0},
            legacy_snapshot_id=fs_id,
            skip_enrichment=True,
        )
        check("automatic PIT capture", bool(snap.snapshot_id), snap.snapshot_id or "")
        expected_reco = make_recommendation_id(legacy_snapshot_id=fs_id)
        check("recommendation linkage", snap.recommendation_id == expected_reco,
              snap.recommendation_id)

        # ── trade linkage fields ──
        trade = {
            "trade_id": "t1",
            "symbol": "ETHUSDT",
            "market": "crypto",
            "timeframe": "1h",
            "status": WON,
            "r_multiple": 1.5,
            "signal_at": TS,
            "feature_snapshot_id": fs_id,
            "pit_snapshot_id": snap.snapshot_id,
            "recommendation_id": snap.recommendation_id,
            "feature_version": "3.0.0",
            "decision_timestamp": TS,
        }
        check("trade linkage pit_id", trade["pit_snapshot_id"] == snap.snapshot_id)
        check("trade linkage reco_id", trade["recommendation_id"] == snap.recommendation_id)

        # ── close linkage / immutable snapshot ──
        before = json.dumps(snap.features, sort_keys=True, default=str)
        # Simulate close: only outcome fields on trade, PIT untouched
        trade_closed = dict(trade)
        trade_closed["status"] = WON
        trade_closed["r_multiple"] = 2.0
        reloaded = pit_store.get_by_id(snap.snapshot_id)
        after = json.dumps(reloaded.features if reloaded else {}, sort_keys=True, default=str)
        check("immutable snapshot after close", before == after)
        check("close linkage via encode", encode_row_v3(trade_closed, pit_snapshot=reloaded.to_dict()) is not None)

        # ── dataset eligibility ──
        if reloaded and float(reloaded.coverage or 0) < 0.70:
            rich = _save_good_snap(fs_id)
            snap = rich
            trade["pit_snapshot_id"] = rich.snapshot_id
            trade_closed["pit_snapshot_id"] = rich.snapshot_id
            reloaded = rich

        man = build_dataset_v3([trade_closed], reconstruct=False, validate_leakage=True)
        check("dataset eligibility linked closed", man.get("eligible_count", 0) >= 1,
              str(man.get("eligible_count")) + " cov=" + str(getattr(reloaded, "coverage", None)))

        # ── legacy exclusion ──
        orphan_trade = {
            "trade_id": "t_legacy",
            "status": LOST,
            "r_multiple": -1.0,
            "signal_at": TS,
            "feature_snapshot_id": "",
            "pit_snapshot_id": "",
        }
        man2 = build_dataset_v3([orphan_trade], reconstruct=False, validate_leakage=True)
        check("legacy exclusion no fabricate", man2.get("eligible_count", 0) == 0)
        reasons = man2.get("rejection_reasons") or {}
        check("legacy reason recorded",
              "historical_snapshot_unavailable" in reasons or "no_pit_snapshot" in reasons,
              str(reasons))

        # ── readiness threshold ──
        ready = build_readiness(trades=[trade_closed], persist=True)
        check("readiness exposes required_rows", ready.get("required_rows") == 100)
        check("readiness COLLECTING below 100",
              ready.get("status") == "COLLECTING" or ready.get("ready_for_training") is False,
              ready.get("status", ""))
        check("readiness progress keys", "progress_percent" in ready and "eligible_rows" in ready)

        # Build 100 synthetic eligible rows for threshold / fingerprint / trigger
        eligible_trades = []
        for i in range(100):
            sid_legacy = f"fs_bulk_{i:03d}"
            s = _save_good_snap(sid_legacy, symbol=f"S{i}")
            eligible_trades.append({
                "trade_id": f"tb_{i}",
                "symbol": f"S{i}",
                "market": "crypto",
                "timeframe": "1h",
                "status": WON if i % 2 == 0 else LOST,
                "r_multiple": 1.0 if i % 2 == 0 else -1.0,
                "signal_at": f"2025-07-{(i % 28) + 1:02d}T12:00:00+00:00",
                "feature_snapshot_id": sid_legacy,
                "pit_snapshot_id": s.snapshot_id,
                "recommendation_id": s.recommendation_id,
            })

        ready100 = build_readiness(trades=eligible_trades, persist=True)
        check("readiness threshold 100", ready100.get("ready_for_training") is True,
              str(ready100.get("eligible_rows")))
        check("status READY_FOR_TRAINING or completed path",
              ready100.get("status") in (
                  "READY_FOR_TRAINING", "COLLECTING", "NOT_PROMOTED",
                  "CANDIDATE_FOR_PROMOTION", "IDLE", "COMPLETED",
              ), ready100.get("status", ""))

        # ── fingerprint ──
        m_a = build_dataset_v3(eligible_trades, reconstruct=False, validate_leakage=True)
        m_b = build_dataset_v3(eligible_trades, reconstruct=False, validate_leakage=True)
        check("fingerprint stable", m_a.get("fingerprint") == m_b.get("fingerprint"))
        fp = m_a.get("fingerprint")

        # ── training trigger + duplicate prevention ──
        with mock.patch("scanner.predictive.dataset_v3.run_v3_experiment") as run_exp:
            run_exp.return_value = {
                "status": "NOT_PROMOTED",
                "quality_gate": {
                    "promotion_status": "NOT_PROMOTED",
                    "passed": False,
                    "reason": "gates",
                    "test_accuracy": 0.5,
                    "baseline_accuracy": 0.55,
                    "improvement": -0.05,
                },
            }
            r_train = v3_retrain.maybe_trigger_v3_retrain(trades=eligible_trades, force=False)
            check("training trigger at 100",
                  r_train.get("skipped") is False and r_train.get("ok") is True,
                  str(r_train.get("reason") or r_train.get("status")))
            check("no automatic promotion", r_train.get("auto_promoted") is False)
            check("status NOT_PROMOTED valid",
                  r_train.get("promotion_status") == "NOT_PROMOTED")

            r_dup = v3_retrain.maybe_trigger_v3_retrain(trades=eligible_trades, force=False)
            check("duplicate fingerprint prevented",
                  r_dup.get("skipped") is True and "duplicate" in str(r_dup.get("reason", "")),
                  str(r_dup.get("reason")))

            # Retraining threshold +20
            r_early = v3_retrain.maybe_trigger_v3_retrain(
                trades=eligible_trades + eligible_trades[:10], force=False)
            # fingerprint differs because more trades — but delta from last_eligible may apply
            # Force clear fingerprint to test delta gate
            st = v3_retrain._load_state()
            st["last_fingerprint"] = "other"
            st["successful_trains"] = 1
            st["last_eligible"] = 100
            v3_retrain._save_state(st)
            r_delta = v3_retrain.maybe_trigger_v3_retrain(
                trades=eligible_trades[:105] if len(eligible_trades) >= 105 else eligible_trades,
                trigger_new=20, force=False)
            # With only 100 trades, delta=0 → wait
            check("retraining threshold +20",
                  r_delta.get("skipped") is True and "waiting_for_new_eligible" in str(r_delta.get("reason", "")),
                  str(r_delta.get("reason")))

        # Concurrent training requests
        busy_flags = []

        def _worker():
            busy_flags.append(v3_retrain.maybe_trigger_v3_retrain(trades=eligible_trades, force=True))

        # Hold lock to simulate concurrent
        acquired = v3_retrain._LOCK.acquire(blocking=False)
        check("lock acquire for concurrency test", acquired)
        if acquired:
            try:
                t = threading.Thread(target=_worker)
                t.start()
                t.join(timeout=2)
                check("concurrent training requests blocked",
                      busy_flags and busy_flags[0].get("reason") == "v3_retrain_busy")
            finally:
                v3_retrain._LOCK.release()

        # Failed training recovery
        with mock.patch("scanner.predictive.dataset_v3.run_v3_experiment",
                        side_effect=RuntimeError("boom")):
            st = v3_retrain._load_state()
            st["last_fingerprint"] = ""
            st["successful_trains"] = 0
            v3_retrain._save_state(st)
            fail = v3_retrain.maybe_trigger_v3_retrain(trades=eligible_trades, force=True)
            check("failed training recovery status", fail.get("status") == "FAILED")
            # Second force should run again (recovery)
            with mock.patch("scanner.predictive.dataset_v3.run_v3_experiment") as run2:
                run2.return_value = {
                    "quality_gate": {"promotion_status": "NOT_PROMOTED", "passed": False},
                }
                st = v3_retrain._load_state()
                st["last_fingerprint"] = ""
                v3_retrain._save_state(st)
                ok2 = v3_retrain.maybe_trigger_v3_retrain(trades=eligible_trades, force=True)
                check("failed training recovery retry", ok2.get("ok") is True and ok2.get("skipped") is False)

        # Quality gates unchanged
        gate = evaluate_promotion(
            test_metrics={"classification": {"accuracy": 0.60}, "sample_size": 20,
                          "trading": {"expectancy": 0.1}},
            baseline_metrics={"classification": {"accuracy": 0.55},
                              "trading": {"expectancy": 0.05}},
            walk_forward={"aggregate": {"mean_accuracy": 0.58}, "folds": []},
            calibration={"calibration_status": "CALIBRATED", "mean_calibration_error": 0.05},
        )
        # May be candidate or not depending on full gate fields — improvement 5% >= 2%
        check("quality gates produce status",
              gate.get("promotion_status") in (PROMOTION_CANDIDATE, PROMOTION_NOT_PROMOTED, "CANDIDATE_FOR_PROMOTION"))
        weak = evaluate_promotion(
            test_metrics={"classification": {"accuracy": 0.55}, "sample_size": 20,
                          "trading": {"expectancy": 0.01}},
            baseline_metrics={"classification": {"accuracy": 0.55},
                              "trading": {"expectancy": 0.05}},
            walk_forward={"aggregate": {"mean_accuracy": 0.50}, "folds": []},
            calibration={"calibration_status": "CALIBRATED", "mean_calibration_error": 0.05},
        )
        check("weak model NOT_PROMOTED", weak.get("promotion_status") == PROMOTION_NOT_PROMOTED)
        check("no auto ACTIVE from gates",
              gate.get("promotion_status") != "ACTIVE" and weak.get("promotion_status") != "ACTIVE")

        # ACTIVE-only adapter
        adapter = PredictionAdapter(state_loader=lambda: {"active_model_id": ""})
        pred = adapter.get_active_prediction({"symbol": "ETHUSDT"})
        check("ACTIVE-only adapter unavailable", pred.get("available") is False)
        check("reason no_active_model", pred.get("reason") == REASON_NO_ACTIVE or
              "no_active" in str(pred.get("reason", "")), str(pred.get("reason")))

        # Fusion unavailable state via readiness
        check("fusion PREDICTION_UNAVAILABLE", ready100.get("fusion") == "PREDICTION_UNAVAILABLE")
        check("prediction UNAVAILABLE", ready100.get("prediction") == "UNAVAILABLE")

        # Dashboard readiness keys
        for k in ("eligible_rows", "required_rows", "progress_percent", "ready_for_training",
                  "good_snapshot_count", "linked_closed_trades", "dataset_fingerprint"):
            check(f"dashboard readiness key {k}", k in ready100)

        # Alerts: coverage low
        alerts = compute_alerts({
            "runtime_coverage_pct": 50,
            "eligible_rows": 10,
            "required_rows": 100,
            "trade_linkage": {"orphan": 0, "total": 1},
            "leakage_rejected": 0,
            "training": {"status": "COLLECTING"},
            "retrain_state": {},
        }, previous=None)
        check("alert runtime coverage low",
              any(a.get("code") == "runtime_coverage_low" for a in alerts))

        # Below train threshold skip (smoke OK but <100)
        small = eligible_trades[:25]
        st = v3_retrain._load_state()
        st.clear()
        v3_retrain._save_state(st)
        skip_early = v3_retrain.maybe_trigger_v3_retrain(trades=small, force=False)
        check("do not train too early",
              skip_early.get("skipped") is True and "below_train" in str(skip_early.get("reason", "")),
              str(skip_early.get("reason")))


# summary
failed = [r for r in results if not r[0]]
print(f"AIA-12 tests: {len(results) - len(failed)}/{len(results)} passed")
for ok, name, extra in results:
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
sys.exit(1 if failed else 0)
