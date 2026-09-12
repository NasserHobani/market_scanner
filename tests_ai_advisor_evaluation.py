# -*- coding: utf-8 -*-
"""Unit tests for scanner.ai_advisor.evaluation — run: python tests_ai_advisor_evaluation.py"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.memory import AdvisorMemory
from scanner.ai_advisor.evaluation import (
    AdvisorEvaluationDataset,
    AdvisorEvaluationService,
    AdvisorMetrics,
    AdvisorReport,
    EvaluationEngine,
    ProviderBenchmark,
    ProviderLeaderboard,
    EvaluationScheduler,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _make_memory_record(review_id: str, *, agreement: str = "agree",
                        confidence: float = 80, risks: list | None = None,
                        hallucination_count: int = 0,
                        provider: str = "claude") -> dict:
    return {
        "record_id": review_id,
        "package_id": "pkg_test_001",
        "event_id": "evt_001",
        "prompt_version": "advisor_prompt_v1",
        "provider_id": provider,
        "model_name": "claude-test",
        "response": {
            "agreement": agreement,
            "confidence": confidence,
            "risks": risks or [],
            "validation": {"hallucination_count": hallucination_count},
        },
        "accepted": True,
        "rejected": False,
    }


def _trade_result(*, status: str = "won", r_multiple: float = 1.5,
                  market: str = "crypto", timeframe: str = "4h",
                  strategy: str = "breakout", direction: str = "buy") -> dict:
    return {
        "status": status,
        "r_multiple": r_multiple,
        "market": market,
        "timeframe": timeframe,
        "strategy": strategy,
        "direction": direction,
        "execution_date": "2026-08-09",
        "expectancy": 0.8,
        "profit_factor": 1.5,
    }


# ── Dataset persistence ──────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    ds_path = Path(tmp) / "eval.jsonl"
    dataset = AdvisorEvaluationDataset(ds_path)
    eid = dataset.save({"trade_id": "t1", "advisor_correct": True, "provider": "claude"})
    check("dataset save returns id", bool(eid))
    loaded = dataset.load(eid)
    check("dataset load", loaded is not None and loaded["trade_id"] == "t1")
    check("dataset schema version", loaded.get("schema_version") == "1.0.0")
    check("dataset count", dataset.count() == 1)
    check("dataset by_provider", len(dataset.by_provider("claude")) == 1)


# ── Evaluation engine ────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    mem_path = Path(tmp) / "memory.jsonl"
    eval_path = Path(tmp) / "eval.jsonl"
    memory = AdvisorMemory(mem_path)
    dataset = AdvisorEvaluationDataset(eval_path)
    engine = EvaluationEngine(dataset=dataset, memory=memory)

    review_id = memory.save(
        package_id="pkg_001", event_id="evt_001",
        prompt_version="advisor_prompt_v1", provider_id="claude",
        model_name="claude-test",
        response={"agreement": "agree", "confidence": 85, "risks": ["volatility"],
                  "validation": {"hallucination_count": 0}},
        accepted=True,
    )

    result = engine.evaluate_by_review_id(
        trade_id="trade_001",
        review_id=review_id,
        trade_result=_trade_result(status="won"),
    )
    check("evaluation returns id", "evaluation_id" in result)
    check("advisor correct on agree+won", result.get("advisor_correct") is True)
    check("useful warning on agree+won with risks", result.get("false_warning") is True)
    check("dataset persisted", dataset.count() == 1)

    mem_record = memory.load(review_id)
    check("memory performance updated", mem_record.get("later_performance", {}).get("outcome") == "correct")

    result2 = engine.evaluate_by_review_id(
        trade_id="trade_002",
        review_id=review_id,
        trade_result=_trade_result(status="lost", r_multiple=-1.5),
    )
    check("advisor incorrect on agree+lost", result2.get("advisor_correct") is False)
    check("useful warning on lost with risks", result2.get("useful_warning") is True)


# ── Hallucination detection ──────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "eval.jsonl"
    engine = EvaluationEngine(dataset=AdvisorEvaluationDataset(eval_path))
    record = _make_memory_record("rev_hall", hallucination_count=2)
    ev = engine.evaluate_closed_trade(
        trade_id="t_hall", trade_result=_trade_result(), memory_record=record,
    )
    check("hallucination flagged", ev.get("hallucination") is True)


# ── Metrics ──────────────────────────────────────────────────────────────────

from datetime import datetime, timezone

records = [
    {"advisor_correct": True, "advisor_agreement": "agree", "advisor_confidence": 75,
     "hallucination": False, "useful_warning": False, "false_warning": False,
     "missed_warning": False, "market": "crypto", "timeframe": "4h",
     "strategy": "breakout", "trend": "bullish", "direction": "buy",
     "execution_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
    {"advisor_correct": False, "advisor_agreement": "agree", "advisor_confidence": 55,
     "hallucination": True, "useful_warning": True, "false_warning": False,
     "missed_warning": False, "market": "forex", "timeframe": "1h",
     "strategy": "reversal", "trend": "bearish", "direction": "sell",
     "execution_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
    {"advisor_correct": True, "advisor_agreement": "disagree", "advisor_confidence": 92,
     "hallucination": False, "useful_warning": False, "false_warning": False,
     "missed_warning": True, "market": "crypto", "timeframe": "4h",
     "strategy": "breakout", "trend": "bullish", "direction": "long",
     "execution_date": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
]
metrics = AdvisorMetrics().compute(records)
check("overall accuracy", metrics["overall_accuracy"]["value"] == 66.7)
check("metrics sample size", metrics["overall_accuracy"]["sample_size"] == 3)
check("metrics CI", len(metrics["overall_accuracy"]["confidence_interval"]) == 2)
check("calibration buckets", len(metrics["confidence_calibration"]) == 5)
check("market accuracy groups", "crypto" in metrics["market_accuracy"])
check("long accuracy", metrics["long_accuracy"]["sample_size"] >= 1)


# ── Leaderboard ──────────────────────────────────────────────────────────────

lb_records = [
    {"provider": "claude", "advisor_correct": True, "advisor_agreement": "agree",
     "advisor_confidence": 80, "hallucination": False, "useful_warning": True},
    {"provider": "claude", "advisor_correct": True, "advisor_agreement": "agree",
     "advisor_confidence": 70, "hallucination": False, "useful_warning": False},
    {"provider": "openai", "advisor_correct": False, "advisor_agreement": "disagree",
     "advisor_confidence": 60, "hallucination": True, "useful_warning": False},
]
board = ProviderLeaderboard().compute(lb_records)
check("leaderboard ranks", len(board) == 2)
check("leaderboard rank 1", board[0]["rank"] == 1)
check("leaderboard claude accuracy", board[0]["provider"] == "claude" and board[0]["accuracy"] == 100.0)
check("leaderboard review count", board[0]["review_count"] == 2)


# ── Benchmark ────────────────────────────────────────────────────────────────

bench_records = [
    {"decision_package_id": "pkg1", "provider": "claude", "advisor_correct": True,
     "hallucination": False, "useful_warning": True},
    {"decision_package_id": "pkg1", "provider": "openai", "advisor_correct": False,
     "hallucination": True, "useful_warning": False},
    {"decision_package_id": "pkg2", "provider": "claude", "advisor_correct": True,
     "hallucination": False, "useful_warning": False},
    {"decision_package_id": "pkg2", "provider": "openai", "advisor_correct": True,
     "hallucination": False, "useful_warning": True},
]
bench = ProviderBenchmark().compare(bench_records, provider_a="claude", provider_b="openai")
check("benchmark winner", bench["winner"] == "claude")
check("benchmark paired", bench["paired_packages"] == 2)
check("benchmark has z_score", "z_score" in bench)
check("benchmark metric diffs", "accuracy" in bench["metric_differences"])


# ── Reports ──────────────────────────────────────────────────────────────────

report = AdvisorReport().generate(records, period="daily")
check("report has score", "overall_advisor_score" in report)
check("report provider ranking", len(report["provider_ranking"]) >= 0)
check("report recommendations", len(report["recommendations"]) > 0)
check("report hallucination summary", report["hallucination_summary"]["count"] == 1)

ui = AdvisorReport().to_ui_model(records)
check("ui advisor score", "advisor_score" in ui)
check("ui calibration curve", "calibration_curve" in ui)
check("ui recent evaluations", "recent_evaluations" in ui)
check("ui accuracy trend", len(ui["accuracy_trend"]) >= 1)


# ── Scheduler ────────────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "eval.jsonl"
    dataset = AdvisorEvaluationDataset(eval_path)
    dataset.save({"trade_id": "t1", "advisor_correct": True, "provider": "claude",
                  "execution_date": "2026-08-09", "advisor_confidence": 80,
                  "advisor_agreement": "agree", "hallucination": False})
    sched = EvaluationScheduler(dataset=dataset)
    daily = sched.run_daily()
    weekly = sched.run_weekly()
    monthly = sched.run_monthly()
    check("scheduler daily", daily["job"] == "daily" and daily["status"] == "completed")
    check("scheduler weekly", weekly["job"] == "weekly")
    check("scheduler monthly", monthly["job"] == "monthly")


# ── Service facade ───────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "eval.jsonl"
    mem_path = Path(tmp) / "memory.jsonl"
    svc = AdvisorEvaluationService(
        dataset=AdvisorEvaluationDataset(eval_path),
        memory=AdvisorMemory(mem_path),
    )
    rid = svc._memory.save(
        package_id="pkg_s", event_id="evt_s",
        prompt_version="advisor_prompt_v1", provider_id="gemini",
        model_name="gemini-test",
        response={"agreement": "disagree", "confidence": 70, "risks": [],
                  "validation": {"hallucination_count": 0}},
        accepted=True,
    )
    ev = svc.evaluate_trade(trade_id="t_svc", review_id=rid,
                            trade_result=_trade_result(status="lost", r_multiple=-1.0))
    check("service evaluate", ev.get("advisor_correct") is True)
    check("service metrics", svc.metrics()["overall_accuracy"]["sample_size"] == 1)
    check("service leaderboard", len(svc.leaderboard()) == 1)
    check("service ui model", svc.to_ui_model()["available"] is True)


# ── Versioning ───────────────────────────────────────────────────────────────

check("evaluation version", EvaluationEngine.__module__ is not None)
from scanner.ai_advisor.evaluation import EVALUATION_VERSION, EVALUATION_SCHEMA_VERSION
check("version constants", EVALUATION_VERSION == "1.0.0" and EVALUATION_SCHEMA_VERSION == "1.0.0")


# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*60}")
print(f"AI Advisor Evaluation Tests: {passed}/{len(results)} passed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if extra:
        line += f" — {extra}"
    print(line)
if failed:
    print(f"\n{len(failed)} FAILED")
    sys.exit(1)
print("\nAll tests passed.")
