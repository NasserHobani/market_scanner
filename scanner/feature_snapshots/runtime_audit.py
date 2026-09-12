# -*- coding: utf-8 -*-
"""Runtime PIT snapshot audit — coverage, provenance, linkage, eligibility."""
from __future__ import annotations

import hashlib
import json
import statistics
import time
from collections import Counter
from typing import Any

from scanner.predictive.dataset_v3 import build_dataset_v3, encode_row_v3
from scanner.predictive.leakage_detector import (
    adversarial_leakage_tests,
    validate_provenance,
    validate_row_features,
)
from scanner.predictive.feature_registry import V3_COLUMNS

from .builder import V3_FEATURE_SPECS
from .config import DEFAULT_RUNTIME_CONFIG, RuntimeSnapshotConfig
from .contract import PointInTimeSnapshot, SnapshotStatus
from .enrichment import FEATURE_CATEGORIES, missing_by_category
from .observability import log_event
from .store import get_by_legacy, iter_snapshots, load_index

# re-export for monitor
from .observability import recent_events

# Feature → specific missing reason for UI/diagnostics
FEATURE_MISSING_REASON: dict[str, str] = {
    "trend_direction": "missing_trend",
    "trend_strength": "missing_trend",
    "higher_timeframe_trend": "missing_trend",
    "multi_timeframe_alignment": "missing_components",
    "rsi": "missing_rsi",
    "momentum_state": "missing_momentum",
    "divergence": "missing_momentum",
    "momentum_strength": "missing_momentum",
    "atr_pct": "missing_atr",
    "atr_percentile": "missing_atr",
    "volatility_regime": "missing_volatility",
    "rvol": "missing_rvol",
    "volume_participation": "missing_volume",
    "volume_trend": "missing_volume",
    "bos_count": "missing_structure",
    "choch_count": "missing_structure",
    "structure_direction": "missing_structure",
    "support_distance": "missing_structure",
    "resistance_distance": "missing_structure",
    "match_count": "missing_similarity",
    "similarity_score": "missing_similarity",
    "historical_win_rate": "missing_similarity",
    "historical_expectancy": "missing_similarity",
    "knowledge_score": "missing_knowledge",
    "detected_pattern_count": "missing_knowledge",
    "regime": "missing_knowledge",
    "knowledge_confidence": "missing_knowledge",
    "research_signal": "missing_research",
    "research_confidence": "missing_research",
    "research_sample_size": "missing_research",
    "score": "missing_platform_score",
    "confidence": "missing_recommendation",
    "grade_enc": "missing_recommendation",
    "risk_reward": "missing_recommendation",
    "expected_r": "missing_recommendation",
    "side_buy": "missing_recommendation",
}

SIMILARITY_FEATURES = frozenset({
    "match_count", "similarity_score", "historical_win_rate", "historical_expectancy",
})
STRUCTURE_FEATURES = frozenset({
    "bos_count", "choch_count", "structure_direction", "support_distance", "resistance_distance",
})
RESEARCH_FEATURES = frozenset({"research_signal", "research_confidence", "research_sample_size"})


def make_recommendation_id(*, legacy_snapshot_id: str, symbol: str = "",
                         market: str = "", timeframe: str = "",
                         candle_time: str = "") -> str:
    """Stable 1:1 recommendation key — one ScanResult reco per fs_* snapshot."""
    if legacy_snapshot_id:
        return f"reco_{legacy_snapshot_id}"
    payload = f"{market}|{symbol}|{timeframe}|{candle_time}"
    digest = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return f"reco_{digest}"


def snapshot_content_hash(snap: PointInTimeSnapshot | dict[str, Any]) -> str:
    row = snap.to_dict() if isinstance(snap, PointInTimeSnapshot) else snap
    core = {
        "snapshot_id": row.get("snapshot_id"),
        "features": row.get("features"),
        "provenance": row.get("provenance"),
        "decision_timestamp": row.get("decision_timestamp"),
        "feature_timestamp": row.get("feature_timestamp"),
    }
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode(),
    ).hexdigest()[:24]


def analyze_feature_coverage(snap: PointInTimeSnapshot | dict[str, Any],
                             *,
                             total_features: int | None = None) -> dict[str, Any]:
    row = snap.to_dict() if isinstance(snap, PointInTimeSnapshot) else snap
    feats = row.get("features") or {}
    spec_names = [n for n, _, _ in V3_FEATURE_SPECS]
    total = total_features or len(spec_names) or DEFAULT_RUNTIME_CONFIG.total_v3_features
    available = [n for n in spec_names if n in feats and feats[n] is not None]
    missing = [n for n in spec_names if n not in available]
    coverage_pct = round(len(available) / total * 100, 2) if total else 0.0
    missing_reasons = sorted({FEATURE_MISSING_REASON.get(m, f"missing_{m}") for m in missing})
    return {
        "total_features": total,
        "available_features": len(available),
        "missing_features": missing,
        "missing_count": len(missing),
        "missing_by_category": missing_by_category(missing),
        "coverage": round(len(available) / total, 4) if total else 0.0,
        "coverage_pct": coverage_pct,
        "missing_reasons": missing_reasons,
        "available_list": available,
    }


def validate_snapshot_provenance(snap: PointInTimeSnapshot | dict[str, Any]) -> dict[str, Any]:
    row = snap.to_dict() if isinstance(snap, PointInTimeSnapshot) else snap
    decision_ts = str(row.get("decision_timestamp") or "")
    prov = row.get("provenance") or []
    violations = validate_provenance(prov, decision_ts=decision_ts)
    populated = {p.get("name") for p in prov if isinstance(p, dict)}
    feats = set((row.get("features") or {}).keys())
    missing_prov = sorted(feats - populated)
    for name in missing_prov:
        violations.append(f"missing provenance for {name}")
    invalid = []
    for p in prov:
        if not isinstance(p, dict):
            continue
        if not p.get("source"):
            invalid.append(f"unknown source for {p.get('name')}")
        if not p.get("calculation_version"):
            invalid.append(f"missing calc version for {p.get('name')}")
    return {
        "valid": len(violations) == 0 and len(invalid) == 0,
        "violations": violations + invalid,
        "provenance_count": len(prov),
        "feature_count": len(feats),
    }


def classify_runtime_quality(
    snap: PointInTimeSnapshot | dict[str, Any],
    *,
    config: RuntimeSnapshotConfig = DEFAULT_RUNTIME_CONFIG,
) -> dict[str, Any]:
    row = snap.to_dict() if isinstance(snap, PointInTimeSnapshot) else snap
    cov = analyze_feature_coverage(row, total_features=config.total_v3_features)
    prov = validate_snapshot_provenance(row)
    leakage_violations: list[str] = []
    if row.get("features"):
        leakage_violations = validate_row_features(
            row, feature_columns=V3_COLUMNS, decision_ts=row.get("decision_timestamp", ""),
        )
        leakage_violations.extend(prov["violations"])

    failure_reasons: list[str] = list(cov.get("missing_reasons") or [])
    if not (row.get("components") or row.get("context")):
        if "missing_components" not in failure_reasons:
            failure_reasons.append("missing_components")
    missing_set = set(cov.get("missing_features") or [])
    if missing_set & SIMILARITY_FEATURES == SIMILARITY_FEATURES:
        failure_reasons.append("missing_similarity")
    if missing_set & STRUCTURE_FEATURES == STRUCTURE_FEATURES:
        failure_reasons.append("missing_structure")
    if missing_set & RESEARCH_FEATURES == RESEARCH_FEATURES:
        failure_reasons.append("missing_research")

    coverage = cov["coverage"]
    rating = "FAILED"
    if leakage_violations or not prov["valid"]:
        rating = "FAILED"
        failure_reasons.append("invalid_provenance" if not prov["valid"] else "leakage_detected")
    elif coverage >= config.good_coverage_min and prov["valid"]:
        rating = "GOOD"
    elif coverage >= config.partial_coverage_min and prov["valid"]:
        rating = "PARTIAL"
    else:
        rating = "FAILED"
        if coverage < config.partial_coverage_min:
            failure_reasons.append("low_coverage")

    return {
        "runtime_quality": rating,
        "coverage": coverage,
        "coverage_pct": cov["coverage_pct"],
        "missing_features": cov["missing_features"],
        "missing_by_category": cov.get("missing_by_category") or {},
        "missing_reasons": sorted(set(failure_reasons)),
        "provenance_valid": prov["valid"],
        "leakage_violations": leakage_violations,
        "leakage_pass": len(leakage_violations) == 0,
    }


def enrich_snapshot_audit(snap: PointInTimeSnapshot,
                          *,
                          config: RuntimeSnapshotConfig = DEFAULT_RUNTIME_CONFIG) -> PointInTimeSnapshot:
    audit = classify_runtime_quality(snap, config=config)
    snap.missing_features = audit["missing_features"]
    snap.failure_reasons = audit["missing_reasons"]
    snap.runtime_quality = audit["runtime_quality"]
    if not snap.missing_by_category:
        snap.missing_by_category = audit.get("missing_by_category") or missing_by_category(
            snap.missing_features,
        )
    if audit["runtime_quality"] == "FAILED":
        snap.quality_status = "FAILED"
        snap.status = SnapshotStatus.FAILED.value if snap.status == SnapshotStatus.CREATED.value else snap.status
    elif audit["runtime_quality"] == "PARTIAL":
        snap.quality_status = "PARTIAL"
        if snap.status == SnapshotStatus.CREATED.value:
            snap.status = SnapshotStatus.PARTIAL.value
    else:
        snap.quality_status = "GOOD"
    if audit["leakage_violations"]:
        log_event(
            "LEAKAGE_DETECTED",
            symbol=snap.symbol,
            timeframe=snap.timeframe,
            snapshot_id=snap.snapshot_id,
            reason=";".join(audit["leakage_violations"][:3]),
        )
        snap.failure_reason = ";".join(audit["leakage_violations"][:3])
        snap.runtime_quality = "FAILED"
        snap.quality_status = "FAILED"
    return snap


def audit_linkage(*, scan_results: list[dict[str, Any]] | None = None,
                  trades: list[dict[str, Any]] | None = None,
                  snapshots: list[PointInTimeSnapshot] | None = None) -> dict[str, Any]:
    scan_results = scan_results or []
    trades = trades or []
    snapshots = snapshots if snapshots is not None else iter_snapshots()
    idx = load_index()
    by_legacy = idx.get("by_legacy") or {}

    reco_ids = set()
    for sr in scan_results:
        fs_id = sr.get("feature_snapshot_id") or ""
        if fs_id:
            reco_ids.add(make_recommendation_id(legacy_snapshot_id=fs_id))

    snap_by_reco: dict[str, str] = {}
    orphan_snaps: list[str] = []
    for snap in snapshots:
        if snap.status == SnapshotStatus.HISTORICAL_RECONSTRUCTED.value:
            continue
        rid = snap.recommendation_id or snap.legacy_snapshot_id
        if rid:
            snap_by_reco[rid] = snap.snapshot_id
        elif snap.legacy_snapshot_id and snap.legacy_snapshot_id not in by_legacy.values():
            pass
        if snap.legacy_snapshot_id and snap.legacy_snapshot_id not in {
            sr.get("feature_snapshot_id") for sr in scan_results if sr.get("feature_snapshot_id")
        } and not trades:
            # runtime-only snapshots without scan context — not orphan if has legacy link
            if not snap.legacy_snapshot_id:
                orphan_snaps.append(snap.snapshot_id)

    missing_pit: list[str] = []
    for sr in scan_results:
        fs_id = sr.get("feature_snapshot_id") or ""
        if fs_id and fs_id not in by_legacy:
            missing_pit.append(fs_id)

    trade_linked = 0
    trade_missing_snap = 0
    for t in trades:
        fs_id = t.get("feature_snapshot_id") or ""
        if not fs_id:
            trade_missing_snap += 1
            continue
        if get_by_legacy(fs_id):
            trade_linked += 1
        else:
            trade_missing_snap += 1

    return {
        "recommendations": len(reco_ids),
        "snapshots": len([s for s in snapshots
                          if s.status != SnapshotStatus.HISTORICAL_RECONSTRUCTED.value]),
        "orphan_snapshots": orphan_snaps,
        "orphan_count": len(orphan_snaps),
        "missing_pit_for_scan": missing_pit,
        "missing_snapshot_count": len(missing_pit),
        "snapshot_linked_trades": trade_linked,
        "trades_missing_snapshot": trade_missing_snap,
        "one_to_one": "recommendation_id = reco_{fs_*} — one ScanResult snapshot per recommendation",
    }


def latency_stats_from_events(limit: int = 500) -> dict[str, Any]:
    events = recent_events(limit)
    started: dict[str, float] = {}
    latencies: list[float] = []
    for ev in events:
        eid = ev.get("snapshot_id") or f"{ev.get('symbol')}_{ev.get('recommendation_id')}"
        if ev.get("event") == "SNAPSHOT_STARTED":
            try:
                started[eid] = time.time()
            except Exception:  # noqa: BLE001
                pass
        elif ev.get("event") in ("SNAPSHOT_CREATED", "SNAPSHOT_PARTIAL", "SNAPSHOT_FAILED"):
            sid = ev.get("snapshot_id") or eid
            ms = ev.get("latency_ms")
            if ms is not None:
                latencies.append(float(ms))
            elif sid in started:
                latencies.append((time.time() - started[sid]) * 1000)
    if not latencies:
        for ev in events:
            if ev.get("latency_ms") is not None:
                latencies.append(float(ev["latency_ms"]))
    if not latencies:
        return {"count": 0, "average_ms": None, "p50_ms": None, "p95_ms": None, "max_ms": None}
    latencies.sort()
    n = len(latencies)
    p50 = latencies[int(n * 0.5)]
    p95 = latencies[min(n - 1, int(n * 0.95))]
    return {
        "count": n,
        "average_ms": round(statistics.mean(latencies), 2),
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "max_ms": round(max(latencies), 2),
    }


def dataset_eligibility_report(trades: list[dict[str, Any]], *,
                               reconstruct: bool = False) -> dict[str, Any]:
    manifest = build_dataset_v3(trades, reconstruct=reconstruct, validate_leakage=True)
    reasons = Counter()
    if isinstance(manifest.get("rejection_reasons"), dict):
        reasons = Counter(manifest["rejection_reasons"])

    closed = len(trades)
    linked = sum(1 for t in trades if t.get("feature_snapshot_id"))
    return {
        "total_trades": closed,
        "snapshot_linked": linked,
        "eligible": manifest.get("eligible_count", 0),
        "rejected": manifest.get("rejected_count", 0),
        "rejection_reasons": dict(reasons),
        "v3_smoke_ready": manifest.get("eligible_count", 0) >= DEFAULT_RUNTIME_CONFIG.v3_smoke_min_rows,
        "v3_train_ready": manifest.get("eligible_count", 0) >= DEFAULT_RUNTIME_CONFIG.v3_train_min_rows,
        "dataset_id": manifest.get("dataset_id"),
    }


def enrichment_runtime_report(snapshots: list[PointInTimeSnapshot] | None = None) -> dict[str, Any]:
    """Aggregate AIA-10.6 enrichment metrics from persisted snapshots."""
    snapshots = snapshots if snapshots is not None else [
        s for s in iter_snapshots()
        if s.status != SnapshotStatus.HISTORICAL_RECONSTRUCTED.value
    ]
    if not snapshots:
        return {
            "snapshot_count": 0,
            "coverage_before_avg": 0.0,
            "coverage_after_avg": 0.0,
            "coverage_delta_avg": 0.0,
            "missing_by_category_totals": {cat: 0 for cat in FEATURE_CATEGORIES},
        }

    before_vals: list[float] = []
    after_vals: list[float] = []
    cat_totals: Counter = Counter()
    prov_ok = 0
    leakage_ok = 0
    latencies: list[float] = []
    quality = Counter()

    for snap in snapshots:
        meta = snap.enrichment_meta or {}
        if meta.get("coverage_before") is not None:
            before_vals.append(float(meta["coverage_before"]))
        if meta.get("coverage_after") is not None:
            after_vals.append(float(meta["coverage_after"]))
        for cat, count in (snap.missing_by_category or meta.get("missing_by_category") or {}).items():
            cat_totals[cat] += int(count)
        audit = classify_runtime_quality(snap)
        quality[audit["runtime_quality"]] += 1
        if audit.get("provenance_valid"):
            prov_ok += 1
        if audit.get("leakage_pass"):
            leakage_ok += 1
        if snap.capture_latency_ms:
            latencies.append(float(snap.capture_latency_ms))

    latencies.sort()
    n = len(snapshots)
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None

    return {
        "snapshot_count": n,
        "coverage_before_avg": round(statistics.mean(before_vals) * 100, 2) if before_vals else None,
        "coverage_after_avg": round(statistics.mean(after_vals) * 100, 2) if after_vals else None,
        "coverage_delta_avg": round(
            (statistics.mean(after_vals) - statistics.mean(before_vals)) * 100, 2,
        ) if before_vals and after_vals else None,
        "average_coverage_pct": round(statistics.mean([s.coverage for s in snapshots]) * 100, 2),
        "quality": dict(quality),
        "missing_by_category_totals": dict(cat_totals),
        "provenance_pass": prov_ok == n,
        "leakage_pass": leakage_ok == n,
        "latency_avg_ms": round(statistics.mean(latencies), 2) if latencies else None,
        "latency_p95_ms": round(p95, 2) if p95 is not None else None,
    }


def full_runtime_report(*, scan_results: list[dict[str, Any]] | None = None,
                        trades: list[dict[str, Any]] | None = None,
                        config: RuntimeSnapshotConfig = DEFAULT_RUNTIME_CONFIG) -> dict[str, Any]:
    from .coverage import coverage_report

    snapshots = [
        s for s in iter_snapshots()
        if s.status != SnapshotStatus.HISTORICAL_RECONSTRUCTED.value
    ]
    audits = [classify_runtime_quality(s, config=config) for s in snapshots]
    quality_counts = Counter(a["runtime_quality"] for a in audits)
    avg_cov = round(statistics.mean([a["coverage_pct"] for a in audits]), 2) if audits else 0.0
    all_missing = Counter()
    for a in audits:
        for r in a.get("missing_reasons") or []:
            all_missing[r] += 1

    leakage_events = [
        e for e in recent_events(200)
        if e.get("event") == "LEAKAGE_DETECTED" or "leakage" in str(e.get("reason", "")).lower()
    ]
    linkage = audit_linkage(scan_results=scan_results, trades=trades, snapshots=snapshots)
    hist_cov = coverage_report(closed_trades=trades or []).get("historical", {})
    runtime_cov = coverage_report(closed_trades=trades or []).get("runtime", {})
    eligibility = dataset_eligibility_report(trades or [], reconstruct=False)
    latency = latency_stats_from_events()
    enrichment = enrichment_runtime_report(snapshots)

    status = _overall_status(
        runtime_cov=runtime_cov,
        leakage_events=leakage_events,
        linkage=linkage,
        audits=audits,
        config=config,
    )

    return {
        "status": status,
        "runtime_snapshot_count": len(snapshots),
        "historical_coverage_pct": hist_cov.get("coverage_pct", 0),
        "runtime_coverage_pct": runtime_cov.get("coverage_pct", 0),
        "average_feature_coverage_pct": avg_cov,
        "quality": dict(quality_counts),
        "missing_feature_reasons": dict(all_missing.most_common(20)),
        "leakage_events": len(leakage_events),
        "leakage_pass": len(leakage_events) == 0 and all(a["leakage_pass"] for a in audits),
        "linkage": linkage,
        "latency": latency,
        "enrichment": enrichment,
        "dataset_eligibility": eligibility,
        "snapshots_sample": [
            {
                "snapshot_id": s.snapshot_id,
                "symbol": s.symbol,
                "recommendation_id": s.recommendation_id,
                "runtime_quality": classify_runtime_quality(s)["runtime_quality"],
                "coverage_pct": classify_runtime_quality(s)["coverage_pct"],
                "missing_reasons": classify_runtime_quality(s)["missing_reasons"][:5],
            }
            for s in snapshots[-10:]
        ],
    }


def _overall_status(*, runtime_cov: dict, leakage_events: list,
                    linkage: dict, audits: list[dict],
                    config: RuntimeSnapshotConfig) -> str:
    if leakage_events or any(not a.get("leakage_pass", True) for a in audits):
        return "FAIL"
    if any(not a.get("provenance_valid", True) for a in audits):
        return "FAIL"
    if linkage.get("orphan_count", 0) > 0 and linkage.get("recommendations", 0) > 0:
        return "WARNING"
    rt_pct = runtime_cov.get("coverage_pct", 0) / 100.0
    if rt_pct >= config.runtime_coverage_target and linkage.get("missing_snapshot_count", 0) == 0:
        return "PASS"
    if runtime_cov.get("total_attempts", 0) == 0:
        return "WARNING"
    partial = sum(1 for a in audits if a.get("runtime_quality") == "PARTIAL")
    if rt_pct < config.runtime_coverage_target or partial > 0:
        return "WARNING"
    return "PASS"


def verify_udp_snapshot(package_dict: dict[str, Any]) -> dict[str, Any]:
    fs = package_dict.get("feature_snapshot") or {}
    blob = json.dumps(package_dict).lower()
    categories = ["trend", "momentum", "volatility", "volume", "structure", "similarity", "knowledge"]
    summary = fs.get("summary") or {}
    return {
        "available": fs.get("available") is True,
        "has_snapshot_id": bool(fs.get("snapshot_id")),
        "feature_count": fs.get("feature_count"),
        "no_ohlc": not any(k in blob for k in ("ohlc", "candles", "dataframe", '"open"', '"high"', '"low"')),
        "summary_categories": [c for c in categories if c in json.dumps(summary).lower()],
        "evidence_id": fs.get("evidence_id"),
    }
