# -*- coding: utf-8 -*-
"""Market-data sync HTTP API (MD-01)."""
from __future__ import annotations

import threading

from .jsonsafe import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import market_sync_worker


@require_GET
def api_market_sync_status(request):
    """GET /api/market-data/sync/status/"""
    from scanner.market_sync import get_service

    market = request.GET.get("market")
    markets = [market] if market else None
    try:
        # ذاكرة ثلاثين ثانية: هذه النقطة تُنادى من كل صفحة وكل
        # ثلاثين ثانية، وإعادة الحساب كانت 26 ثانية. والحالة لا
        # تتغيّر أسرع من دورة عامل المزامنة.
        report = get_service().global_status(markets=markets, max_age=30.0)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "error", "reason": str(exc)[:200]}, status=500)

    worker = market_sync_worker.status()
    report["worker_runtime"] = {
        "thread_started": worker.get("thread_started"),
        "running": worker.get("running"),
        "cycle_count": worker.get("cycle_count"),
        "last_cycle": worker.get("last_cycle"),
        "last_error": worker.get("last_error"),
    }
    # Compact UI payload
    report["ui"] = _ui_badge(report)
    return JsonResponse(report)


@require_POST
def api_market_sync_now(request):
    """Force incremental sync — NOT a prerequisite for every scan."""
    market = request.POST.get("market") or request.GET.get("market") or "crypto"
    force = request.POST.get("force", "1") not in ("0", "false", "False")

    if market_sync_worker.is_running():
        return JsonResponse({"ok": False, "reason": "مزامنة جارية بالفعل"})

    markets = [market] if market != "all" else None

    def _run():
        market_sync_worker.run_once(markets, force=force)

    threading.Thread(target=_run, name=f"manual-sync-{market}", daemon=True).start()
    return JsonResponse({
        "ok": True,
        "market": market,
        "mode": "incremental",
        "message": "جاري تحديث البيانات…",
    })


@require_GET
def api_market_sync_worker_status(request):
    st = market_sync_worker.status()
    return JsonResponse(st)


@require_GET
def api_chart_latest(request, market: str, symbol: str):
    """Lightweight latest-candle poll — no historical reload, no full sync."""
    from scanner import storage
    from scanner.live import UI_TIMEFRAMES
    from scanner.market_sync.freshness import assess_freshness

    timeframe = request.GET.get("tf") or "1h"
    if timeframe not in UI_TIMEFRAMES:
        return JsonResponse({"error": "فريم غير مدعوم"}, status=400)

    df = storage.load(market, symbol, timeframe)
    if df is None or df.empty:
        return JsonResponse({"error": "لا بيانات محلية", "available": False}, status=404)

    last = df.iloc[-1]
    ts = df.index[-1]
    freshness = assess_freshness(market, symbol, timeframe, df=df)
    return JsonResponse({
        "available": True,
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "candle": {
            "time": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
            "open": float(last["open"]),
            "high": float(last["high"]),
            "low": float(last["low"]),
            "close": float(last["close"]),
            "volume": float(last.get("volume", 0) or 0),
        },
        "freshness": freshness,
        "candle_count": len(df),
    })


def _ui_badge(report: dict) -> dict:
    status = report.get("status") or "unknown"
    stale = int(report.get("stale") or 0)
    error = int(report.get("error") or 0)
    last = report.get("last_successful_sync")
    if status == "healthy":
        return {
            "level": "ok",
            "title": "بيانات السوق محدثة",
            "detail": f"آخر مزامنة: {_ago(last)}",
            "candles": "محدثة",
        }
    if status == "degraded":
        return {
            "level": "warn",
            "title": "بعض البيانات متأخرة",
            "detail": f"{stale + error} أزواج متأخرة/متعذّرة",
            "candles": "جزئياً",
        }
    if status == "error":
        return {
            "level": "error",
            "title": "مزامنة السوق متوقفة",
            "detail": f"آخر تحديث: {_ago(last)}",
            "candles": "متوقفة",
        }
    return {
        "level": "unknown",
        "title": "حالة بيانات السوق غير معروفة",
        "detail": "لم تكتمل مزامنة بعد",
        "candles": "—",
    }


def _ago(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        from datetime import datetime, timezone
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        sec = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
        if sec < 60:
            return f"منذ {sec} ثانية"
        if sec < 3600:
            return f"منذ {sec // 60} دقيقة"
        return f"منذ {sec // 3600} ساعة"
    except Exception:  # noqa: BLE001
        return iso[:19]
