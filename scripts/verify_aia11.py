# -*- coding: utf-8 -*-
"""AIA-11 verification — evidence-only report."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    from scanner.predictive.aia11_reports import build_aia11_bundle, render_all_reports
    from scanner.ai_fusion.prediction_adapter import PredictionAdapter

    bundle = build_aia11_bundle()
    paths = render_all_reports(bundle)

    rt = bundle.get("runtime") or {}
    ds = bundle.get("dataset") or {}
    exp = bundle.get("experiment") or {}
    gate = (exp or {}).get("quality_gate") or {}
    adv = bundle.get("adversarial_leakage") or {}

    try:
        active = PredictionAdapter().get_active_model_id() or ""
    except Exception:
        active = ""

    pred_status = "ACTIVE" if active else "UNAVAILABLE"
    if not active and gate.get("promotion_status") == "CANDIDATE_FOR_PROMOTION":
        pred_status = "CANDIDATE"
    elif not active and isinstance(exp, dict) and exp.get("status") == "INSUFFICIENT_DATA":
        pred_status = "UNAVAILABLE"

    fusion = "AVAILABLE" if active else "PREDICTION_UNAVAILABLE"
    cats = rt.get("categories") or {}
    v3_eval = exp.get("v3_test") or {}
    cls = v3_eval.get("classification") or {}
    naive = (exp.get("naive_baseline") or {}).get("classification") or {}

    print("=" * 50)
    print("AIA-11 VERIFICATION")
    print("=" * 50)
    print(f"\nPIT snapshots:")
    print(f"TOTAL: {rt.get('total')}")
    print(f"GOOD: {rt.get('good')}")
    print(f"PARTIAL: {rt.get('partial')}")
    print(f"FAILED: {rt.get('failed')}")
    print(f"\nRuntime coverage:")
    print(f"OVERALL: {rt.get('overall')}%")
    for k in ("trend", "momentum", "volatility", "volume", "structure",
              "similarity", "knowledge", "research", "platform"):
        print(f"{k.upper()}: {cats.get(k, 0)}%")
    print(f"\nDataset V3:")
    print(f"TOTAL: {ds.get('total_trades')}")
    print(f"ELIGIBLE: {ds.get('eligible')}")
    print(f"REJECTED: {ds.get('rejected')}")
    leak = ds.get("leakage") or {}
    print(f"LEAKAGE: {'PASS' if leak.get('passed', True) else 'FAIL'}")
    print(f"\nModel:")
    print(f"STATUS: {gate.get('promotion_status') or exp.get('status') or 'NOT_RUN'}")
    print(f"MODEL_ID: {active or '-'}")
    print(f"FEATURE_VERSION: {ds.get('feature_version') or '3.0.0'}")
    print(f"OOS: {cls.get('accuracy') if cls else '-'}")
    print(f"BASELINE: {naive.get('accuracy') if naive else '-'}")
    print(f"IMPROVEMENT: {gate.get('improvement', '-')}")
    print(f"WALK_FORWARD: {('PASS' if gate.get('walk_forward_pass') else 'FAIL') if gate else '-'}")
    print(f"CALIBRATION: {(exp.get('calibration') or {}).get('calibration_status', '-')}")
    print(f"EXPECTANCY: {(v3_eval.get('trading') or {}).get('expectancy', '-')}")
    print(f"\nQuality Gate:")
    print("PASS" if gate.get("passed") else "FAIL")
    print(f"\nPrediction:")
    print(pred_status)
    print(f"\nFusion:")
    print(fusion)
    print("=" * 50)
    print("\nReports:")
    for k, p in paths.items():
        print(f"  {k}: {p}")
    if adv:
        print(f"\nAdversarial leakage: {'PASS' if all(adv.values()) else 'FAIL'}")

    # Evidence-based exit: never claim success without data
    if rt.get("total", 0) == 0 and (ds.get("eligible") or 0) == 0:
        print("\nNOTE: No runtime snapshots / eligible rows — coverage claim deferred.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
