# -*- coding: utf-8 -*-
"""AIA-05.5 tests — failure classification, deduplication, thresholds."""
from __future__ import annotations

import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.evaluation.evaluation_engine import EvaluationEngine
from scanner.ai_advisor.evaluation.advisor_dataset import AdvisorEvaluationDataset
from scanner.ai_advisor.memory import AdvisorMemory
from scanner.ai_learning.failure_classifier import classify_evaluation
from scanner.ai_learning.failure_labels import title_ar
from scanner.ai_learning.lesson_fingerprint import lesson_fingerprint
from scanner.ai_learning.lesson_generator import LessonGenerator
from scanner.ai_learning.lesson_repository import LessonRepository
from scanner.ai_learning.lesson_thresholds import recommendation_for_sample, THRESHOLD_EMERGING
from scanner.ai_learning.learning_engine import LearningEngine
from scanner.ai_learning.learning_history import LearningHistory
from scanner.ai_learning.learning_lock import learning_cycle_lock

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _eval(**kwargs):
    base = {
        "advisor_agreement": "agree",
        "advisor_confidence": 70,
        "hallucination": False,
        "missed_warning": False,
        "false_warning": False,
        "trade_result": "WON",
        "r_multiple": 1.5,
        "won": True,
        "lost": False,
    }
    base.update(kwargs)
    return classify_evaluation(base)


# 1–7 classification
check("false_warning disagree+win", _eval(advisor_agreement="disagree", won=True, lost=False)["failure_type"] == "incorrect_disagreement")
check("partial_on_loss", _eval(advisor_agreement="partial", won=False, lost=True, trade_result="LOST", r_multiple=-1)["failure_type"] == "partial_on_loss")
check("partial_on_win", _eval(advisor_agreement="partial", won=True, lost=False)["failure_type"] == "partial_on_win")
check("correct_disagreement", _eval(advisor_agreement="disagree", won=False, lost=True, trade_result="LOST", r_multiple=-1)["evaluation_type"] == "correct_disagreement")
check("correct_disagreement not failure", _eval(advisor_agreement="disagree", won=False, lost=True, trade_result="LOST", r_multiple=-1)["is_failure"] is False)
check("incorrect_disagreement", _eval(advisor_agreement="disagree", won=True, lost=False)["evaluation_type"] == "incorrect_disagreement")
check("high_confidence_wrong secondary", _eval(advisor_agreement="agree", won=False, lost=True, trade_result="LOST", r_multiple=-1, advisor_confidence=85)["secondary_type"] == "high_confidence_wrong")
check("low_confidence_wrong secondary", _eval(advisor_agreement="agree", won=False, lost=True, trade_result="LOST", r_multiple=-1, advisor_confidence=50)["secondary_type"] == "low_confidence_wrong")

# 8 fingerprint
fp1 = lesson_fingerprint(failure_type="false_warning", provider="claude", market="crypto", timeframe="15m")
fp2 = lesson_fingerprint(failure_type="false_warning", provider="claude", market="crypto", timeframe="15m")
fp3 = lesson_fingerprint(failure_type="false_warning", provider="claude", market="crypto", timeframe="4h")
check("fingerprint stable", fp1 == fp2)
check("fingerprint differs by tf", fp1 != fp3)

# 9–12 dedup + update + concurrent + restart
with tempfile.TemporaryDirectory() as tmp:
    lesson_path = Path(tmp) / "lessons.jsonl"
    repo = LessonRepository(lesson_path)
    lesson = {
        "failure_type": "incorrect_disagreement",
        "pattern_type": "incorrect_disagreement",
        "provider": "claude",
        "affected_markets": ["crypto"],
        "affected_timeframes": ["15m"],
        "sample_size": 1,
        "title": "Test",
        "title_ar": "اختبار",
        "evidence": ["eval_1"],
        "trade_examples": [{"trade_id": "t1", "symbol": "BTCUSDT"}],
    }
    lesson["fingerprint"] = lesson_fingerprint(
        failure_type="incorrect_disagreement", provider="claude", market="crypto", timeframe="15m",
    )
    id1, created1 = repo.upsert(lesson)
    check("lesson created", created1)
    lesson2 = {**lesson, "sample_size": 2, "evidence": ["eval_2"], "trade_examples": [{"trade_id": "t2", "symbol": "ETHUSDT"}]}
    id2, created2 = repo.upsert(lesson2)
    check("duplicate prevented", created2 is False and id1 == id2)
    check("sample_size updated", repo.load(id1)["sample_size"] >= 2)
    check("restart dedup list", repo.count() == 1)

    errors: list[str] = []

    def _cycle():
        try:
            with learning_cycle_lock(Path(tmp) / "lock"):
                repo.upsert({**lesson, "sample_size": 3})
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    t1 = threading.Thread(target=_cycle)
    t2 = threading.Thread(target=_cycle)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)
    check("concurrent lock no crash", not errors)

# 13 Arabic labels
check("arabic false_warning", title_ar("false_warning") == "تحذير خاطئ")

# 14 thresholds
check("insufficient sample", recommendation_for_sample(1)["strength"] == "insufficient")
check("emerging sample", recommendation_for_sample(THRESHOLD_EMERGING)["strength"] == "emerging")

# 15–16 semantics via evaluation engine
with tempfile.TemporaryDirectory() as tmp:
    mem = AdvisorMemory(Path(tmp) / "mem.jsonl")
    ds = AdvisorEvaluationDataset(Path(tmp) / "eval.jsonl")
    engine = EvaluationEngine(dataset=ds, memory=mem)
    rid = mem.save(
        package_id="p1", event_id="e1", prompt_version="v1", provider_id="claude",
        model_name="m", response={"agreement": "disagree", "confidence": 72, "risks": ["x"],
                                   "validation": {"hallucination_count": 0}},
        accepted=True,
    )
    ev = engine.evaluate_by_review_id(
        trade_id="t1", review_id=rid,
        trade_result={"status": "won", "r_multiple": 1.5, "market": "crypto", "timeframe": "4h", "symbol": "ETHUSDT"},
    )
    check("eval has failure_type", ev.get("failure_type") == "incorrect_disagreement")
    check("eval partial fields", ev.get("evaluation_type") is not None)

    rid2 = mem.save(
        package_id="p2", event_id="e2", prompt_version="v1", provider_id="claude",
        model_name="m", response={"agreement": "partial", "confidence": 58, "risks": [],
                                   "validation": {"hallucination_count": 0}},
        accepted=True,
    )
    ev2 = engine.evaluate_by_review_id(
        trade_id="t2", review_id=rid2,
        trade_result={"status": "lost", "r_multiple": -1, "market": "crypto", "timeframe": "4h"},
    )
    check("partial_on_loss eval", ev2.get("failure_type") == "partial_on_loss")
    check("partial not simply false correct", ev2.get("advisor_correct") is False)

# 17–19 lesson generator grouping
evals = [
    {"evaluation_id": "e1", "trade_id": "t1", "provider": "claude", "market": "crypto", "timeframe": "15m",
     "advisor_agreement": "disagree", "advisor_confidence": 72, "advisor_correct": False,
     "hallucination": False, "missed_warning": False, "false_warning": True,
     "trade_result": "WON", "r_multiple": 1.5, "symbol": "BTCUSDT"},
    {"evaluation_id": "e2", "trade_id": "t2", "provider": "claude", "market": "forex", "timeframe": "1h",
     "advisor_agreement": "disagree", "advisor_confidence": 80, "advisor_correct": False,
     "hallucination": False, "missed_warning": False, "false_warning": True,
     "trade_result": "WON", "r_multiple": 1.2, "symbol": "EURUSD"},
]
lessons = LessonGenerator().generate([], evals)
check("multiple markets lessons", len(lessons) >= 2)
check("no generic other when specific", all(l.get("failure_type") != "other_failure" for l in lessons if l.get("is_failure")))

# 20 backward compat — legacy lesson without fingerprint still lists
with tempfile.TemporaryDirectory() as tmp:
    repo = LessonRepository(Path(tmp) / "lessons.jsonl")
    repo.save({"title": "Legacy", "description": "old", "sample_size": 1, "pattern_type": "other_failure"})
    listed = repo.list_all()
    check("legacy readable", len(listed) == 1 and listed[0]["title"] == "Legacy")

# Full cycle upsert
with tempfile.TemporaryDirectory() as tmp:
    eval_path = Path(tmp) / "evals.jsonl"
    lesson_path = Path(tmp) / "lessons.jsonl"
    ds = AdvisorEvaluationDataset(eval_path)
    for e in evals:
        ds.save(e)
    eng = LearningEngine(
        dataset=ds,
        lessons=LessonRepository(lesson_path),
        history=LearningHistory(Path(tmp) / "hist"),
    )
    eng.run_cycle(scope={"last_n": 10})
    eng.run_cycle(scope={"last_n": 10})
    repo = LessonRepository(lesson_path)
    check("cycle dedup count", repo.count() <= len(evals) + 2)

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*60}")
print(f"AIA-05.5 Learning Tests: {passed}/{len(results)} passed")
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
print("\nAll AIA-05.5 tests passed.")
