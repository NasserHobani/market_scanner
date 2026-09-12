# -*- coding: utf-8 -*-
"""Unit tests for scanner.ai_learning — run: python tests_ai_learning.py"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.evaluation.advisor_dataset import AdvisorEvaluationDataset
from scanner.ai_learning import (
    LearningEngine,
    LearningHistory,
    LearningService,
    LessonRepository,
    PatternDetector,
    ReflectionEngine,
    LessonGenerator,
    KnowledgeProposals,
    HypothesisGenerator,
    ImprovementCandidates,
    ReflectionReport,
    LEARNING_VERSION,
    LESSON_STATUSES,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sample_evaluations() -> list[dict]:
    return [
        {"evaluation_id": f"eval_{i}", "trade_id": f"t{i}", "provider": "claude",
         "market": "crypto", "timeframe": "4h", "strategy": "breakout",
         "advisor_correct": i % 3 != 0, "advisor_agreement": "agree" if i % 2 == 0 else "disagree",
         "advisor_confidence": 70 + i * 3, "hallucination": i == 2,
         "missed_warning": i == 4, "false_warning": False,
         "execution_date": _today(), "direction": "buy"}
        for i in range(10)
    ] + [
        {"evaluation_id": "eval_bad", "trade_id": "t_bad", "provider": "openai",
         "market": "forex", "timeframe": "1h", "strategy": "reversal",
         "advisor_correct": False, "advisor_agreement": "agree",
         "advisor_confidence": 92, "hallucination": True,
         "missed_warning": False, "false_warning": False,
         "execution_date": _today(), "direction": "sell"},
    ] * 3


# ── Lesson repository ────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    repo = LessonRepository(Path(tmp) / "lessons.jsonl")
    lid = repo.save({"title": "Test lesson", "description": "desc", "sample_size": 5})
    check("lesson save", bool(lid))
    check("lesson load", repo.load(lid) is not None)
    check("lesson status update", repo.update_status(lid, "UNDER_REVIEW"))
    check("lesson status valid", repo.load(lid)["status"] == "UNDER_REVIEW")
    check("lesson count", repo.count() == 1)


# ── Learning history ─────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    hist = LearningHistory(tmp)
    pid = hist.save_proposal({"reason": "test", "confidence": 80})
    hid = hist.save_hypothesis({"statement": "test hyp"})
    rid = hist.save_report({"period": "daily"})
    check("history proposal", bool(pid))
    check("history hypothesis", bool(hid))
    check("history report", bool(rid))
    check("history list proposals", len(hist.list_proposals()) == 1)


# ── Reflection ───────────────────────────────────────────────────────────────

evals = _sample_evaluations()
reflection = ReflectionEngine().reflect(evaluations=evals, scope={"last_n": 5})
check("reflection sample size", reflection["sample_size"] == 5)
check("reflection has accuracy", reflection.get("accuracy") is not None)
check("reflection failures", "failures" in reflection)
check("reflection successes", "successes" in reflection)

scoped = ReflectionEngine().reflect(evaluations=evals, scope={"market": "crypto"})
check("reflection market filter", all(e.get("market") == "crypto" for e in scoped["evaluations"]))


# ── Pattern detection ────────────────────────────────────────────────────────

patterns = PatternDetector().detect(evals, context={
    "research_results": [{"verdict": "disagree", "experiment_id": "exp1"}],
    "optimization_results": [{"similarity_score": 0.3, "optimization_id": "opt1"}],
    "trade_outcomes": [{"low_liquidity": True, "market": "forex"}],
    "prediction_results": [{"confidence": 0.9, "correct": False, "prediction_id": "p1"}],
})
check("patterns detected", len(patterns) > 0)
check("pattern has evidence", all("supporting_evidence" in p for p in patterns))
check("pattern has type", all("pattern_type" in p for p in patterns))


# ── Lesson generation ────────────────────────────────────────────────────────

lessons = LessonGenerator().generate(patterns, evals)
check("lessons generated", len(lessons) > 0)
check("lesson has id", all("lesson_id" in l for l in lessons))
check("lesson status NEW", all(l.get("status") == "NEW" for l in lessons))
check("lesson has evidence", all("supporting_evidence" in l for l in lessons))


# ── Knowledge proposals ──────────────────────────────────────────────────────

proposals = KnowledgeProposals().generate(lessons)
check("proposals generated", len(proposals) > 0)
check("proposal has id", all("proposal_id" in p for p in proposals))
check("proposal has module", all("affected_module" in p for p in proposals))
check("proposal has experiment", all("required_experiment" in p for p in proposals))


# ── Hypothesis generation ────────────────────────────────────────────────────

hypotheses = HypothesisGenerator().generate(lessons, patterns)
check("hypotheses generated", len(hypotheses) > 0)
check("hypothesis has statement", all("statement" in h for h in hypotheses))
check("hypothesis not executed", all(h.get("status") == "NEW" for h in hypotheses))


# ── Improvement ranking ──────────────────────────────────────────────────────

candidates = ImprovementCandidates().rank(lessons=lessons, proposals=proposals, hypotheses=hypotheses)
check("candidates ranked", len(candidates) > 0)
check("candidates sorted", candidates[0]["rank"] == 1)
check("candidate composite score", all("composite_score" in c for c in candidates))
check("candidate has impact", all("impact" in c for c in candidates))


# ── Reflection report ────────────────────────────────────────────────────────

report = ReflectionReport().generate(
    reflection=reflection, lessons=lessons, proposals=proposals,
    hypotheses=hypotheses, candidates=candidates, evaluations=evals, period="daily",
)
check("report has top lessons", "top_lessons" in report)
check("report has proposals", "new_proposals" in report)
check("report has experiments", "suggested_experiments" in report)
check("report provider comparison", "provider_comparison" in report)

ui = ReflectionReport().to_ui_model(
    lessons=lessons, proposals=proposals, hypotheses=hypotheses,
    candidates=candidates, reports=[report],
)
check("ui lessons", "lessons" in ui)
check("ui top insights", "top_insights" in ui)
check("ui proposals", "knowledge_proposals" in ui)
check("ui experiments", "suggested_experiments" in ui)
check("ui timeline", "reflection_timeline" in ui)


# ── Learning engine full cycle ───────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "evals.jsonl"
    lesson_path = Path(tmp) / "lessons.jsonl"
    hist_dir = Path(tmp) / "history"

    dataset = AdvisorEvaluationDataset(eval_path)
    for e in _sample_evaluations():
        dataset.save(e)

    engine = LearningEngine(
        dataset=dataset,
        lessons=LessonRepository(lesson_path),
        history=LearningHistory(hist_dir),
    )

    cycle = engine.run_cycle(scope={"last_n": 10}, period="daily")
    check("cycle has reflection", "reflection" in cycle)
    check("cycle has patterns", len(cycle["patterns"]) > 0)
    check("cycle has lessons", len(cycle["lessons"]) > 0)
    check("cycle has proposals", len(cycle["proposals"]) > 0)
    check("cycle has hypotheses", len(cycle["hypotheses"]) > 0)
    check("cycle has candidates", len(cycle["candidates"]) > 0)
    check("cycle has report", "report" in cycle)

    check("lessons persisted", engine.list_lessons() != [])
    check("proposals persisted", engine.list_proposals() != [])
    check("hypotheses persisted", engine.list_hypotheses() != [])
    check("reports persisted", engine.list_reports() != [])

    lid = engine.list_lessons()[0]["lesson_id"]
    check("lesson status VALIDATED", engine.update_lesson_status(lid, "VALIDATED"))


# ── Service facade ───────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "evals.jsonl"
    dataset = AdvisorEvaluationDataset(eval_path)
    for e in _sample_evaluations()[:5]:
        dataset.save(e)

    svc = LearningService(engine=LearningEngine(
        dataset=dataset,
        lessons=LessonRepository(Path(tmp) / "lessons.jsonl"),
        history=LearningHistory(Path(tmp) / "hist"),
    ))
    cycle = svc.run_cycle(scope={"last_n": 5})
    check("service run_cycle", "lessons" in cycle)
    ui_svc = svc.to_ui_model()
    check("service ui available", ui_svc.get("available") is True)
    check("service advisory only", ui_svc.get("advisory_only") is True)


# ── Versioning ───────────────────────────────────────────────────────────────

check("learning version", LEARNING_VERSION == "1.0.0")
check("lesson statuses", "NEW" in LESSON_STATUSES and "VALIDATED" in LESSON_STATUSES)


# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*60}")
print(f"AI Learning Tests: {passed}/{len(results)} passed")
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
