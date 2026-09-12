# -*- coding: utf-8 -*-
"""Unit tests for scanner.intelligence — run: python tests_intelligence.py"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.intelligence import (
    EdgeMonitor,
    HistoricalStatisticsEngine,
    InsightEngine,
    IntelligenceEngine,
    IntelligenceService,
    KnowledgeSummaryEngine,
    MarketMemoryEngine,
    PatternEngine,
    StrategyHealthEngine,
    TrendMonitor,
)
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, status: str = WON, r: float = 1.0,
             factors: list[str] | None = None,
             market: str = "crypto", tf: str = "4h",
             grade: str = "A", atr_pct: float = 2.0) -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 12, 0, tzinfo=timezone.utc)
    return {
        "status": status,
        "r_multiple": r,
        "factors": factors or ["htf", "confluence"],
        "market": market,
        "timeframe": tf,
        "grade": grade,
        "closed_at": ts,
        "signal_at": ts,
        "atr_pct": atr_pct,
    }


def _sample_rows(n: int = 30) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        won = i % 3 != 0
        rows.append(_trade(
            i,
            status=WON if won else LOST,
            r=1.5 if won else -1.0,
            factors=["htf", "confluence", "price_action"] if i % 2 == 0 else ["htf", "sweep"],
            tf="4h" if i % 2 == 0 else "1h",
            market="crypto" if i < n // 2 else "forex",
        ))
    return rows


# ── Pattern Engine ─────────────────────────────────────────────────────────

rows = _sample_rows(20)
pat = PatternEngine(min_trades=3).discover(rows)
check("PatternEngine returns patterns", len(pat.patterns) > 0, str(len(pat.patterns)))
check("Pattern has expectancy", pat.patterns[0].expectancy is not None,
      str(pat.patterns[0].expectancy))
check("Pattern label is human-readable", "+" in pat.patterns[0].label or pat.patterns[0].label,
      pat.patterns[0].label)
check("Pattern to_dict", "patterns" in pat.to_dict())

# ── Edge Monitor ───────────────────────────────────────────────────────────

edge = EdgeMonitor(windows=[5, 10]).analyze(rows)
check("EdgeMonitor snapshots", len(edge.snapshots) >= 1, str(len(edge.snapshots)))
check("EdgeMonitor has stability", edge.edge_stability is not None,
      str(edge.edge_stability))
check("Edge snapshot fields", edge.snapshots[0].expectancy is not None)

# Degrading edge: last trades all losses
bad_rows = _sample_rows(15)
for r in bad_rows[-5:]:
    r["status"] = LOST
    r["r_multiple"] = -1.0
edge_bad = EdgeMonitor(windows=[5, 10]).analyze(bad_rows)
check("EdgeMonitor alerts on degradation", len(edge_bad.alerts) > 0,
      str(len(edge_bad.alerts)))

# ── Trend Monitor ────────────────────────────────────────────────────────────

trend = TrendMonitor(bucket_size=5).analyze(rows)
check("TrendMonitor points", len(trend.points) > 0, str(len(trend.points)))
check("TrendMonitor direction", trend.direction in ("improving", "degrading", "flat"),
      trend.direction)

# ── Market Memory ────────────────────────────────────────────────────────────

memory = MarketMemoryEngine(min_trades=3).build(rows)
check("MarketMemory records", len(memory.records) > 0, str(len(memory.records)))
check("MarketMemory has expectancy", memory.records[0].expectancy is not None)

# ── Strategy Health ──────────────────────────────────────────────────────────

health = StrategyHealthEngine().assess(rows, pattern_count=5, market_memory_count=3)
check("Health overall score", 0 <= health.overall_health_score <= 100,
      str(health.overall_health_score))
check("Health components exposed", len(health.components) >= 5,
      str(len(health.components)))
check("Health label", health.label in ("healthy", "monitor", "weak"), health.label)

# ── Historical Statistics ────────────────────────────────────────────────────

stats = HistoricalStatisticsEngine().generate(rows)
check("Stats best timeframes", isinstance(stats.best_timeframes, list))
check("Stats worst patterns", isinstance(stats.worst_patterns, list))

# ── Knowledge Summary ────────────────────────────────────────────────────────

summary = KnowledgeSummaryEngine(default_window=50).summarize(rows)
check("Summary closed trades", summary.closed_trades > 0, str(summary.closed_trades))
check("Summary factor importance", len(summary.factor_importance) > 0,
      str(len(summary.factor_importance)))
check("Summary importance fields", summary.trend_importance >= 0)

# ── Insight Engine ───────────────────────────────────────────────────────────

insight_report = InsightEngine().build(
    patterns=pat, edge=edge, health=health,
    statistics=stats, summary=summary,
)
check("InsightEngine produces items", len(insight_report.items) > 0,
      str(len(insight_report.items)))
check("Insight has required fields",
      all(i.insight_id and i.title and i.trace for i in insight_report.items))
check("Insight to_dict", "items" in insight_report.to_dict())

# ── Intelligence Engine (full pipeline) ────────────────────────────────────────

full = IntelligenceEngine().run(rows, strategy_id="test_strategy")
check("IntelligenceEngine strategy_id", full.strategy_id == "test_strategy")
check("IntelligenceEngine all sections",
      full.patterns.patterns and full.edge.snapshots and full.insights.items)
check("IntelligenceReport to_dict",
      "patterns" in full.to_dict() and "insights" in full.to_dict())

# ── Intelligence Service ─────────────────────────────────────────────────────

svc = IntelligenceService()
report = svc.analyze(rows, strategy_id="svc_test")
check("IntelligenceService analyze", report["strategy_id"] == "svc_test")
check("IntelligenceService patterns key", "patterns" in report)
check("IntelligenceService insights key", "insights" in report)
check("discover_patterns", "patterns" in svc.discover_patterns(rows))
check("monitor_edge", "snapshots" in svc.monitor_edge(rows))
check("assess_health", "overall_health_score" in svc.assess_health(rows))
check("generate_insights", len(svc.generate_insights(rows).items) > 0)

# ── Empty input ──────────────────────────────────────────────────────────────

empty = IntelligenceService().analyze([])
check("Empty rows no crash", empty["patterns"]["count"] == 0)
check("Empty rows no insights", empty["insights"]["count"] == 0)

# ── Report ───────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Intelligence Tests: {passed} passed, {failed} failed / {len(results)} total")
print(f"{'='*60}")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    suffix = f"  ({extra})" if extra and not ok else ""
    print(f"  [{mark}] {name}{suffix}")

sys.exit(1 if failed else 0)
