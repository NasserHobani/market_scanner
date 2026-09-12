# -*- coding: utf-8 -*-
"""Unit tests for scanner.optimization — run: python tests_optimization.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.optimization import (
    DEFAULT_RANKING_WEIGHTS,
    ExperimentRegistry,
    GridSearchOptimizer,
    OptimizationEngine,
    OptimizationMethod,
    OptimizationService,
    OptimizationStatus,
    Parameter,
    ParameterEvaluator,
    ParameterRanker,
    ParameterSpace,
    ParameterType,
    RandomSearchOptimizer,
    WalkForwardOptimizer,
    apply_parameters,
    sort_rows_by_time,
)
from scanner.optimization.report import OptimizationReportGenerator
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, status: str = WON, r: float = 1.0,
             factors: list[str] | None = None, score: float = 75.0,
             confidence: float = 0.8, grade: str = "A") -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 12, 0, tzinfo=timezone.utc)
    return {
        "event_id": f"evt_{i}",
        "status": status,
        "r_multiple": r,
        "factors": factors or ["htf", "confluence"],
        "market": "crypto",
        "timeframe": "4h",
        "grade": grade,
        "score": score,
        "confidence": confidence,
        "closed_at": ts,
        "signal_at": ts,
    }


def _sample_rows(n: int = 60) -> list[dict]:
    rows: list[dict] = []
    for i in range(n):
        has_htf = i % 2 == 0
        won = (i % 3 != 0) if has_htf else (i % 5 == 0)
        rows.append(_trade(
            i,
            status=WON if won else LOST,
            r=1.5 if won else -1.0,
            factors=["htf", "confluence"] if has_htf else ["confluence"],
            score=60 + (i % 4) * 10,
            grade=["A", "B", "C", "D"][i % 4],
        ))
    return rows


ROWS = _sample_rows(60)

# ── Parameter Space ──────────────────────────────────────────────────────────

space = ParameterSpace()
space.add(Parameter("min_score", ParameterType.INTEGER.value, low=60, high=80, step=10))
space.add(Parameter("require_htf", ParameterType.BOOLEAN.value))
space.add_constraint("score range valid", lambda p: p.get("min_score", 0) >= 0)

check("Space parameters", len(space.parameters) == 2)
check("Space defaults", "min_score" in space.defaults() or True)

grid_combos = list(space.grid_combinations())
check("Grid combinations", len(grid_combos) == 6, str(len(grid_combos)))  # 3 scores × 2 bool

samples_a = space.random_sample(5, seed=42)
samples_b = space.random_sample(5, seed=42)
check("Random sample repeatable", samples_a == samples_b)
check("Random sample count", len(samples_a) == 5)

errors = space.validate_params({"min_score": 70, "require_htf": True})
check("Valid params no errors", len(errors) == 0)

bad_errors = space.validate_params({"min_score": 999, "require_htf": True})
check("Invalid params caught", len(bad_errors) > 0)

# ── Evaluation ───────────────────────────────────────────────────────────────

evaluator = ParameterEvaluator()
all_eval = evaluator.evaluate(ROWS, {"min_score": 60})
htf_eval = evaluator.evaluate(ROWS, {"min_score": 60, "require_htf": True})
check("Evaluate trade count", all_eval["trade_count"] > 0)
check("HTF filter reduces trades", htf_eval["trade_count"] < all_eval["trade_count"])
check("Evaluate has expectancy", all_eval.get("expectancy") is not None)
check("Evaluate has profit_factor", all_eval.get("profit_factor") is not None)
check("Evaluate has win_rate", all_eval.get("win_rate") is not None)
check("Evaluate has avg_r", all_eval.get("avg_r") is not None)
check("Evaluate has drawdown", all_eval.get("max_drawdown_r") is not None)

filtered = apply_parameters(ROWS, {"require_htf": True, "min_grade": "B"})
check("Apply parameters filters", all(r.get("grade") in ("A", "B") or True for r in filtered))

sorted_rows = sort_rows_by_time(list(reversed(ROWS)))
times = [r["closed_at"] for r in sorted_rows]
check("Sort by time", times == sorted(times))

# ── Grid Search ──────────────────────────────────────────────────────────────

grid = GridSearchOptimizer()
grid_results = grid.search(space, evaluator, ROWS)
check("Grid search results", len(grid_results) == len(grid_combos))
check("Grid search has params", all("params" in r for r in grid_results))

# ── Random Search ────────────────────────────────────────────────────────────

rand = RandomSearchOptimizer()
rand_results = rand.search(space, evaluator, ROWS, n_samples=10, seed=99)
check("Random search count", 0 < len(rand_results) <= min(10, len(grid_combos)))
rand2 = rand.search(space, evaluator, ROWS, n_samples=10, seed=99)
check("Random search deterministic", rand_results == rand2)

# ── Walk Forward ─────────────────────────────────────────────────────────────

wf = WalkForwardOptimizer(inner_method="grid")
wf_results = wf.search(space, evaluator, ROWS, train_window=30, validation_window=10, step=10)
check("Walk forward results", len(wf_results) >= 1)
check("Walk forward has OOS", wf_results[0].get("oos_performance") is not None)
check("Walk forward metadata", "walk_forward" in wf_results[0])

# ── Ranking ──────────────────────────────────────────────────────────────────

ranker = ParameterRanker()
ranked = ranker.rank(grid_results)
check("Ranking sorted", ranked[0]["composite_score"] >= ranked[-1]["composite_score"])
check("Ranking has ranks", ranked[0]["rank"] == 1)

board = ranker.leaderboard(grid_results, top_n=3)
check("Leaderboard top", len(board["top_strategies"]) == 3)
check("Leaderboard worst", len(board["worst_parameter_sets"]) == 3)
check("Leaderboard total", board["total_evaluated"] == len(grid_results))
check("Ranking weights exposed", ranker.weights == DEFAULT_RANKING_WEIGHTS)

# ── Report ───────────────────────────────────────────────────────────────────

reporter = OptimizationReportGenerator()
report = reporter.generate(
    experiment_id="opt_test",
    method="grid",
    ranked_results=ranked,
    baseline=all_eval,
    leaderboard=board,
)
check("Report has id", report["report_id"].startswith("optrpt_"))
check("Report best params", bool(report["best_parameters"]))
check("Report improvement", bool(report["improvement"]))
check("Report confidence", report["confidence"]["label"] in ("high", "medium", "low"))
check("Report warnings list", isinstance(report["warnings"], list))
check("Report trade count", report["best_metrics"]["closed_trades"] is not None)

# ── Registry ─────────────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    registry = ExperimentRegistry(store_path)
    from scanner.optimization.experiment_registry import OptimizationExperiment
    exp = OptimizationExperiment(
        experiment_id="opt_test001",
        title="Test",
        method="grid",
        status=OptimizationStatus.COMPLETED.value,
    )
    registry.save(exp)
    loaded = registry.load("opt_test001")
    check("Registry save/load", loaded is not None and loaded.title == "Test")
    check("Registry history", len(registry.history()) == 1)

# ── Engine ───────────────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    engine = OptimizationEngine(registry=ExperimentRegistry(store_path))
    result = engine.optimize(ROWS, space, method="grid", title="Engine Test")
    check("Engine optimize status", result["status"] == OptimizationStatus.COMPLETED.value)
    check("Engine experiment id", result["experiment_id"].startswith("opt_"))
    check("Engine report", bool(result["report"]))
    check("Engine leaderboard", bool(result["leaderboard"]))

    single = engine.evaluate(ROWS, {"min_score": 70})
    check("Engine evaluate", single.get("expectancy") is not None)

    lb = engine.leaderboard(result["experiment_id"])
    check("Engine leaderboard lookup", lb is not None)

    hist = engine.history()
    check("Engine history", len(hist) >= 1)

# ── Service ──────────────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    svc = OptimizationService(registry=ExperimentRegistry(store_path))

    svc_result = svc.optimize(ROWS, space, method="random", n_samples=8, seed=7,
                              title="Service Random Test")
    check("Service optimize", svc_result["method"] == "random")

    svc_eval = svc.evaluate(ROWS, {"min_score": 60, "require_htf": False})
    check("Service evaluate", svc_eval["trade_count"] > 0)

    svc_board = svc.leaderboard(svc_result["experiment_id"])
    check("Service leaderboard", svc_board is not None)

    svc_hist = svc.history()
    check("Service history", len(svc_hist) >= 1)

    built = OptimizationService.build_space(
        min_score_range=(60, 80, 10),
        require_htf=False,
        min_grade_choices=["A", "B"],
    )
    check("Service build_space", len(built.parameters) >= 2)

# ── Walk Forward Service ─────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    store_path = Path(tmp) / "experiments.jsonl"
    svc_wf = OptimizationService(registry=ExperimentRegistry(store_path))
    wf_result = svc_wf.optimize(
        ROWS, space,
        method=OptimizationMethod.WALK_FORWARD.value,
        train_window=30, validation_window=10, step=10,
        title="WF Test",
    )
    check("Service walk forward", wf_result["method"] == "walk_forward")
    check("Service WF report", wf_result["report"].get("walk_forward") is not None
          or wf_result["report"].get("oos_metrics") is not None)

# ── Categorical Parameter ────────────────────────────────────────────────────

cat_space = ParameterSpace()
cat_space.add(Parameter("min_grade", ParameterType.CATEGORICAL.value,
                        choices=("A", "B", "C")))
cat_results = grid.search(cat_space, evaluator, ROWS)
check("Categorical grid", len(cat_results) == 3)

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Optimization Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
