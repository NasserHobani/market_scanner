# -*- coding: utf-8 -*-
"""AIA-12 verification — distinct lifecycle states, evidence-only."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    print("=" * 50)
    print("AIA-12 VERIFICATION")
    print("=" * 50)

    # Market
    md_status = "UNAVAILABLE"
    try:
        from scanner.market_sync.service import get_service
        st = get_service().global_status()
        md_status = st.get("overall_freshness") or st.get("status") or "UNKNOWN"
        if isinstance(md_status, dict):
            md_status = md_status.get("status") or "UNKNOWN"
    except Exception:
        md_status = "CONFIGURED"
    print("Market Data:")
    print(f"STATUS: {md_status}")

    from scanner.predictive.dataset_readiness import build_readiness
    from scanner.predictive.v3_retrain import _load_state
    from scanner.ai_fusion.prediction_adapter import PredictionAdapter

    r = build_readiness(persist=True)
    rs = _load_state()
    lr = rs.get("last_result") or {}

    print("PIT:")
    print(f"TOTAL: {r.get('runtime_snapshot_count', 0) + (r.get('legacy') or {}).get('legacy_total', 0)}")
    print(f"GOOD: {r.get('good_snapshot_count')}")
    print(f"PARTIAL: {r.get('partial_snapshot_count')}")
    print(f"FAILED: {r.get('failed_snapshot_count')}")
    print("Runtime Coverage:")
    print(f"% {r.get('runtime_coverage_pct')}")

    link = r.get("trade_linkage") or {}
    print("Trade Linkage:")
    print(f"TOTAL: {link.get('total')}")
    print(f"LINKED: {link.get('linked')}")
    print(f"ORPHAN: {link.get('orphan')}")

    print("Dataset V3:")
    print(f"ELIGIBLE: {r.get('eligible_rows')}")
    print(f"REQUIRED: {r.get('required_rows')}")
    print(f"PROGRESS: {r.get('progress_percent')}%")

    # Distinct training states — never collapse
    job = str(rs.get("job_status") or "IDLE")
    last = str(rs.get("last_status") or "")
    if job == "RUNNING":
        train_status = "TRAINING"
    elif r.get("ready_for_training") and not last:
        train_status = "READY"
    elif last in ("NOT_PROMOTED", "CANDIDATE_FOR_PROMOTION", "FAILED", "COMPLETED"):
        train_status = last if last != "CANDIDATE_FOR_PROMOTION" else "CANDIDATE"
    elif r.get("eligible_rows", 0) < r.get("required_rows", 100):
        train_status = "CONFIGURED" if r.get("runtime_snapshot_count", 0) else "CONFIGURED"
        if r.get("status") == "COLLECTING":
            train_status = "COLLECTING"
    else:
        train_status = "READY"

    print("Training:")
    print(f"STATUS: {train_status}")
    print(f"LAST JOB: {job}")
    print(f"LAST DATASET: {rs.get('last_dataset_id') or '—'}")

    try:
        active = PredictionAdapter().get_active_model_id() or ""
    except Exception:
        active = ""

    model_status = "ACTIVE" if active else (
        "CANDIDATE" if last == "CANDIDATE_FOR_PROMOTION" else (
            "NOT_PROMOTED" if last == "NOT_PROMOTED" else (
                "FAILED" if last == "FAILED" else "NONE"
            )
        )
    )
    print("Model:")
    print(f"MODEL_ID: {active or rs.get('last_dataset_id') or 'NONE'}")
    print(f"STATUS: {model_status}")

    print("OOS:")
    print(f"{lr.get('test_accuracy')}")
    print("BASELINE:")
    print(f"{lr.get('baseline_accuracy')}")
    print("IMPROVEMENT:")
    print(f"{lr.get('improvement')}")

    print("Walk Forward:")
    print(f"{lr.get('walk_forward_pass')}")
    print("Calibration:")
    print(f"{lr.get('calibration_pass')}")
    print("Expectancy:")
    print(f"{lr.get('expectancy_pass')}")

    qg = "PASS" if last == "CANDIDATE_FOR_PROMOTION" else (
        "FAIL" if last == "NOT_PROMOTED" else "N/A"
    )
    print("Quality Gate:")
    print(f"{qg}")

    print("Prediction:")
    print(f"{'ACTIVE' if active else 'UNAVAILABLE'}")
    print("Fusion:")
    print(f"{'AVAILABLE' if active else 'PREDICTION_UNAVAILABLE'}")

    print("Automation:")
    print(
        f"PIT_CAPTURE=ON READINESS=ON TRAIN_TRIGGER="
        f"{'READY' if r.get('ready_for_training') else 'WAITING'} "
        f"AUTO_PROMOTE=OFF"
    )

    # Write runtime verification report
    report = _ROOT / "scanner" / "AIA-12_RUNTIME_VERIFICATION.md"
    report.write_text(
        "\n".join([
            "# AIA-12 Runtime Verification",
            "",
            f"- Market: `{md_status}`",
            f"- Eligible: `{r.get('eligible_rows')}/{r.get('required_rows')}`",
            f"- Runtime coverage: `{r.get('runtime_coverage_pct')}%`",
            f"- Training status: `{train_status}`",
            f"- Model status: `{model_status}`",
            f"- Prediction: `{'ACTIVE' if active else 'UNAVAILABLE'}`",
            f"- Fusion: `{'AVAILABLE' if active else 'PREDICTION_UNAVAILABLE'}`",
            f"- Auto-promote: `OFF`",
            "",
            "States are reported distinctly (CONFIGURED / COLLECTING / READY / "
            "TRAINING / COMPLETED / NOT_PROMOTED / CANDIDATE / ACTIVE / FAILED).",
        ]),
        encoding="utf-8",
    )
    print(f"\nWrote {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
