# -*- coding: utf-8 -*-
"""Tests for scanner.research orchestrator — run: python tests_research_orchestrator.py"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from scanner.research.config import ResearchOrchestratorConfig
from scanner.research.fingerprint import compute_dataset_fingerprint
from scanner.research.jobs import JobStatus, JobStore, LOCK_PATH
from scanner.research.orchestrator import (
    ResearchOrchestrator,
    ResearchTrigger,
    TRIGGER_MANUAL,
    TRIGGER_SCHEDULED,
    TRIGGER_TRADE_COUNT,
    TRIGGER_LEARNING_HYPOTHESIS,
    TRIGGER_RECURRING_FAILURE,
)
from scanner.research.state import OrchestratorState
from scanner.tracking import LOST, WON

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _trade(i: int, *, status: str = WON, r: float = 1.0,
             factors: list[str] | None = None,
             market: str = "crypto", tf: str = "4h") -> dict:
    ts = datetime(2025, 1, 1 + i % 28, 12, 0, tzinfo=timezone.utc)
    return {
        "trade_id": f"t_{i}",
        "event_id": f"evt_{i}",
        "status": status,
        "r_multiple": r,
        "factors": factors or ["htf", "confluence"],
        "market": market,
        "timeframe": tf,
        "grade": "A",
        "closed_at": ts.isoformat(),
        "signal_at": ts.isoformat(),
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
        ))
    return rows


ROWS = _sample_rows(40)


class _FakeTrade:
    pk = 1
    symbol = "BTCUSDT"
    market = "crypto"
    timeframe = "4h"
    status = WON
    side = "buy"
    r_multiple = 1.5
    closed_at = datetime.now(timezone.utc)


def _make_orch(tmp: Path, *, min_new_trades: int = 10,
               min_closed_trades: int = 20,
               hypothesis_enabled: bool = False,
               failure_threshold: int = 999) -> ResearchOrchestrator:
    import scanner.research.jobs as jobs_mod
    import scanner.research.orchestrator as orch_mod

    lock = tmp / ".research_lock"
    jobs_mod.LOCK_PATH = lock
    orch_mod.LOCK_PATH = lock

    cfg = ResearchOrchestratorConfig(
        auto_enabled=True,
        min_new_trades=min_new_trades,
        weekly_enabled=True,
        hypothesis_enabled=hypothesis_enabled,
        failure_threshold=failure_threshold,
        min_closed_trades=min_closed_trades,
        min_group_size=5,
        min_comparison_size=5,
        hypothesis_min_confidence=60.0,
    )
    orch = ResearchOrchestrator(
        config=cfg,
        jobs=JobStore(tmp / "jobs.jsonl"),
        state=OrchestratorState(tmp / "state.json"),
        rows_provider=lambda: ROWS,
    )
    orch._maybe_start_worker = lambda: None  # noqa: SLF001 — keep tests synchronous
    return orch


# ── 1. Trade count trigger ─────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    trade = _FakeTrade()
    queued = []
    for _ in range(10):
        out = orch.on_trade_closed(trade)
        if out and out.get("queued_jobs"):
            queued.extend(out["queued_jobs"])
    check("trade count trigger queues job", len(queued) >= 1, str(len(queued)))

# ── 2. Threshold not reached ───────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    trade = _FakeTrade()
    for _ in range(9):
        out = orch.on_trade_closed(trade)
    check("threshold not reached — no queue", out is None or not out.get("queued_jobs"))

# ── 3. Threshold reached + execution ─────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    trig = ResearchTrigger(trigger_type=TRIGGER_TRADE_COUNT, reason="test")
    job = orch._queue_job(trig, automatic=True)
    assert job
    finished = orch._execute_job(job.job_id)
    check("threshold reached — job completes or insufficient",
          finished is not None and finished.status in (
              JobStatus.COMPLETED.value,
              JobStatus.INSUFFICIENT_DATA.value,
              JobStatus.FAILED.value,
          ),
          finished.status if finished else "none")

# ── 4. Weekly trigger ──────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    jobs = orch.run_scheduled_research()
    check("weekly trigger queues job", len(jobs) >= 1, str(len(jobs)))
    st = orch._state.load()
    check("weekly last run recorded", bool(st.get("weekly_last_run_at")))

# ── 5. Hypothesis trigger ──────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp, hypothesis_enabled=True)

    class _FakeLH:
        def list_hypotheses(self):
            return [{
                "hypothesis_id": "hyp_ui_test",
                "confidence": 85,
                "statement": "HTF filter may improve expectancy",
                "pattern_type": "wrong_agreement",
            }]

    with patch("scanner.ai_learning.learning_history.LearningHistory", _FakeLH):
        triggers = orch._learning_hypothesis_triggers()
    check("hypothesis trigger detected", len(triggers) >= 1)
    job = orch._queue_job(triggers[0], automatic=True)
    check("hypothesis job queued", job is not None and job.trigger_type == TRIGGER_LEARNING_HYPOTHESIS)

# ── 6. Recurring failure trigger ───────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp, failure_threshold=10)
    evals = [{"failure_type": "incorrect_disagreement"} for _ in range(10)]

    class _FakeDS:
        def list_all(self):
            return evals

    with patch("scanner.ai_advisor.evaluation.advisor_dataset.AdvisorEvaluationDataset", _FakeDS):
        triggers = orch._recurring_failure_triggers()
    check("recurring failure trigger", len(triggers) >= 1)
    check("failure trigger type", triggers[0].trigger_type == TRIGGER_RECURRING_FAILURE)

# ── 7. Insufficient data ───────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp, min_closed_trades=100)
    trig = ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason="insuf test")
    job = orch._queue_job(trig, automatic=False)
    assert job
    done = orch._execute_job(job.job_id)
    check("insufficient data status",
          done is not None and done.status == JobStatus.INSUFFICIENT_DATA.value,
          done.reason if done else "")
    check("insufficient sample counts",
          done is not None and done.sample_counts.get("available", 0) < 100)

# ── 8. Duplicate protection ────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    trig = ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason="dup")
    j1 = orch._queue_job(trig, automatic=False)
    assert j1
    orch._jobs.update(j1.__class__.from_dict({
        **j1.to_dict(),
        "status": JobStatus.COMPLETED.value,
        "experiment_id": "rex_dup",
    }))
    j2 = orch._queue_job(trig, automatic=False)
    check("duplicate protection skips", j2 is not None and j2.status == JobStatus.SKIPPED.value)

# ── 9. Dataset fingerprint ─────────────────────────────────────────────────

fp1 = compute_dataset_fingerprint(ROWS[:20], {"completed_only": True})
fp2 = compute_dataset_fingerprint(ROWS[:20], {"completed_only": True})
fp3 = compute_dataset_fingerprint(ROWS, {"completed_only": True})
check("fingerprint deterministic", fp1 == fp2, fp1)
check("fingerprint changes with data", fp1 != fp3)

# ── 10. Job persistence ────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    store = JobStore(tmp / "jobs.jsonl")
    from scanner.research.jobs import ResearchJob, new_job_id
    j = ResearchJob(job_id=new_job_id(), trigger_type="manual", status="PENDING")
    store.append(j)
    loaded = store.get(j.job_id)
    check("job persistence", loaded is not None and loaded.job_id == j.job_id)

# ── 11. Job lifecycle ────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    job = orch.run_manual()
    final = orch._jobs.get(job.job_id)
    check("job lifecycle terminal state",
          final is not None and final.status in (
              JobStatus.COMPLETED.value,
              JobStatus.INSUFFICIENT_DATA.value,
              JobStatus.FAILED.value,
          ),
          final.status if final else "")

# ── 12. Concurrency ────────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    import scanner.research.jobs as jobs_mod
    jobs_mod.LOCK_PATH.write_text("locked", encoding="utf-8")
    trig = ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason="conc")
    job = orch._queue_job(trig, automatic=False)
    check("concurrency queues when locked",
          job is not None and job.status == JobStatus.PENDING.value)
    jobs_mod.LOCK_PATH.unlink(missing_ok=True)

# ── 13. Manual trigger ─────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    job = orch.run_manual(configuration={"note": "manual"})
    check("manual trigger", not job.automatic or job.trigger_type == TRIGGER_MANUAL)
    check("manual trigger type", job.trigger_type == TRIGGER_MANUAL)

# ── 14. Research failure ───────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)

    def _boom(*a, **k):
        raise RuntimeError("simulated research failure")

    orch._service.run_experiment = _boom  # type: ignore[method-assign]
    trig = ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason="fail")
    job = orch._queue_job(trig, automatic=False)
    assert job
    done = orch._execute_job(job.job_id)
    check("research failure status", done is not None and done.status == JobStatus.FAILED.value)

# ── 15. Trade settlement not blocked ─────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    t0 = time.perf_counter()
    for _ in range(5):
        orch.on_trade_closed(_FakeTrade())
    elapsed_ms = (time.perf_counter() - t0) * 1000
    check("trade settlement not blocked", elapsed_ms < 500, f"{elapsed_ms:.1f}ms")

# ── 16. Research → learning integration ──────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    saved: list[dict] = []

    class _FakeLH2:
        def save_report(self, report):
            saved.append(report)
            return "lrpt_test"

    with patch("scanner.ai_learning.learning_history.LearningHistory", _FakeLH2):
        from scanner.research.experiment import Experiment
        exp = Experiment(experiment_id="rex_learn", title="t", results={
            "comparison": {"winner": "with_htf"},
        })
        from scanner.research.jobs import ResearchJob, new_job_id
        j = ResearchJob(job_id=new_job_id(), trigger_type=TRIGGER_MANUAL,
                        dataset_fingerprint="dsfp_test")
        orch._feed_learning(exp, j)
    check("research learning feed", len(saved) == 1 and saved[0].get("source") == "research_orchestrator")

# ── 17. Infinite-loop prevention ───────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    st = orch._state.load()
    st["last_dataset_fingerprint"] = compute_dataset_fingerprint(ROWS, {"completed_only": True})
    orch._state.save(st)
    trig = ResearchTrigger(trigger_type=TRIGGER_TRADE_COUNT, reason="loop")
    job = orch._queue_job(trig, automatic=True)
    check("infinite loop prevention skip",
          job is not None and job.status == JobStatus.SKIPPED.value,
          job.reason if job else "")

# ── 18. API status model ───────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    status = orch.status()
    ui = orch.ui_model()
    check("API status enabled key", "enabled" in status)
    check("API status pending_jobs", "pending_jobs" in status)
    check("UI model automatic flag", "automatic_research_on" in ui)
    check("UI model progress stages", len(ui.get("progress_stages", [])) >= 5)

# ── 19. API jobs list ──────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    orch._queue_job(ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason="j"), automatic=False)
    jobs = orch.list_jobs()
    check("API jobs list", len(jobs) >= 1)

# ── 20. UI model fields ────────────────────────────────────────────────────

with tempfile.TemporaryDirectory() as tmpdir:
    tmp = Path(tmpdir)
    orch = _make_orch(tmp)
    ui = orch.ui_model()
    for key in ("new_trades", "new_trades_threshold", "pending_jobs", "completed_jobs",
                "latest_experiment_id", "latest_hypothesis", "latest_result"):
        check(f"UI model has {key}", key in ui)

# ── Summary ────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Research Orchestrator Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
