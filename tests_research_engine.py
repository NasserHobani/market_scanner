# -*- coding: utf-8 -*-
"""Unit tests for scanner.research — run: python tests_research_engine.py"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.research import (
    ComparisonEngine,
    DatasetBuilder,
    Experiment,
    ExperimentStatus,
    ExperimentStore,
    Hypothesis,
    HypothesisEngine,
    MetricsEngine,
    ReportGenerator,
    ResearchEngine,
    ResearchService,
)
from scanner.research.experiment_runner import ExperimentRunner
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, status: str = WON, r: float = 1.0,
             factors: list[str] | None = None,
             market: str = "crypto", tf: str = "4h",
             grade: str = "A", event_id: str = "") -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 12, 0, tzinfo=timezone.utc)
    return {
        "event_id": event_id or f"evt_{i}",
        "status": status,
        "r_multiple": r,
        "factors": factors or ["htf", "confluence"],
        "market": market,
        "timeframe": tf,
        "grade": grade,
        "closed_at": ts,
        "signal_at": ts,
    }


def _sample_rows(n: int = 40) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        has_htf = i % 2 == 0
        won = (i % 3 != 0) if has_htf else (i % 4 != 0)
        rows.append(_trade(
            i,
            status=WON if won else LOST,
            r=2.0 if won else -1.0,
            factors=["htf", "confluence"] if has_htf else ["sweep"],
            tf="4h" if i % 2 == 0 else "1h",
            market="crypto" if i < n // 2 else "forex",
            grade="A" if has_htf else "B",
        ))
    return rows


ROWS = _sample_rows(40)

# ── Dataset Builder ────────────────────────────────────────────────────────

builder = DatasetBuilder()
ds = builder.from_rows(ROWS, label="all")
check("DatasetBuilder creates dataset", ds.count == 40, str(ds.count))
check("Dataset fingerprint", ds.fingerprint().startswith("ds_"), ds.fingerprint())

completed = builder.completed(ds)
check("Completed filter", completed.closed_count == completed.count,
      f"{completed.closed_count}/{completed.count}")

winners = builder.winners(ds)
check("Winners filter", all(r["status"] == WON for r in winners.rows), str(winners.count))

losers = builder.losers(ds)
check("Losers filter", all(r["status"] == LOST for r in losers.rows), str(losers.count))

by_mkt = builder.by_market(ds, "crypto")
check("Market filter", all(r["market"] == "crypto" for r in by_mkt.rows), str(by_mkt.count))

by_tf = builder.by_timeframe(ds, "4h")
check("Timeframe filter", all(r["timeframe"] == "4h" for r in by_tf.rows), str(by_tf.count))

by_factor = builder.by_factor(ds, "htf")
check("Factor filter", all("htf" in r["factors"] for r in by_factor.rows), str(by_factor.count))

by_regime = builder.by_regime(ds, "A")
check("Regime filter", all(r["grade"] == "A" for r in by_regime.rows), str(by_regime.count))

# ── Metrics Engine ─────────────────────────────────────────────────────────

metrics = MetricsEngine().compute(ROWS)
check("Metrics expectancy", metrics.get("expectancy") is not None, str(metrics.get("expectancy")))
check("Metrics win_rate", metrics.get("win_rate") is not None, str(metrics.get("win_rate")))
check("Metrics profit_factor", "profit_factor" in metrics)
check("Metrics median_r", "median_r" in metrics)
check("Metrics sharpe", "sharpe" in metrics)
check("Metrics recovery_factor", "recovery_factor" in metrics)
check("Metrics deterministic", metrics["trade_count"] == 40, str(metrics["trade_count"]))

# ── Hypothesis Engine ─────────────────────────────────────────────────────

hyp = Hypothesis(
    hypothesis_id="hyp_htf",
    title="HTF filter improves expectancy",
    filter_type="factor",
    filter_key="htf",
    treatment_label="with_htf",
    baseline_label="without_htf",
)
engine = HypothesisEngine()
treatment, baseline = engine.split(ROWS, hyp)
check("Hypothesis split", len(treatment) + len(baseline) == 40,
      f"{len(treatment)}+{len(baseline)}")
check("Treatment has htf", all("htf" in r["factors"] for r in treatment))
check("Baseline lacks htf", all("htf" not in r["factors"] for r in baseline))

eval_result = engine.evaluate(ROWS, hyp)
check("Hypothesis evaluate", eval_result["treatment_count"] == len(treatment))

# ── Comparison Engine ──────────────────────────────────────────────────────

cmp = ComparisonEngine().compare(treatment, baseline,
                                  label_a="with_htf", label_b="without_htf")
check("Comparison has metrics", "metrics_a" in cmp.to_dict() or cmp.metrics_a)
check("Comparison statistics", cmp.statistics.get("differences") is not None)
check("Comparison winner", cmp.winner in ("with_htf", "without_htf", "tie", "inconclusive"),
      cmp.winner)
check("Comparison notes", isinstance(cmp.notes, list))

cmp_mkt = ComparisonEngine().market_vs_market(
    builder.by_market(ds, "crypto").rows,
    builder.by_market(ds, "forex").rows,
    market_a="crypto", market_b="forex",
)
check("Market vs market", cmp_mkt.comparison_type == "market_vs_market")

cmp_tf = ComparisonEngine().timeframe_vs_timeframe(
    builder.by_timeframe(ds, "4h").rows,
    builder.by_timeframe(ds, "1h").rows,
    tf_a="4h", tf_b="1h",
)
check("Timeframe vs timeframe", cmp_tf.comparison_type == "timeframe_vs_timeframe")

# ── Report Generator ───────────────────────────────────────────────────────

report = ReportGenerator().generate(
    experiment_id="rex_test",
    title="HTF Test",
    dataset_summary=ds.to_dict(),
    methodology={"version": "1.0.0", "hypothesis": hyp.to_dict()},
    metrics={"treatment": metrics, "baseline": metrics},
    comparison=cmp.to_dict(),
    hypothesis_eval=eval_result,
)
check("Report has id", report.report_id.startswith("rpt_"), report.report_id)
check("Report conclusions", len(report.conclusions) > 0, str(len(report.conclusions)))
check("Report warnings", isinstance(report.warnings, list))
check("Report limitations", len(report.limitations) > 0)
check("Report to_dict", "methodology" in report.to_dict())

# ── Experiment Runner ──────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    store = ExperimentStore(store_path)
    runner = ExperimentRunner(store=store)

    exp = runner.run(
        title="HTF Filter Test",
        rows=ROWS,
        hypothesis=hyp,
        description="Does HTF improve expectancy?",
        dataset_config={"completed_only": True},
    )
    check("Experiment completed", exp.status == ExperimentStatus.COMPLETED.value, exp.status)
    check("Experiment has results", "metrics" in exp.results)
    check("Experiment has report", exp.report_id.startswith("rpt_"), exp.report_id)
    check("Experiment persisted", store_path.exists())

    loaded = store.load(exp.experiment_id)
    check("Experiment loadable", loaded.experiment_id == exp.experiment_id)

    history = store.history()
    check("Experiment history", len(history) >= 1, str(len(history)))

# ── Research Engine ────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    engine = ResearchEngine(store=ExperimentStore(store_path))

    exp2 = engine.run_experiment(
        title="No Hypothesis Baseline",
        rows=ROWS,
        dataset_config={"label": "baseline"},
    )
    check("Engine run without hypothesis", exp2.status == ExperimentStatus.COMPLETED.value)
    check("Engine all metrics", "all" in exp2.results.get("metrics", {}))

    stats = engine.statistics(ROWS)
    check("Engine statistics", stats.get("expectancy") is not None)

    cmp2 = engine.compare(treatment, baseline, label_a="A", label_b="B")
    check("Engine compare", cmp2.winner is not None)

    rpt = engine.generate_report(exp2.experiment_id)
    check("Engine generate_report", rpt.experiment_id == exp2.experiment_id)

    hist = engine.history()
    check("Engine history", len(hist) >= 1)

# ── Research Service ───────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    svc = ResearchService(store=ExperimentStore(store_path))

    exp3 = svc.run_experiment(
        title="Service Test",
        rows=ROWS,
        hypothesis={"hypothesis_id": "h1", "title": "Liquidity filter",
                    "filter_type": "factor", "filter_key": "confluence"},
    )
    check("Service run_experiment", exp3.status == ExperimentStatus.COMPLETED.value)

    svc_stats = svc.statistics(ROWS)
    check("Service statistics", svc_stats.get("win_rate") is not None)

    svc_cmp = svc.compare(treatment, baseline, label_a="T", label_b="B")
    check("Service compare", svc_cmp.comparison_id.startswith("cmp_"))

    svc_rpt = svc.generate_report(exp3.experiment_id)
    check("Service generate_report", svc_rpt.title == "Service Test")

    svc_hist = svc.history()
    check("Service history", len(svc_hist) >= 1)

    diff = svc.compare_metrics(svc_stats, svc_stats, label_a="X", label_b="Y")
    check("Service compare_metrics", "differences" in diff)

# ── Experiment Model ───────────────────────────────────────────────────────

exp_dict = Experiment(
    experiment_id="rex_abc",
    title="Test",
    status=ExperimentStatus.PENDING.value,
).to_dict()
check("Experiment to_dict", exp_dict["experiment_id"] == "rex_abc")
restored = Experiment.from_dict(exp_dict)
check("Experiment from_dict", restored.title == "Test")

# ── Summary ────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Research Engine Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
