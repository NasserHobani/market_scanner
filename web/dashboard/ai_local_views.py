# -*- coding: utf-8 -*-
"""Local AI REST API — Ollama health, models, leaderboard (AIA-06)."""
from __future__ import annotations

from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from scanner.ai_local.benchmark import build_leaderboard, recent_comparisons
from scanner.ai_local.config import local_config_to_public_dict, load_local_config
from scanner.ai_local.health import check_ollama_health, test_ollama_connection
from scanner.ai_local.metrics import compute_metrics
from scanner.ai_local.model_registry import list_models
from scanner.ai_local.runtime import status_payload


@require_GET
def api_ai_local_health(request):
  """GET /api/ai/local/health/ — runtime availability, not config alone."""
  cfg = load_local_config()
  health = check_ollama_health(cfg)
  return JsonResponse({
      "ok": True,
      "enabled": cfg.local_enabled and cfg.ollama_enabled,
      "ollama_reachable": health.get("ollama_reachable", False),
      "model_available": health.get("model_available", False),
      "base_url": health.get("base_url"),
      "default_model": health.get("default_model"),
      "models": health.get("models", []),
      "error": health.get("error", ""),
      "execution_mode": cfg.execution_mode,
      "config": local_config_to_public_dict(cfg),
  })


@require_POST
def api_ai_local_test(request):
  """Test Ollama connectivity and model availability."""
  result = test_ollama_connection()
  return JsonResponse({
      "ok": result.get("connected", False),
      **result,
  })


@require_GET
def api_ai_local_models(request):
  """List registered local models + Ollama runtime tags."""
  cfg = load_local_config()
  registry = [m.to_dict() for m in list_models()]
  health = check_ollama_health(cfg)
  return JsonResponse({
      "ok": True,
      "registry": registry,
      "runtime_models": health.get("models", []),
      "default_model": cfg.local_default_model,
  })


@require_GET
def api_ai_local_status(request):
  """Dashboard status — metrics, last review, runtime state."""
  return JsonResponse({"ok": True, **status_payload()})


@require_GET
def api_ai_local_leaderboard(request):
  """Claude vs Qwen leaderboard from real persisted records."""
  return JsonResponse({"ok": True, "leaderboard": build_leaderboard()})


@require_GET
def api_ai_local_comparisons(request):
  limit = min(100, max(1, int(request.GET.get("limit", 20))))
  return JsonResponse({
      "ok": True,
      "items": recent_comparisons(limit),
  })
