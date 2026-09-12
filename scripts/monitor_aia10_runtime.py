# -*- coding: utf-8 -*-
"""AIA-10.5 / AIA-10.6 runtime PIT snapshot monitor."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_scan_results() -> list[dict]:
    try:
        from dashboard.models import ScanResult
        qs = ScanResult.objects.exclude(feature_snapshot_id="").order_by("-candle_time")[:500]
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


def _load_trades() -> list[dict]:
    try:
        from scanner.predictive.trade_dataset import load_trades_from_django
        return load_trades_from_django()
    except Exception:
        return []


def main() -> int:
    from scanner.feature_snapshots.runtime_audit import full_runtime_report

    scan_results = _load_scan_results()
    trades = _load_trades()
    report = full_runtime_report(scan_results=scan_results, trades=trades)

    print("=" * 40)
    print("AIA-10.5 RUNTIME SNAPSHOT MONITOR")
    print("=" * 40)
    linkage = report.get("linkage") or {}
    elig = report.get("dataset_eligibility") or {}
    lat = report.get("latency") or {}
    qual = report.get("quality") or {}
    missing = report.get("missing_feature_reasons") or {}
    enrich = report.get("enrichment") or {}

    print(f"\nRecommendations: {linkage.get('recommendations', 0)}")
    print(f"Snapshots: {report.get('runtime_snapshot_count', 0)}")
    print(f"\nHistorical coverage: {report.get('historical_coverage_pct', 0)}%")
    print(f"Runtime coverage: {report.get('runtime_coverage_pct', 0)}%")
    print(f"\nAverage feature coverage: {report.get('average_feature_coverage_pct', 0)}%")
    print(f"\nGOOD: {qual.get('GOOD', 0)}")
    print(f"PARTIAL: {qual.get('PARTIAL', 0)}")
    print(f"FAILED: {qual.get('FAILED', 0)}")
    print(f"\nMissing features (top reasons):")
    for reason, count in list(missing.items())[:10]:
        print(f"  {reason}: {count}")
    print(f"\nLeakage events: {report.get('leakage_events', 0)}")
    print(f"Orphan snapshots: {linkage.get('orphan_count', 0)}")
    print(f"Snapshot-linked closed trades: {linkage.get('snapshot_linked_trades', 0)}")
    print(f"V3 eligible rows: {elig.get('eligible', 0)}")
    print(f"V3 smoke ready (>=20): {elig.get('v3_smoke_ready', False)}")
    print(f"V3 train ready (>=100): {elig.get('v3_train_ready', False)}")
    if lat.get("count"):
        print(f"\nLatency avg/p50/p95/max (ms): "
              f"{lat.get('average_ms')}/{lat.get('p50_ms')}/{lat.get('p95_ms')}/{lat.get('max_ms')}")
    print(f"\nSTATUS: {report.get('status', 'UNKNOWN')}")

    print("\n" + "=" * 40)
    print("AIA-10.6 FEATURE ENRICHMENT")
    print("=" * 40)
    print(f"\nSnapshots: {enrich.get('snapshot_count', 0)}")
    print(f"\nBefore enrichment coverage: {enrich.get('coverage_before_avg', 'n/a')}%")
    print(f"After enrichment coverage: {enrich.get('coverage_after_avg', 'n/a')}%")
    print(f"Coverage delta: {enrich.get('coverage_delta_avg', 'n/a')}%")
    print(f"\nAverage coverage: {enrich.get('average_coverage_pct', report.get('average_feature_coverage_pct', 0))}%")
    eq = enrich.get("quality") or qual
    print(f"\nGOOD: {eq.get('GOOD', 0)}")
    print(f"PARTIAL: {eq.get('PARTIAL', 0)}")
    print(f"FAILED: {eq.get('FAILED', 0)}")
    cat_totals = enrich.get("missing_by_category_totals") or {}
    print(f"\nMissing trend: {cat_totals.get('trend', 0)}")
    print(f"Missing momentum: {cat_totals.get('momentum', 0)}")
    print(f"Missing volatility: {cat_totals.get('volatility', 0)}")
    print(f"Missing volume: {cat_totals.get('volume', 0)}")
    print(f"Missing structure: {cat_totals.get('structure', 0)}")
    print(f"Missing similarity: {cat_totals.get('similarity', 0)}")
    print(f"Missing knowledge: {cat_totals.get('knowledge', 0)}")
    print(f"Missing research: {cat_totals.get('research', 0)}")
    prov = "PASS" if enrich.get("provenance_pass") else "FAIL"
    leak = "PASS" if enrich.get("leakage_pass") and report.get("leakage_pass") else "FAIL"
    print(f"\nProvenance: {prov}")
    print(f"Leakage: {leak}")
    if enrich.get("latency_avg_ms") is not None:
        print(f"\nAverage latency: {enrich.get('latency_avg_ms')} ms")
        print(f"P95 latency: {enrich.get('latency_p95_ms')} ms")
    print("=" * 40)
    return 0 if report.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
