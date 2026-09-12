# -*- coding: utf-8 -*-
"""Lightweight widget API endpoints — one endpoint per dashboard widget."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from .jsonsafe import JsonResponse

from .widget_cache import (
    TTL_HEALTH,
    TTL_OPEN_TRADES,
    TTL_PERFORMANCE,
    TTL_SCANNER_SUMMARY,
    TTL_SETTLEMENT,
    TTL_TRENDS,
    widget_cache,
)
from . import widgets as widget_builders

logger = logging.getLogger("dashboard.widgets")


def _timing_response(data: dict[str, Any], *, compute_ms: float, cache_hit: bool,
                     started: float) -> JsonResponse:
    total_ms = round((time.perf_counter() - started) * 1000, 2)
    data["_timing"] = {
        "compute_ms": round(compute_ms, 2),
        "total_ms": total_ms,
        "cache_hit": cache_hit,
    }
    logger.info(
        "widget=%s cache=%s compute=%.1fms total=%.1fms",
        data.get("_widget", "?"), cache_hit, compute_ms, total_ms,
    )
    return JsonResponse(data)


def _widget(request, name: str, ttl: float, builder: Callable[[], dict[str, Any]],
              filters: dict[str, Any]) -> JsonResponse:
    started = time.perf_counter()
    t0 = time.perf_counter()

    def compute():
        return builder()

    try:
        payload, cache_hit = widget_cache.get_or_compute(name, filters, ttl, compute)
    except Exception as exc:  # noqa: BLE001
        logger.exception("widget %s failed", name)
        return JsonResponse({
            "error": str(exc)[:200],
            "_widget": name,
            "_timing": {"total_ms": round((time.perf_counter() - started) * 1000, 2)},
        }, status=500)

    compute_ms = 0.0 if cache_hit else round((time.perf_counter() - t0) * 1000, 2)
    payload = dict(payload)
    payload["_widget"] = name
    return _timing_response(payload, compute_ms=compute_ms, cache_hit=cache_hit,
                            started=started)


def _trade_context(request):
    from django.db.utils import OperationalError, ProgrammingError

    from .views import _held_text, _local_text, _trade_filters, _trade_queryset

    f = _trade_filters(request)
    try:
        qs = _trade_queryset(f)
        rows = widget_builders.rows_for_request(qs)
    except (OperationalError, ProgrammingError) as exc:
        return None, f, str(exc)
    return (qs, rows, f, _local_text, _held_text), f, ""


def api_widget_health(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": f"جدول الصفقات غير موجود: {err}"}, status=500)
    _, rows, f, _, _ = ctx

    def build():
        exp_data = widget_builders.build_experiments()
        bl = widget_builders.build_baselines(
            rows, market=f["market"], timeframe=f["timeframe"])
        return {"health": widget_builders.build_health(
            rows, market=f["market"], timeframe=f["timeframe"],
            running_experiments=exp_data["running_experiments"],
            baseline_pass=bl["baselines"].get("gate_pass", False),
        )}

    return _widget(request, "health", TTL_HEALTH, build, f)


def api_widget_trends(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "trends", TTL_TRENDS,
                   lambda: {"trends": widget_builders.build_trends(rows)}, f)


def api_widget_experiments(request):
    from .views import _trade_filters

    f = _trade_filters(request)
    return _widget(request, "experiments", TTL_PERFORMANCE,
                   widget_builders.build_experiments, f)


def api_widget_factors(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "factors", TTL_PERFORMANCE,
                   lambda: widget_builders.build_factors(rows), f)


def api_widget_confidence(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "confidence", TTL_PERFORMANCE,
                   lambda: widget_builders.build_confidence(rows), f)


def api_widget_baselines(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "baselines", TTL_PERFORMANCE,
                   lambda: widget_builders.build_baselines(
                       rows, market=f["market"], timeframe=f["timeframe"]), f)


def api_widget_splits(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "splits", TTL_PERFORMANCE,
                   lambda: widget_builders.build_splits(rows), f)


def api_widget_trades(request):
    from .views import _apply_status, _paginate, _status_counts

    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    qs, _, f, local_text, held_text = ctx
    page = request.GET.get("page", "1")
    size = request.GET.get("size", "")
    sort = request.GET.get("sort", "date_desc")
    trade_filters = {**f, "page": page, "size": size, "sort": sort}
    return _widget(
        request, "trades", TTL_OPEN_TRADES,
        lambda: widget_builders.build_trades_page(
            qs, filters=f, page=int(page) if page.isdigit() else 1,
            page_size=size, sort=sort, local_text=local_text, held_text=held_text,
            paginate_fn=_paginate, apply_status_fn=_apply_status,
            status_counts_fn=_status_counts),
        trade_filters,
    )


def api_widget_open_trades(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    qs, _, f, local_text, held_text = ctx
    return _widget(
        request, "open_trades", TTL_OPEN_TRADES,
        lambda: widget_builders.build_open_trades(
            qs, local_text=local_text, held_text=held_text),
        f,
    )


def api_widget_settlement(request):
    from .views import _settlement_status

    started = time.perf_counter()
    data = {"settlement": _settlement_status(), "_widget": "settlement"}
    return _timing_response(data, compute_ms=0, cache_hit=False, started=started)


def api_widget_scanner_summary(request):
    from .views import _countdown, _default_scanner_timeframe, _latest_run

    market = request.GET.get("market", "crypto")
    requested_tf = request.GET.get("tf") or None
    tf = _default_scanner_timeframe(market, requested_tf)
    filters = {"market": market, "tf": tf}
    started = time.perf_counter()
    t0 = time.perf_counter()

    def compute():
        run = _latest_run(market, tf)
        if run is None:
            return {"run": None, "countdown": _countdown(tf or "4h")}
        return {
            "run": {
                "id": run.id,
                "started_at": run.started_at.isoformat(),
                "timeframe": run.timeframe,
                "scanned": run.symbols_scanned,
                "failed": run.symbols_failed,
                "ready": run.ready_count,
                "duration": run.duration_seconds,
            },
            "countdown": _countdown(run.timeframe),
        }

    try:
        payload, cache_hit = widget_cache.get_or_compute(
            "scanner_summary", filters, TTL_SCANNER_SUMMARY, compute)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)[:200]}, status=500)

    compute_ms = 0.0 if cache_hit else round((time.perf_counter() - t0) * 1000, 2)
    payload = dict(payload)
    payload["_widget"] = "scanner_summary"
    return _timing_response(payload, compute_ms=compute_ms, cache_hit=cache_hit,
                            started=started)


def api_widget_alerts(request):
    market = request.GET.get("market", "")
    filters = {"market": market}
    return _widget(request, "alerts", TTL_OPEN_TRADES,
                   lambda: widget_builders.build_alerts(market), filters)


def api_widget_optimization_summary(request):
    return _widget(request, "optimization_summary", TTL_PERFORMANCE,
                   widget_builders.build_optimization_summary, {})


def api_widget_ai_platform(request):
    ctx, f, err = _trade_context(request)
    if ctx is None:
        return JsonResponse({"error": err}, status=500)
    _, rows, f, _, _ = ctx
    return _widget(request, "ai_platform", TTL_HEALTH,
                   lambda: widget_builders.build_ai_platform_summary(rows), f)


def api_widget_ai_advisor(request):
    return _widget(request, "ai_advisor", TTL_HEALTH,
                   widget_builders.build_ai_advisor_summary, {})


def api_widget_ai_advisor_evaluation(request):
    return _widget(request, "ai_advisor_evaluation", TTL_HEALTH,
                   widget_builders.build_ai_advisor_evaluation_summary, {})


def api_widget_ai_learning(request):
    return _widget(request, "ai_learning", TTL_HEALTH,
                   widget_builders.build_ai_learning_summary, {})
