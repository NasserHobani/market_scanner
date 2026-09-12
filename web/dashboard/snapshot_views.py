# -*- coding: utf-8 -*-
"""Snapshot runtime API — AIA-10.5 dashboard metrics."""
from __future__ import annotations

from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET

from scanner.feature_snapshots.config import DEFAULT_RUNTIME_CONFIG
from scanner.feature_snapshots.runtime_audit import full_runtime_report


def _scan_results() -> list[dict]:
    try:
        from dashboard.models import ScanResult
        qs = ScanResult.objects.exclude(feature_snapshot_id="").order_by("-candle_time")[:300]
        return [
            {
                "symbol": r.symbol,
                "market": r.market,
                "timeframe": r.timeframe,
                "feature_snapshot_id": r.feature_snapshot_id,
                "candle_time": r.candle_time.isoformat() if r.candle_time else "",
            }
            for r in qs
        ]
    except Exception:
        return []


def _trades() -> list[dict]:
    try:
        from scanner.predictive.trade_dataset import load_trades_from_django
        return load_trades_from_django()
    except Exception:
        return []


@require_GET
def api_snapshot_runtime(request):
    report = full_runtime_report(scan_results=_scan_results(), trades=_trades())
    cfg = DEFAULT_RUNTIME_CONFIG
    elig = report.get("dataset_eligibility") or {}
    return JsonResponse({
        "ok": True,
        "status": report.get("status"),
        "runtime_snapshot_coverage": report.get("runtime_coverage_pct"),
        "historical_snapshot_coverage": report.get("historical_coverage_pct"),
        "snapshot_quality": report.get("quality"),
        "average_feature_coverage": report.get("average_feature_coverage_pct"),
        "missing_feature_reasons": report.get("missing_feature_reasons"),
        "failed_snapshots": (report.get("quality") or {}).get("FAILED", 0),
        "orphan_snapshots": (report.get("linkage") or {}).get("orphan_count", 0),
        "pit_leakage_events": report.get("leakage_events", 0),
        "snapshot_linked_closed_trades": (report.get("linkage") or {}).get("snapshot_linked_trades", 0),
        "v3_eligible_trades": elig.get("eligible", 0),
        "v3_smoke_ready": elig.get("v3_smoke_ready", False),
        "v3_train_ready": elig.get("v3_train_ready", False),
        "latency": report.get("latency"),
        "linkage": report.get("linkage"),
        "thresholds": {
            "runtime_coverage_target_pct": cfg.runtime_coverage_target * 100,
            "good_coverage_pct": cfg.good_coverage_min * 100,
            "partial_coverage_pct": cfg.partial_coverage_min * 100,
            "v3_smoke_min_rows": cfg.v3_smoke_min_rows,
            "v3_train_min_rows": cfg.v3_train_min_rows,
        },
        "prediction_note": "UNAVAILABLE until v3_train_ready and quality gates pass",
    })
