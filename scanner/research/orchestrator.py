# -*- coding: utf-8 -*-
"""Research orchestrator — automatic quant research triggers (AI-06.2)."""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

from scanner.tracking import LOST, WON

from .config import ResearchOrchestratorConfig, load_research_config
from .fingerprint import compute_dataset_fingerprint
from .hypothesis import Hypothesis
from .jobs import JobStatus, JobStore, LOCK_PATH, ResearchJob, new_job_id
from .services import ResearchService
from .state import OrchestratorState

log = logging.getLogger("scanner.research.orchestrator")

TRIGGER_TRADE_COUNT = "trade_count"
TRIGGER_SCHEDULED = "scheduled"
TRIGGER_LEARNING_HYPOTHESIS = "learning_hypothesis"
TRIGGER_RECURRING_FAILURE = "recurring_failure"
TRIGGER_REGIME_CHANGE = "regime_change"
TRIGGER_MANUAL = "manual"

FAILURE_PATTERN_TYPES = frozenset({
    "wrong_agreement", "missed_warning", "partial_on_loss",
    "incorrect_disagreement", "hallucination", "high_confidence_wrong",
})

PATTERN_TO_FILTER = {
    "timeframe_specific_failure": ("timeframe", "timeframe"),
    "strategy_specific_failure": ("factor", "htf"),
    "wrong_agreement": ("factor", "htf"),
    "missed_warning": ("factor", "confluence"),
    "partial_on_loss": ("factor", "htf"),
    "incorrect_disagreement": ("factor", "htf"),
    "hallucination": ("factor", "confluence"),
    "low_liquidity_failure": ("factor", "sweep"),
}


@dataclass(frozen=True)
class ResearchTrigger:
    trigger_type: str
    reason: str
    hypothesis_id: str = ""
    configuration: dict[str, Any] | None = None
    priority: int = 50


class ResearchOrchestrator:
    """Queue and run research jobs — never blocks trade settlement."""

    def __init__(self,
                 config: ResearchOrchestratorConfig | None = None,
                 jobs: JobStore | None = None,
                 state: OrchestratorState | None = None,
                 service: ResearchService | None = None,
                 rows_provider: Callable[[], list[dict]] | None = None) -> None:
        self._cfg = config or load_research_config()
        self._jobs = jobs or JobStore()
        self._state = state or OrchestratorState()
        self._service = service or ResearchService()
        self._rows_provider = rows_provider
        self._lock = threading.Lock()
        self._worker_started = False

    # ── Trade settlement hook ─────────────────────────────────────────────

    def on_trade_closed(self, trade: Any) -> dict[str, Any] | None:
        """Called after trade settlement — non-blocking, queues research only."""
        if not self._cfg.auto_enabled:
            return None
        try:
            count = self._state.increment_trade_counter()
            triggers = self._inspect_triggers(trade=trade, new_trade_count=count)
            queued = []
            for trig in triggers:
                job = self._queue_job(trig, automatic=True)
                if job:
                    queued.append(job.job_id)
            self._maybe_start_worker()
            return {"queued_jobs": queued, "trades_since_last_run": count} if queued else None
        except Exception as exc:  # noqa: BLE001
            log.warning("research orchestrator on_trade_closed: %s", str(exc)[:200])
            return None

    # ── Scheduled entry point ─────────────────────────────────────────────

    def run_scheduled_research(self) -> list[ResearchJob]:
        if not self._cfg.auto_enabled or not self._cfg.weekly_enabled:
            return []
        st = self._state.load()
        last = st.get("weekly_last_run_at") or ""
        if last:
            try:
                prev = datetime.fromisoformat(last.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - prev < timedelta(days=7):
                    return []
            except ValueError:
                pass

        triggers = self._weekly_triggers()
        results = []
        for trig in triggers:
            job = self._queue_job(trig, automatic=True)
            if job:
                results.append(job)
        data = self._state.load()
        data["weekly_last_run_at"] = datetime.now(timezone.utc).isoformat()
        self._state.save(data)
        self._maybe_start_worker()
        return results

    # ── Manual trigger ────────────────────────────────────────────────────

    def run_manual(self, *, configuration: dict[str, Any] | None = None) -> ResearchJob:
        trig = ResearchTrigger(
            trigger_type=TRIGGER_MANUAL,
            reason="Manual research trigger",
            configuration=configuration or {},
            priority=100,
        )
        job = self._queue_job(trig, automatic=False)
        if not job:
            raise RuntimeError("failed to queue manual research job")
        self._execute_job(job.job_id)
        return self._jobs.get(job.job_id) or job

    def run_job(self, job_id: str) -> ResearchJob | None:
        return self._execute_job(job_id)

    # ── Status ────────────────────────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        cfg = self._cfg
        st = self._state.load()
        counts = self._jobs.count_by_status()
        jobs = self._jobs.list_all()
        last_completed = next(
            (j for j in jobs if j.status == JobStatus.COMPLETED.value), None)
        pending = counts.get(JobStatus.PENDING.value, 0)
        running = counts.get(JobStatus.RUNNING.value, 0)
        next_weekly = ""
        if st.get("weekly_last_run_at"):
            try:
                prev = datetime.fromisoformat(
                    st["weekly_last_run_at"].replace("Z", "+00:00"))
                next_weekly = (prev + timedelta(days=7)).isoformat()
            except ValueError:
                pass
        return {
            "enabled": cfg.auto_enabled,
            "pending_jobs": pending,
            "running_jobs": running,
            "completed_jobs": counts.get(JobStatus.COMPLETED.value, 0),
            "skipped_jobs": counts.get(JobStatus.SKIPPED.value, 0),
            "insufficient_data_jobs": counts.get(JobStatus.INSUFFICIENT_DATA.value, 0),
            "failed_jobs": counts.get(JobStatus.FAILED.value, 0),
            "last_run": st.get("last_run_at", ""),
            "next_scheduled_run": next_weekly,
            "new_trades_since_last_run": int(st.get("trades_since_last_run") or 0),
            "min_new_trades": cfg.min_new_trades,
            "last_dataset_fingerprint": st.get("last_dataset_fingerprint", ""),
            "last_experiment_id": st.get("last_experiment_id", ""),
            "latest_job": jobs[0].to_dict() if jobs else None,
            "config": {
                "weekly_enabled": cfg.weekly_enabled,
                "hypothesis_enabled": cfg.hypothesis_enabled,
                "failure_threshold": cfg.failure_threshold,
                "min_closed_trades": cfg.min_closed_trades,
            },
        }

    def list_jobs(self, *, limit: int = 50) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._jobs.list_all()[:limit]]

    def ui_model(self) -> dict[str, Any]:
        """Dashboard model for Quant Research Lab automation panel."""
        st = self._state.load()
        jobs = self._jobs.list_all()
        cfg = self._cfg
        automatic = sum(1 for j in jobs if j.automatic and j.status == JobStatus.COMPLETED.value)
        manual = sum(1 for j in jobs if not j.automatic and j.status == JobStatus.COMPLETED.value)
        latest_completed = next(
            (j for j in jobs if j.status == JobStatus.COMPLETED.value), None)
        latest_running = next(
            (j for j in jobs if j.status == JobStatus.RUNNING.value), None)
        latest_pending = next(
            (j for j in jobs if j.status == JobStatus.PENDING.value), None)
        active = latest_running or latest_pending

        latest_hypothesis = ""
        try:
            from scanner.ai_learning.learning_history import LearningHistory
            hyps = LearningHistory().list_hypotheses()
            if hyps:
                latest_hypothesis = hyps[-1].get("statement", "") or hyps[-1].get("title", "")
        except Exception:  # noqa: BLE001
            pass

        latest_result = ""
        if latest_completed and latest_completed.experiment_id:
            try:
                exp = self._service.load_experiment(latest_completed.experiment_id)
                comparison = (exp.results or {}).get("comparison") or {}
                latest_result = comparison.get("winner", "") or "no edge"
            except Exception:  # noqa: BLE001
                latest_result = latest_completed.status.lower()
        elif jobs:
            insuf = next((j for j in jobs if j.status == JobStatus.INSUFFICIENT_DATA.value), None)
            if insuf:
                latest_result = f"insufficient data ({insuf.reason})"

        progress_stages = [
            "queued", "dataset", "hypothesis", "metrics", "comparison", "report", "completed",
        ]
        stage = ""
        if active:
            stage = active.progress_stage or (
                "queued" if active.status == JobStatus.PENDING.value else "dataset"
            )

        return {
            "automatic_research_on": cfg.auto_enabled,
            "last_research_at": st.get("last_run_at", ""),
            "new_trades": int(st.get("trades_since_last_run") or 0),
            "new_trades_threshold": cfg.min_new_trades,
            "pending_jobs": sum(1 for j in jobs if j.status == JobStatus.PENDING.value),
            "completed_jobs": sum(1 for j in jobs if j.status == JobStatus.COMPLETED.value),
            "automatic_research_count": automatic,
            "manual_research_count": manual,
            "latest_experiment_id": st.get("last_experiment_id", ""),
            "latest_hypothesis": latest_hypothesis,
            "latest_result": latest_result,
            "latest_dataset_fingerprint": st.get("last_dataset_fingerprint", ""),
            "active_job_id": active.job_id if active else "",
            "active_job_status": active.status if active else "",
            "progress_stage": stage,
            "progress_stages": progress_stages,
            "progress_index": progress_stages.index(stage) if stage in progress_stages else -1,
        }

    # ── Trigger inspection ────────────────────────────────────────────────

    def _inspect_triggers(self, *, trade: Any = None,
                          new_trade_count: int = 0) -> list[ResearchTrigger]:
        triggers: list[ResearchTrigger] = []
        if new_trade_count >= self._cfg.min_new_trades:
            triggers.append(ResearchTrigger(
                trigger_type=TRIGGER_TRADE_COUNT,
                reason=f"{new_trade_count} closed trades since last research",
                priority=60,
            ))
        if self._cfg.hypothesis_enabled:
            triggers.extend(self._learning_hypothesis_triggers())
        triggers.extend(self._recurring_failure_triggers())
        return triggers

    def _weekly_triggers(self) -> list[ResearchTrigger]:
        rows = self._get_rows()
        if len([r for r in rows if r.get("status") in (WON, LOST)]) < self._cfg.min_closed_trades:
            return [ResearchTrigger(
                trigger_type=TRIGGER_SCHEDULED,
                reason="Weekly research — may have insufficient data",
                priority=40,
            )]
        return [ResearchTrigger(
            trigger_type=TRIGGER_SCHEDULED,
            reason="Weekly scheduled research",
            priority=40,
        )]

    def _learning_hypothesis_triggers(self) -> list[ResearchTrigger]:
        from scanner.ai_learning.learning_history import LearningHistory

        st = self._state.load()
        processed = set(st.get("processed_hypothesis_ids") or [])
        triggers = []
        for hyp in LearningHistory().list_hypotheses():
            hid = hyp.get("hypothesis_id", "")
            if not hid or hid in processed:
                continue
            conf = float(hyp.get("confidence") or 0)
            if conf < self._cfg.hypothesis_min_confidence:
                continue
            triggers.append(ResearchTrigger(
                trigger_type=TRIGGER_LEARNING_HYPOTHESIS,
                reason=hyp.get("statement", "Learning hypothesis"),
                hypothesis_id=hid,
                configuration={"learning_hypothesis": hyp},
                priority=70,
            ))
        return triggers[:3]

    def _recurring_failure_triggers(self) -> list[ResearchTrigger]:
        from scanner.ai_advisor.evaluation.advisor_dataset import AdvisorEvaluationDataset

        st = self._state.load()
        processed = set(st.get("processed_failure_patterns") or [])
        evals = AdvisorEvaluationDataset().list_all()
        counts: dict[str, int] = {}
        for e in evals:
            ft = e.get("failure_type") or ""
            if ft in FAILURE_PATTERN_TYPES:
                counts[ft] = counts.get(ft, 0) + 1

        triggers = []
        for ft, n in counts.items():
            key = f"{ft}:{n}"
            if n >= self._cfg.failure_threshold and key not in processed:
                triggers.append(ResearchTrigger(
                    trigger_type=TRIGGER_RECURRING_FAILURE,
                    reason=f"Recurring {ft} pattern ({n} samples)",
                    configuration={"failure_type": ft, "sample_count": n},
                    priority=65,
                ))
        return triggers[:2]

    # ── Job queue / execution ─────────────────────────────────────────────

    def _queue_job(self, trigger: ResearchTrigger,
                   *, automatic: bool) -> ResearchJob | None:
        rows = self._get_rows()
        dataset_config = {"completed_only": True}
        if trigger.configuration:
            dataset_config.update({
                k: v for k, v in trigger.configuration.items()
                if k in ("market", "timeframe", "factor", "regime")
            })
        hypothesis_id = trigger.hypothesis_id or ""
        fp = compute_dataset_fingerprint(
            rows, dataset_config, hypothesis_id=hypothesis_id)
        configuration = {
            "trigger": trigger.trigger_type,
            "reason": trigger.reason,
            "dataset_config": dataset_config,
            "strategy_key": "default",
            **(trigger.configuration or {}),
        }

        dup = self._jobs.find_duplicate(
            hypothesis_id=hypothesis_id, fingerprint=fp, configuration=configuration)
        if dup:
            job = ResearchJob(
                job_id=new_job_id(),
                trigger_type=trigger.trigger_type,
                status=JobStatus.SKIPPED.value,
                hypothesis_id=hypothesis_id,
                dataset_fingerprint=fp,
                reason="identical research already executed",
                configuration=configuration,
                automatic=automatic,
            )
            self._jobs.append(job)
            return job

        last_fp = self._state.load().get("last_dataset_fingerprint", "")
        if (last_fp and fp == last_fp
                and trigger.trigger_type in (TRIGGER_TRADE_COUNT, TRIGGER_SCHEDULED)):
            job = ResearchJob(
                job_id=new_job_id(),
                trigger_type=trigger.trigger_type,
                status=JobStatus.SKIPPED.value,
                hypothesis_id=hypothesis_id,
                dataset_fingerprint=fp,
                reason="dataset fingerprint unchanged since last research",
                configuration=configuration,
                automatic=automatic,
            )
            self._jobs.append(job)
            return job

        if self._jobs.running_for_strategy("default"):
            job = ResearchJob(
                job_id=new_job_id(),
                trigger_type=trigger.trigger_type,
                status=JobStatus.PENDING.value,
                hypothesis_id=hypothesis_id,
                dataset_fingerprint=fp,
                configuration=configuration,
                reason=trigger.reason,
                automatic=automatic,
            )
            self._jobs.append(job)
            return job

        job = ResearchJob(
            job_id=new_job_id(),
            trigger_type=trigger.trigger_type,
            status=JobStatus.PENDING.value,
            hypothesis_id=hypothesis_id,
            dataset_fingerprint=fp,
            configuration=configuration,
            reason=trigger.reason,
            automatic=automatic,
        )
        self._jobs.append(job)
        return job

    def _maybe_start_worker(self) -> None:
        with self._lock:
            if self._worker_started:
                return
            self._worker_started = True
        t = threading.Thread(target=self._process_pending, daemon=True)
        t.start()

    def _process_pending(self) -> None:
        try:
            for job in self._jobs.list_all():
                if job.status == JobStatus.PENDING.value:
                    self._execute_job(job.job_id)
        finally:
            with self._lock:
                self._worker_started = False

    def _execute_job(self, job_id: str) -> ResearchJob | None:
        job = self._jobs.get(job_id)
        if not job or job.status not in (
            JobStatus.PENDING.value, JobStatus.RUNNING.value,
        ):
            return job

        if not self._acquire_lock():
            return job

        start = time.monotonic()
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc).isoformat()
        job.progress_stage = "dataset"
        self._jobs.update(job)

        try:
            rows = self._get_rows()
            dataset_config = dict(job.configuration.get("dataset_config") or {})
            dataset_config.setdefault("completed_only", True)
            closed = [r for r in rows if r.get("status") in (WON, LOST)]

            required = self._cfg.min_closed_trades
            available = len(closed)
            job.sample_counts = {"required": required, "available": available}
            if available < required:
                job.status = JobStatus.INSUFFICIENT_DATA.value
                job.reason = f"{available}/{required} closed trades available"
                job.progress_stage = "completed"
                job.completed_at = datetime.now(timezone.utc).isoformat()
                job.duration_ms = round((time.monotonic() - start) * 1000, 1)
                self._jobs.update(job)
                return job

            job.progress_stage = "hypothesis"
            hypothesis = self._build_hypothesis(job)

            if hypothesis:
                from .hypothesis import HypothesisEngine
                engine = HypothesisEngine()
                treatment, baseline = engine.split(closed, hypothesis)
                if (len(treatment) < self._cfg.min_group_size
                        or len(baseline) < self._cfg.min_comparison_size):
                    log.info(
                        "hypothesis split insufficient (%d/%d) — falling back to baseline experiment",
                        len(treatment), len(baseline),
                    )
                    hypothesis = None

            job.progress_stage = "metrics"
            title = self._experiment_title(job)
            description = (
                f"Automatically triggered — {job.trigger_type}"
                if job.automatic else f"Manually triggered — {job.trigger_type}"
            )
            configuration = {
                **job.configuration,
                "trigger_type": job.trigger_type,
                "automatic": job.automatic,
                "job_id": job.job_id,
            }

            job.progress_stage = "comparison"
            experiment = self._service.run_experiment(
                title=title,
                rows=closed,
                hypothesis=hypothesis,
                description=description,
                dataset_config=dataset_config,
                configuration=configuration,
            )

            job.progress_stage = "report"
            job.experiment_id = experiment.experiment_id
            job.status = JobStatus.COMPLETED.value
            job.progress_stage = "completed"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._jobs.update(job)

            self._state.reset_trade_counter(
                fingerprint=job.dataset_fingerprint,
                experiment_id=experiment.experiment_id,
            )
            self._mark_processed(job)
            self._feed_learning(experiment, job)
            return job

        except Exception as exc:  # noqa: BLE001
            job.status = JobStatus.FAILED.value
            job.error = str(exc)[:300]
            job.progress_stage = "completed"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.duration_ms = round((time.monotonic() - start) * 1000, 1)
            self._jobs.update(job)
            log.warning("research job %s failed: %s", job_id, job.error)
            return job
        finally:
            self._release_lock()

    def _build_hypothesis(self, job: ResearchJob) -> Hypothesis | None:
        cfg = job.configuration
        if job.trigger_type == TRIGGER_LEARNING_HYPOTHESIS:
            hyp = cfg.get("learning_hypothesis") or {}
            ptype = hyp.get("pattern_type", "")
            return self._hypothesis_from_pattern(ptype, hyp)
        if job.trigger_type == TRIGGER_RECURRING_FAILURE:
            ft = cfg.get("failure_type", "wrong_agreement")
            return self._hypothesis_from_pattern(ft, cfg)
        if job.trigger_type in (TRIGGER_TRADE_COUNT, TRIGGER_SCHEDULED, TRIGGER_MANUAL):
            return Hypothesis(
                hypothesis_id=f"hyp_auto_{job.job_id[-8:]}",
                title="HTF factor improves expectancy",
                description=job.reason,
                filter_type="factor",
                filter_key="htf",
                filter_value="htf",
                treatment_label="with_htf",
                baseline_label="without_htf",
            )
        return None

    def _hypothesis_from_pattern(self, pattern_type: str,
                                 source: dict[str, Any]) -> Hypothesis | None:
        mapping = PATTERN_TO_FILTER.get(pattern_type)
        if not mapping:
            return Hypothesis(
                hypothesis_id=source.get("hypothesis_id", f"hyp_{pattern_type}"),
                title=source.get("statement", pattern_type),
                description=f"Validate pattern: {pattern_type}",
                filter_type="factor",
                filter_key="htf",
                filter_value="htf",
            )
        ft, key = mapping
        val = source.get("filter_value")
        if ft == "timeframe":
            tfs = source.get("affected_timeframes") or []
            val = tfs[0] if tfs else source.get("timeframe", "4h")
        elif not val:
            val = key
        return Hypothesis(
            hypothesis_id=source.get("hypothesis_id", f"hyp_{pattern_type}"),
            title=source.get("statement", pattern_type),
            description=f"Hypothesis validation: {pattern_type}",
            filter_type=ft,
            filter_key=key if ft == "factor" else ft,
            filter_value=val,
        )

    @staticmethod
    def _experiment_title(job: ResearchJob) -> str:
        return {
            TRIGGER_TRADE_COUNT: "Auto: trade-count research",
            TRIGGER_SCHEDULED: "Auto: weekly research",
            TRIGGER_LEARNING_HYPOTHESIS: "Auto: learning hypothesis validation",
            TRIGGER_RECURRING_FAILURE: "Auto: recurring failure analysis",
            TRIGGER_MANUAL: "Manual research experiment",
        }.get(job.trigger_type, f"Research: {job.trigger_type}")

    def _mark_processed(self, job: ResearchJob) -> None:
        data = self._state.load()
        if job.hypothesis_id:
            ids = list(data.get("processed_hypothesis_ids") or [])
            if job.hypothesis_id not in ids:
                ids.append(job.hypothesis_id)
            data["processed_hypothesis_ids"] = ids[-200:]
        if job.trigger_type == TRIGGER_RECURRING_FAILURE:
            ft = job.configuration.get("failure_type", "")
            n = job.configuration.get("sample_count", 0)
            patterns = list(data.get("processed_failure_patterns") or [])
            patterns.append(f"{ft}:{n}")
            data["processed_failure_patterns"] = patterns[-100:]
        self._state.save(data)

    def _feed_learning(self, experiment: Any, job: ResearchJob) -> None:
        """Research → Learning loop — advisory only, no infinite re-trigger."""
        try:
            from scanner.ai_learning.learning_history import LearningHistory

            results = experiment.results or {}
            comparison = results.get("comparison") or {}
            LearningHistory().save_report({
                "source": "research_orchestrator",
                "experiment_id": experiment.experiment_id,
                "job_id": job.job_id,
                "trigger_type": job.trigger_type,
                "automatic": job.automatic,
                "winner": comparison.get("winner", ""),
                "dataset_fingerprint": job.dataset_fingerprint,
                "hypothesis_id": job.hypothesis_id,
            })
        except Exception as exc:  # noqa: BLE001
            log.debug("research→learning feed skipped: %s", str(exc)[:120])

    def _get_rows(self) -> list[dict[str, Any]]:
        if self._rows_provider:
            return self._rows_provider()
        try:
            from dashboard import trades as trade_svc
            from dashboard.models import Trade
            from scanner.tracking import WON as W
            qs = Trade.objects.filter(status__in=[W, LOST]).order_by("-closed_at")[:500]
            rows = trade_svc.rows_for_stats(qs)
            for t, r in zip(qs, rows):
                r["trade_id"] = str(t.pk)
            return rows
        except Exception:  # noqa: BLE001
            try:
                from web.dashboard import trades as trade_svc
                from web.dashboard.models import Trade
                from scanner.tracking import WON as W
                qs = Trade.objects.filter(status__in=[W, LOST]).order_by("-closed_at")[:500]
                rows = trade_svc.rows_for_stats(qs)
                for t, r in zip(qs, rows):
                    r["trade_id"] = str(t.pk)
                return rows
            except Exception:  # noqa: BLE001
                return []

    @staticmethod
    def _acquire_lock() -> bool:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        if LOCK_PATH.exists():
            return False
        try:
            LOCK_PATH.write_text(
                json.dumps({"pid": "orchestrator", "at": datetime.now(timezone.utc).isoformat()}),
                encoding="utf-8",
            )
            return True
        except OSError:
            return False

    @staticmethod
    def _release_lock() -> None:
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except OSError:
            pass
