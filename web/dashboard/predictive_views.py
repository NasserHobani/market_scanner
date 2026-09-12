# -*- coding: utf-8 -*-
"""Prediction training REST API — AIA-07 / AIA-12."""
from __future__ import annotations

import json

from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from scanner.predictive.config import config_to_public_dict
from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator


@require_GET
def api_prediction_status(request):
    orch = PredictionTrainingOrchestrator()
    return JsonResponse({"ok": True, **orch.status(), "config": config_to_public_dict()})


@require_GET
def api_prediction_readiness(request):
    """AIA-12 Dataset V3 readiness — continuous accumulation status."""
    try:
        from scanner.predictive.dataset_readiness import build_readiness
        payload = build_readiness(persist=True)
        return JsonResponse({"ok": True, **payload})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)[:300]}, status=500)


@require_GET
def api_prediction_jobs(request):
    from scanner.predictive.training_jobs import TrainingJobStore
    limit = min(100, max(1, int(request.GET.get("limit", 20))))
    jobs = [j.to_dict() for j in TrainingJobStore().list_all()[:limit]]
    return JsonResponse({"ok": True, "jobs": jobs, "count": len(jobs)})


@require_POST
def api_prediction_train(request):
    """Manual train — V2 orchestrator + forced V3 evaluate (never auto-promote)."""
    try:
        job = PredictionTrainingOrchestrator().run_manual()
        from scanner.predictive.v3_retrain import maybe_trigger_v3_retrain
        v3_out = maybe_trigger_v3_retrain(force=True)
        return JsonResponse({
            "ok": True,
            "job": job.to_dict(),
            "v3": v3_out,
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)[:300]}, status=500)


@require_POST
def api_prediction_promote(request, model_id: str):
    result = PredictionTrainingOrchestrator().promote_model(model_id)
    code = 200 if result.get("ok") else 400
    return JsonResponse({"ok": result.get("ok", False), **result}, status=code)
