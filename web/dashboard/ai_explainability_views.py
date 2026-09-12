# -*- coding: utf-8 -*-
"""Explainable AI REST API — review timeline and manual analysis."""
from __future__ import annotations

import json

from django.http import HttpResponse
from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from scanner.ai_advisor.explainability.manual_analysis_service import ManualAnalysisService
from scanner.ai_advisor.explainability.review_export import (
    export_json,
    export_markdown,
    export_pdf_bytes,
)
from scanner.ai_advisor.explainability.review_timeline_service import ReviewTimelineService


def _svc() -> ReviewTimelineService:
    return ReviewTimelineService()


@require_GET
def api_ai_reviews_list(request):
    page = max(1, int(request.GET.get("page", 1)))
    page_size = min(100, max(1, int(request.GET.get("page_size", 25))))
    data = _svc().list_reviews(
        page=page,
        page_size=page_size,
        query=request.GET.get("q", ""),
        provider=request.GET.get("provider", ""),
        agreement=request.GET.get("agreement", ""),
        review_type=request.GET.get("type", ""),
        symbol=request.GET.get("symbol", ""),
        date_from=request.GET.get("from", ""),
        date_to=request.GET.get("to", ""),
    )
    return JsonResponse({"ok": True, **data})


@require_GET
def api_ai_reviews_live(request):
    live = _svc().get_live()
    return JsonResponse({"ok": True, "live": live})


@require_GET
def api_ai_review_detail(request, review_id: str):
    detail = _svc().get_review(review_id)
    if not detail:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    try:
        from scanner.ai_fusion.fusion_history import FusionHistory
        fusion = next(
            (r for r in reversed(FusionHistory().list_all(limit=500))
             if r.get("review_id") == review_id),
            None,
        )
        if fusion:
            detail["fusion"] = fusion
    except Exception:  # noqa: BLE001
        pass
    return JsonResponse({"ok": True, "review": detail})


@require_GET
def api_ai_review_export(request, review_id: str):
    detail = _svc().get_review(review_id)
    if not detail:
        return JsonResponse({"ok": False, "error": "not_found"}, status=404)
    fmt = (request.GET.get("format") or "json").lower()
    if fmt == "json":
        body = export_json(detail)
        return HttpResponse(body, content_type="application/json; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{review_id}.json"'})
    if fmt == "markdown":
        body = export_markdown(detail)
        return HttpResponse(body, content_type="text/markdown; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{review_id}.md"'})
    if fmt == "pdf":
        body = export_pdf_bytes(detail)
        return HttpResponse(body, content_type="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="{review_id}.pdf"'})
    return JsonResponse({"ok": False, "error": "invalid_format"}, status=400)


@require_GET
def api_ai_provider_stats(request):
    return JsonResponse({"ok": True, "providers": _svc().provider_statistics()})


@require_POST
def api_ai_manual_analysis(request):
    try:
        if request.content_type and "json" in request.content_type:
            body = json.loads(request.body.decode() or "{}")
        else:
            body = request.POST.dict()
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    symbol = (body.get("symbol") or "").strip().upper()
    market = (body.get("market") or "crypto").strip().lower()
    timeframe = (body.get("timeframe") or "").strip() or None
    force = str(body.get("force", "")).lower() in ("1", "true", "yes")

    if not symbol:
        return JsonResponse({"ok": False, "error": "symbol_required"}, status=400)

    result = ManualAnalysisService().analyze(
        symbol=symbol, market=market, timeframe=timeframe, force=force,
    )
    status = 200 if result.get("ok") else 503
    return JsonResponse(result, status=status)


def api_widget_ai_review_timeline(request):
    """Widget endpoint — review timeline for AI Center."""
    from .widget_cache import TTL_HEALTH, widget_cache
    from . import widgets as widget_builders
    import time

    page = max(1, int(request.GET.get("page", 1)))
    page_size = min(50, max(1, int(request.GET.get("page_size", 10))))
    filters = {"page": page, "page_size": page_size}
    started = time.perf_counter()
    t0 = time.perf_counter()

    def compute():
        return widget_builders.build_ai_review_timeline(page=page, page_size=page_size)

    try:
        payload, cache_hit = widget_cache.get_or_compute(
            "ai_review_timeline", filters, TTL_HEALTH, compute,
        )
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)[:200], "_widget": "ai_review_timeline"}, status=500)

    compute_ms = 0.0 if cache_hit else round((time.perf_counter() - t0) * 1000, 2)
    payload = dict(payload)
    payload["_widget"] = "ai_review_timeline"
    payload["_timing"] = {
        "compute_ms": round(compute_ms, 2),
        "total_ms": round((time.perf_counter() - started) * 1000, 2),
        "cache_hit": cache_hit,
    }
    return JsonResponse(payload)
