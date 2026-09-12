# -*- coding: utf-8 -*-
"""Research orchestrator REST API — automatic quant research (AI-06.2)."""
from __future__ import annotations

import json

from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from scanner.research.config import config_to_public_dict, load_research_config
from scanner.research.orchestrator import ResearchOrchestrator


def _orchestrator() -> ResearchOrchestrator:
    return ResearchOrchestrator()


@require_GET
def api_research_status(request):
    """GET /api/research/status/ — orchestrator status and observability."""
    orch = _orchestrator()
    payload = orch.status()
    ui = orch.ui_model()
    return JsonResponse({
        "ok": True,
        "enabled": payload.get("enabled", False),
        "pending_jobs": payload.get("pending_jobs", 0),
        "running_jobs": payload.get("running_jobs", 0),
        "completed_jobs": payload.get("completed_jobs", 0),
        "last_run": payload.get("last_run", ""),
        "next_scheduled_run": payload.get("next_scheduled_run", ""),
        "new_trades_since_last_run": payload.get("new_trades_since_last_run", 0),
        "config": config_to_public_dict(load_research_config()),
        "observability": {
            "skipped_jobs": payload.get("skipped_jobs", 0),
            "insufficient_data_jobs": payload.get("insufficient_data_jobs", 0),
            "failed_jobs": payload.get("failed_jobs", 0),
            "automatic_research_count": ui.get("automatic_research_count", 0),
            "manual_research_count": ui.get("manual_research_count", 0),
            "last_experiment_id": payload.get("last_experiment_id", ""),
            "last_dataset_fingerprint": payload.get("last_dataset_fingerprint", ""),
            "latest_hypothesis": ui.get("latest_hypothesis"),
            "latest_result": ui.get("latest_result"),
            "latest_job": payload.get("latest_job"),
        },
        "ui": ui,
    })


@require_GET
def api_research_jobs(request):
    """GET /api/research/jobs/ — persisted research jobs."""
    limit = min(200, max(1, int(request.GET.get("limit", 50))))
    jobs = _orchestrator().list_jobs(limit=limit)
    return JsonResponse({"ok": True, "jobs": jobs, "count": len(jobs)})


@require_POST
def api_research_run(request):
    """POST /api/research/run/ — manual research trigger."""
    configuration = {}
    if request.body:
        try:
            configuration = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "invalid JSON body"}, status=400)
    try:
        job = _orchestrator().run_manual(configuration=configuration)
        return JsonResponse({"ok": True, "job": job.to_dict()})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)[:300]}, status=500)


@require_POST
def api_research_run_job(request, job_id: str):
    """POST /api/research/run/<job_id>/ — execute a queued job."""
    job = _orchestrator().run_job(job_id)
    if not job:
        return JsonResponse({"ok": False, "error": "job not found"}, status=404)
    return JsonResponse({"ok": True, "job": job.to_dict()})
