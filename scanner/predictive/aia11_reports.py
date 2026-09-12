# -*- coding: utf-8 -*-
"""AIA-11 reporting helpers — dataset, leakage, model comparison, quality gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scanner.feature_snapshots.enrichment import FEATURE_CATEGORIES, missing_by_category
from scanner.feature_snapshots.runtime_audit import (
    classify_runtime_quality,
    enrichment_runtime_report,
)
from scanner.feature_snapshots.store import iter_snapshots
from scanner.feature_snapshots.contract import SnapshotStatus
from scanner.predictive.dataset_v3 import build_dataset_v3, run_v3_experiment
from scanner.predictive.feature_quality import (
    analyze_feature_quality,
    dataset_class_balance,
    rejection_breakdown,
)
from scanner.predictive.leakage_detector import adversarial_leakage_tests


REPORT_DIR = Path("scanner")


def write_report(name: str, body: str) -> Path:
    path = REPORT_DIR / name
    path.write_text(body, encoding="utf-8")
    return path


def _j(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def runtime_coverage_summary() -> dict[str, Any]:
    snaps = [
        s for s in iter_snapshots()
        if s.status != SnapshotStatus.HISTORICAL_RECONSTRUCTED.value
    ]
    if not snaps:
        return {"total": 0, "good": 0, "partial": 0, "failed": 0,
                "overall": 0, "median": 0, "p95": 0,
                "categories": {c: 0 for c in FEATURE_CATEGORIES}}

    qualities = [classify_runtime_quality(s) for s in snaps]
    coverages = [q["coverage"] for q in qualities]
    coverages_sorted = sorted(coverages)
    n = len(coverages_sorted)
    cat_cov: dict[str, list[float]] = {c: [] for c in FEATURE_CATEGORIES}
    for s, q in zip(snaps, qualities):
        missing = q.get("missing_features") or s.missing_features or []
        mbc = q.get("missing_by_category") or missing_by_category(missing)
        for cat, names in FEATURE_CATEGORIES.items():
            miss = int(mbc.get(cat, 0))
            avail = max(0, len(names) - miss)
            cat_cov[cat].append(avail / len(names) if names else 0)

    return {
        "total": n,
        "good": sum(1 for q in qualities if q["runtime_quality"] == "GOOD"),
        "partial": sum(1 for q in qualities if q["runtime_quality"] == "PARTIAL"),
        "failed": sum(1 for q in qualities if q["runtime_quality"] == "FAILED"),
        "overall": round(sum(coverages) / n * 100, 2) if n else 0,
        "median": round(coverages_sorted[n // 2] * 100, 2) if n else 0,
        "p95": round(coverages_sorted[min(n - 1, int(n * 0.95))] * 100, 2) if n else 0,
        "categories": {
            c: round(sum(v) / len(v) * 100, 2) if v else 0
            for c, v in cat_cov.items()
        },
        "enrichment": enrichment_runtime_report(snaps),
    }


def build_aia11_bundle(trades: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    trades = trades or []
    try:
        from scanner.predictive.trade_dataset import load_trades_from_django
        if not trades:
            trades = load_trades_from_django()
    except Exception:
        pass

    closed = [
        t for t in trades
        if str(t.get("status", "")).lower() in ("won", "lost")
    ]
    manifest = build_dataset_v3(closed, reconstruct=False, validate_leakage=True)
    eligible = manifest.get("eligible_count", 0)
    rows = list(manifest.get("rows") or [])

    fq = analyze_feature_quality(rows)
    balance = dataset_class_balance(rows)
    reject_reasons = manifest.get("rejection_reasons") or {}

    adv: dict[str, bool] = {}
    if rows:
        adv = adversarial_leakage_tests(rows[0])

    experiment = None
    if eligible >= 20:
        try:
            experiment = run_v3_experiment(manifest)
        except Exception as exc:  # noqa: BLE001
            experiment = {"error": str(exc)[:200], "promotion_status": "NOT_PROMOTED"}

    runtime = runtime_coverage_summary()
    return {
        "runtime": runtime,
        "dataset": {
            "total_trades": len(closed),
            "eligible": eligible,
            "rejected": manifest.get("rejected_count", 0),
            "rejection_reasons": reject_reasons,
            "class_balance": balance,
            "leakage": manifest.get("leakage_validation") or manifest.get("leakage") or {},
            "dataset_id": manifest.get("dataset_id"),
            "feature_version": (manifest.get("feature_schema") or {}).get("feature_version")
            or manifest.get("dataset_version"),
        },
        "feature_quality": fq,
        "adversarial_leakage": adv,
        "experiment": experiment,
    }


def render_all_reports(bundle: dict[str, Any]) -> dict[str, str]:
    rt = bundle.get("runtime") or {}
    ds = bundle.get("dataset") or {}
    fq = bundle.get("feature_quality") or {}
    adv = bundle.get("adversarial_leakage") or {}
    exp = bundle.get("experiment") or {}
    gate = (exp or {}).get("quality_gate") or {}

    feat_sample = {}
    for i, (k, v) in enumerate((fq.get("features") or {}).items()):
        if i >= 12:
            break
        feat_sample[k] = v

    all_adv_pass = all(adv.values()) if adv else False
    pred_status = "UNAVAILABLE"
    if gate.get("promotion_status") == "CANDIDATE_FOR_PROMOTION":
        pred_status = "CANDIDATE"

    paths = {
        "dataset": str(write_report("AIA-11_DATASET_REPORT.md",
            "# AIA-11 Dataset Report\n\n"
            f"- Total closed trades: {ds.get('total_trades')}\n"
            f"- Eligible rows: {ds.get('eligible')}\n"
            f"- Rejected: {ds.get('rejected')}\n"
            f"- Dataset ID: {ds.get('dataset_id')}\n"
            f"- Feature version: {ds.get('feature_version')}\n\n"
            "## Class balance\n```json\n" + _j(ds.get("class_balance") or {}) + "\n```\n\n"
            "## Rejection reasons\n```json\n" + _j(ds.get("rejection_reasons") or {}) + "\n```\n\n"
            "## Leakage\n```json\n" + _j(ds.get("leakage") or {}) + "\n```\n\n"
            f"## Runtime PIT coverage (separate)\n- Overall: {rt.get('overall')}%\n"
            f"- GOOD/PARTIAL/FAILED: {rt.get('good')}/{rt.get('partial')}/{rt.get('failed')}\n"
        )),
        "feature_quality": str(write_report("AIA-11_FEATURE_QUALITY_REPORT.md",
            "# AIA-11 Feature Quality Report\n\n"
            f"Rows analyzed: {fq.get('rows')}\n\n"
            "## Constant / zero-variance\n" + _j(fq.get("constant_features") or []) + "\n\n"
            "## High missingness\n" + _j(fq.get("high_missing") or []) + "\n\n"
            "## Near-duplicates\n" + _j(fq.get("near_duplicate_pairs") or []) + "\n\n"
            "## Per-feature sample\n```json\n" + _j(feat_sample) + "\n```\n"
        )),
        "leakage": str(write_report("AIA-11_LEAKAGE_REPORT.md",
            "# AIA-11 Leakage Report\n\n"
            "## Dataset leakage\n```json\n" + _j(ds.get("leakage") or {}) + "\n```\n\n"
            "## Adversarial tests\n```json\n" + _j(adv) + "\n```\n\n"
            "Overall adversarial: "
            + ("PASS" if all_adv_pass else ("FAIL" if adv else "SKIPPED")) + "\n"
        )),
        "model": str(write_report("AIA-11_MODEL_COMPARISON.md",
            "# AIA-11 Model Comparison\n\n```json\n"
            + _j(exp or {"status": "not_run", "reason": "insufficient eligible rows"})
            + "\n```\n\nNo automatic ACTIVE promotion.\n"
        )),
        "walk_forward": str(write_report("AIA-11_WALK_FORWARD_REPORT.md",
            "# AIA-11 Walk-Forward Report\n\n```json\n"
            + _j((exp or {}).get("walk_forward") or {"status": "not_available"})
            + "\n```\n"
        )),
        "quality_gate": str(write_report("AIA-11_QUALITY_GATE_REPORT.md",
            "# AIA-11 Quality Gate Report\n\n"
            "Gates preserved (not lowered):\n"
            "- OOS improvement >= 2%\n- Walk-forward PASS\n"
            "- Calibration PASS\n- Expectancy PASS\n- No leakage\n\n"
            "## Result\n```json\n" + _j(gate or {"promotion_status": "NOT_PROMOTED"}) + "\n```\n"
        )),
        "runtime": str(write_report("AIA-11_RUNTIME_VERIFICATION.md",
            "# AIA-11 Runtime Verification\n\n"
            f"- TOTAL: {rt.get('total')}\n- GOOD: {rt.get('good')}\n"
            f"- PARTIAL: {rt.get('partial')}\n- FAILED: {rt.get('failed')}\n"
            f"- OVERALL: {rt.get('overall')}%\n- MEDIAN: {rt.get('median')}%\n"
            f"- P95: {rt.get('p95')}%\n\n## Categories\n```json\n"
            + _j(rt.get("categories") or {}) + "\n```\n"
        )),
        "engineering": str(write_report("AIA-11_ENGINEERING_REPORT.md",
            "# AIA-11 Engineering Report\n\n"
            f"## Coverage\n- Runtime overall: {rt.get('overall')}%\n"
            f"- Target: >=80% (prefer >=90%)\n\n"
            f"## Dataset\n- Eligible: {ds.get('eligible')}\n"
            f"- Train gate (>=100): {(ds.get('eligible') or 0) >= 100}\n"
            f"- Smoke (>=20): {(ds.get('eligible') or 0) >= 20}\n\n"
            f"## Prediction\n- Status: {pred_status}\n"
            "- ACTIVE model: NO (explicit promotion only)\n\n"
            "## Remaining blockers\n"
            "1. Accumulate >=100 PIT-linked closed trades with PARTIAL+ coverage\n"
            "2. Re-run verify_aia11.py after enriched live scans\n"
            "3. Explicit promote_model only if CANDIDATE_FOR_PROMOTION\n\n"
            "## Exact next sprint\n"
            "AIA-12 — Runtime coverage accumulation & V3 candidate evaluation "
            "after >=100 eligible rows\n"
        )),
    }
    return paths
