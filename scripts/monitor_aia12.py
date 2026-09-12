# -*- coding: utf-8 -*-
"""AIA-12 monitoring — accumulation / readiness / prediction lifecycle."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    print("AIA-12 STATUS")
    print("=" * 48)

    # Market data
    md = "UNKNOWN"
    try:
        from scanner.market_sync.service import get_service
        st = get_service().global_status()
        md = st.get("overall_freshness") or st.get("status") or st.get("freshness") or "UNKNOWN"
        if isinstance(md, dict):
            md = md.get("status") or str(md)
    except Exception:
        md = "UNAVAILABLE"
    print(f"Market data:\n  {md}")

    # PIT + readiness
    try:
        from scanner.predictive.dataset_readiness import build_readiness
        r = build_readiness(persist=True)
    except Exception as exc:
        print(f"Readiness error: {exc}")
        return 1

    rt = r.get("runtime") or {}
    print("PIT:")
    print(f"  TOTAL:   {r.get('runtime_snapshot_count', 0) + (r.get('legacy') or {}).get('legacy_total', 0)}")
    print(f"  GOOD:    {r.get('good_snapshot_count')}")
    print(f"  PARTIAL: {r.get('partial_snapshot_count')}")
    print(f"  FAILED:  {r.get('failed_snapshot_count')}")
    print(f"Runtime coverage:\n  {r.get('runtime_coverage_pct')}%")
    print("V3 eligible:")
    print(f"  {r.get('eligible_rows')} / {r.get('required_rows')}")

    train = r.get("training") or {}
    rs = r.get("retrain_state") or {}
    job = rs.get("job_status") or "IDLE"
    status = train.get("status") or job
    if r.get("ready_for_training") and status == "COLLECTING":
        status = "READY"
    print("Training:")
    print(f"  {status}")

    print("Latest model:")
    print(f"  {r.get('active_model_id') or rs.get('last_dataset_id') or 'NONE'}")

    lr = rs.get("last_result") or {}
    q = "PASS" if lr.get("promotion_status") == "CANDIDATE_FOR_PROMOTION" else (
        "FAIL" if lr else "N/A"
    )
    if rs.get("last_status") == "NOT_PROMOTED":
        q = "FAIL"
    print(f"Quality:\n  {q}")
    print(f"Prediction:\n  {r.get('prediction')}")
    print(f"Fusion:\n  {r.get('fusion')}")

    alerts = r.get("alerts") or []
    if alerts:
        print("Alerts:")
        for a in alerts:
            print(f"  [{a.get('severity')}] {a.get('code')}: {a.get('message')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
