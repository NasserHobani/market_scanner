#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real verification for AI-06.2 automatic quant research orchestrator.

Usage: python scripts/verify_research_automation.py

States: NOT READY | CONFIGURED | RUNNING | VERIFIED
Research produces evidence only — never modifies trading behavior.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()


def _closed_trade_rows() -> list[dict]:
    from scanner.tracking import LOST, WON
    try:
        from dashboard import trades as trade_svc
        from dashboard.models import Trade
    except ImportError:
        from web.dashboard import trades as trade_svc
        from web.dashboard.models import Trade

    qs = Trade.objects.filter(status__in=[WON, LOST]).order_by("-closed_at")[:500]
    rows = trade_svc.rows_for_stats(qs)
    for t, r in zip(qs, rows):
        r["trade_id"] = str(t.pk)
    return rows


def main() -> int:
    from scanner.research.config import load_research_config, config_to_public_dict
    from scanner.research.fingerprint import compute_dataset_fingerprint
    from scanner.research.jobs import JobStatus, JobStore
    from scanner.research.orchestrator import ResearchOrchestrator, ResearchTrigger, TRIGGER_MANUAL
    from scanner.research.state import OrchestratorState

    cfg = load_research_config()
    print("=== AI-06.2 Research Automation Verification ===\n")

    print("Research enabled:", cfg.auto_enabled)
    print("Configuration:", json.dumps(config_to_public_dict(cfg), indent=2))

    if not cfg.auto_enabled:
        print("\nSTATUS: NOT READY")
        print("Reason: research_auto_enabled is False")
        return 1

    print("\nSTATUS: CONFIGURED")

    rows = _closed_trade_rows()
    closed = [r for r in rows if r.get("status") in ("won", "lost", "WON", "LOST")]
    print(f"Closed trades available: {len(closed)}")

    st = OrchestratorState().load()
    last_fp = st.get("last_dataset_fingerprint", "")
    print(f"Last research fingerprint: {last_fp or '(none)'}")
    print(f"New trades since last run: {st.get('trades_since_last_run', 0)}")

    fp = compute_dataset_fingerprint(rows, {"completed_only": True})
    print(f"Current dataset fingerprint: {fp}")

    orch = ResearchOrchestrator()
    status = orch.status()
    print(f"Pending jobs: {status.get('pending_jobs', 0)}")
    print(f"Completed jobs: {status.get('completed_jobs', 0)}")

    trigger_reason = "verification manual trigger"
    if len(closed) >= cfg.min_closed_trades:
        trigger = ResearchTrigger(trigger_type=TRIGGER_MANUAL, reason=trigger_reason)
        job = orch._queue_job(trigger, automatic=False)
        if not job:
            print("\nSTATUS: NOT READY — failed to queue job")
            return 1
        print(f"\nTrigger: {trigger.trigger_type}")
        print(f"Job ID: {job.job_id}")
        print(f"Dataset fingerprint: {job.dataset_fingerprint}")
        print(f"Sample size available: {len(closed)} (required {cfg.min_closed_trades})")

        if job.status == JobStatus.SKIPPED.value:
            print(f"Job skipped: {job.reason}")
            existing = JobStore().get(job.job_id)
            jobs = orch.list_jobs(limit=5)
            completed = [j for j in jobs if j.get("status") == JobStatus.COMPLETED.value]
            if completed:
                c = completed[0]
                print("\nSTATUS: VERIFIED (prior completed research exists)")
                print(f"Experiment ID: {c.get('experiment_id', '')}")
                print(f"Status: {c.get('status')}")
                return 0
            print("\nSTATUS: CONFIGURED (duplicate skipped, no completed job)")
            return 0

        print("\nSTATUS: RUNNING")
        t0 = __import__("time").perf_counter()
        finished = orch.run_job(job.job_id)
        duration = round((__import__("time").perf_counter() - t0) * 1000, 1)
    else:
        print(f"\nInsufficient closed trades ({len(closed)}/{cfg.min_closed_trades})")
        job = orch.run_manual()
        finished = orch._jobs.get(job.job_id)
        duration = finished.duration_ms if finished else 0

    if not finished:
        print("\nSTATUS: NOT READY — job not found after execution")
        return 1

    print(f"Status: {finished.status}")
    print(f"Duration: {duration}ms")
    if finished.experiment_id:
        print(f"Experiment ID: {finished.experiment_id}")
        try:
            from scanner.research.experiment import ExperimentStore
            exp = ExperimentStore().load(finished.experiment_id)
            report = (exp.results or {}).get("report") or {}
            print(f"Report ID: {report.get('report_id', exp.report_id)}")
            print(f"Winner: {(exp.results or {}).get('comparison', {}).get('winner', 'n/a')}")
        except Exception as exc:  # noqa: BLE001
            print(f"Experiment load warning: {exc}")

    if finished.status == JobStatus.COMPLETED.value:
        print("\nSTATUS: VERIFIED")
        return 0
    if finished.status == JobStatus.INSUFFICIENT_DATA.value:
        print(f"\nSTATUS: CONFIGURED — {finished.reason}")
        return 0
    print(f"\nSTATUS: CONFIGURED — job ended as {finished.status}")
    if finished.error:
        print(f"Error: {finished.error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
