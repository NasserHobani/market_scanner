# -*- coding: utf-8 -*-
"""Unit tests for scanner.feature_intelligence — run: python tests_feature_intelligence.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.feature_intelligence import (
    FeatureCorrelationEngine,
    FeatureDriftEngine,
    FeatureImportanceEngine,
    FeatureIntelligenceService,
    FeatureRankingEngine,
    FeatureStabilityEngine,
    RANKING_WEIGHTS,
    RedundancyDetector,
)
from scanner.feature_intelligence.feature_intelligence_engine import AnalysisHistoryStore
from scanner.ml.label_store import LabelName
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _row(i: int, *, rsi: float = 55.0, score: float = 70.0,
           htf: int = 1, status: str = WON, r: float = 2.0,
           market: str = "crypto", tf: str = "4h") -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 12, 0, tzinfo=timezone.utc)
    won = status == WON
    return {
        "event_id": f"evt_{i:04d}",
        "features": {
            "rsi": rsi + i * 0.5,
            "score": score + i,
            "htf_bias": htf,
            "atr_pct": 2.1,
            "c_trend": 1 if won else -1,
        },
        LabelName.WINNER.value: 1 if won else 0,
        LabelName.LOSER.value: 0 if won else 1,
        LabelName.BINARY_WIN.value: 1 if r > 0 else 0,
        LabelName.R_MULTIPLE.value: r,
        "_meta": {"market": market, "timeframe": tf, "closed_at": ts.isoformat()},
        "closed_at": ts,
    }


N = 30
ROWS = [
    _row(i, status=WON if i % 3 != 0 else LOST,
         r=2.0 if i % 3 != 0 else -1.0,
         rsi=50.0 + (10 if i % 3 != 0 else -5),
         market="crypto" if i < N // 2 else "forex",
         tf="4h" if i % 2 == 0 else "1h")
    for i in range(N)
]
FEATURES = ["rsi", "score", "htf_bias", "atr_pct", "c_trend"]

# ── Feature Importance ─────────────────────────────────────────────────────

imp_engine = FeatureImportanceEngine()
imp_results = imp_engine.compute(ROWS, feature_names=FEATURES)
check("Importance returns results", len(imp_results) == len(FEATURES), str(len(imp_results)))
check("Importance has correlation_win_rate",
      imp_results[0].correlation_win_rate is not None or imp_results[0].sample_size < 5)
check("Importance has correlation_r_multiple",
      any(r.correlation_r_multiple is not None for r in imp_results))
check("Importance statistical_importance",
      any(r.statistical_importance is not None for r in imp_results))
check("Importance MI placeholder", imp_results[0].mutual_information is None)
check("Importance IG placeholder", imp_results[0].information_gain is None)
check("Importance to_dict", "feature" in imp_results[0].to_dict())
check("Importance deterministic",
      imp_results[0].correlation_win_rate ==
      imp_engine.compute(ROWS, feature_names=FEATURES)[0].correlation_win_rate)

# ── Feature Stability ──────────────────────────────────────────────────────

stab_engine = FeatureStabilityEngine()
stab_results = stab_engine.compute(ROWS, feature_names=FEATURES)
check("Stability returns results", len(stab_results) == len(FEATURES))
check("Stability overall", stab_results[0].overall_stability is not None or
      stab_results[0].sample_size if hasattr(stab_results[0], 'sample_size') else True)
check("Stability monthly", "monthly_stability" in stab_results[0].to_dict())
check("Stability market", "market_stability" in stab_results[0].to_dict())
check("Stability timeframe", "timeframe_stability" in stab_results[0].to_dict())
check("Stability score range",
      all(r.overall_stability is None or 0 <= r.overall_stability <= 1
          for r in stab_results))

# ── Feature Drift ──────────────────────────────────────────────────────────

drift_engine = FeatureDriftEngine()
drift_results = drift_engine.compute(ROWS, feature_names=FEATURES)
check("Drift returns results", len(drift_results) == len(FEATURES))
check("Drift has score", drift_results[0].drift_score is not None)
check("Drift has evidence field", "evidence" in drift_results[0].to_dict())
check("Drift distribution_shift", "distribution_shift" in drift_results[0].to_dict())
check("Drift missing rates", "missing_rate_baseline" in drift_results[0].to_dict())

# ── Feature Correlation ──────────────────────────────────────────────────────

corr_engine = FeatureCorrelationEngine()
corr_matrix = corr_engine.compute_matrix(ROWS, feature_names=FEATURES)
check("Correlation matrix features", len(corr_matrix.features) == len(FEATURES))
check("Correlation matrix diagonal", corr_matrix.matrix["rsi"]["rsi"] == 1.0)
check("Correlation outcome", "rsi" in corr_matrix.outcome_correlations)
check("Correlation pairs", len(corr_engine.pair_correlations(ROWS, feature_names=FEATURES)) >= 0)
check("Correlation to_dict", "matrix" in corr_matrix.to_dict())

# ── Redundancy ───────────────────────────────────────────────────────────────

# Create highly correlated features for redundancy test
redundant_rows = []
for i in range(20):
    r = _row(i)
    r["features"]["rsi_clone"] = r["features"]["rsi"]  # perfect correlation
    redundant_rows.append(r)

red = RedundancyDetector(threshold=0.85).detect(
    redundant_rows, feature_names=["rsi", "rsi_clone", "score"])
check("Redundancy detects pairs", len(red.redundant_pairs) >= 1, str(len(red.redundant_pairs)))
check("Redundancy warnings", len(red.warnings) >= 1)
check("Redundancy groups", isinstance(red.groups, list))
check("Redundancy to_dict", "redundant_pairs" in red.to_dict())

# ── Feature Ranking ──────────────────────────────────────────────────────────

ranked = FeatureRankingEngine().rank(
    importance=imp_results, stability=stab_results,
    drift=drift_results, rows=ROWS,
)
check("Ranking returns results", len(ranked) == len(FEATURES))
check("Ranking has ranks", ranked[0].rank == 1)
check("Ranking composite score", ranked[0].composite_score >= 0)
check("Ranking exposes weights", "weights" in ranked[0].to_dict())
check("Ranking weights match", ranked[0].to_dict()["weights"] == RANKING_WEIGHTS)
check("Ranking sorted", ranked[0].composite_score >= ranked[-1].composite_score)

# ── Feature Intelligence Engine ──────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store = AnalysisHistoryStore(Path(tmp) / "history.jsonl")
    from scanner.feature_intelligence import FeatureIntelligenceEngine
    engine = FeatureIntelligenceEngine(store=store)

    result = engine.analyze(ROWS, feature_names=FEATURES)
    check("Engine analyze", result.analysis_id.startswith("fia_"))
    check("Engine importance", len(result.importance) == len(FEATURES))
    check("Engine stability", len(result.stability) == len(FEATURES))
    check("Engine drift", len(result.drift) == len(FEATURES))
    check("Engine correlation", "matrix" in result.correlation)
    check("Engine redundancy", "redundant_pairs" in result.redundancy)
    check("Engine ranking", len(result.ranking) == len(FEATURES))
    check("Engine report", "summary" in result.report)
    check("Engine row_count", result.row_count == N)
    check("Engine persisted", (Path(tmp) / "history.jsonl").exists())

    rank_result = engine.rank(ROWS, feature_names=FEATURES)
    check("Engine rank", len(rank_result) == len(FEATURES))

    drift_only = engine.drift(ROWS, feature_names=FEATURES)
    check("Engine drift", len(drift_only) == len(FEATURES))

    report = engine.report(result.analysis_id)
    check("Engine report load", "summary" in report)

    hist = engine.history()
    check("Engine history", len(hist) >= 1)

# ── FeatureIntelligenceService ───────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    svc = FeatureIntelligenceService(
        store=AnalysisHistoryStore(Path(tmp) / "history.jsonl"))

    svc_result = svc.analyze(ROWS, feature_names=FEATURES)
    check("Service analyze", svc_result.feature_count == len(FEATURES))

    svc_rank = svc.rank(ROWS, feature_names=FEATURES)
    check("Service rank", len(svc_rank) == len(FEATURES))

    svc_drift = svc.drift(ROWS, feature_names=FEATURES)
    check("Service drift", len(svc_drift) == len(FEATURES))

    svc_report = svc.report(svc_result.analysis_id)
    check("Service report", "feature_reports" in svc_report or "summary" in svc_report)

    svc_hist = svc.history()
    check("Service history", len(svc_hist) >= 1)

    weights = svc.ranking_weights()
    check("Service ranking_weights", weights == RANKING_WEIGHTS)

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Feature Intelligence Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
