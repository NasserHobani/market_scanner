# -*- coding: utf-8 -*-
"""صفحة الانضغاط — من ينتظر تمدّداً، وباحتمالٍ مقيس.

الاحتمال **للسوق والفريم** لا للرمز: رمزٌ له خمس حالات لا تُبنى
عليه نسبة. ولذلك يُعرض معه معدّل الأساس دائماً — فيُقرأ الفارق لا
الرقم وحده.
"""
from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import blocklist
from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.squeeze")

# لا يُعرض قياسٌ أقدم من هذا بلا تنبيه: الشموع تتحرّك
STALE_HOURS = 12


def squeeze_page(request):
    from scanner.squeeze_scan import HORIZONS

    from .views import MARKETS, TIMEFRAME_LABELS, UI_TIMEFRAMES, market_options

    return render(request, "dashboard/squeeze.html", {
        "nav_page": "squeeze",
        "markets": MARKETS,
        "market_options": market_options(),
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]}
                       for t in UI_TIMEFRAMES if t in HORIZONS],
    })


@require_GET
def api_squeeze(request):
    """يقرأ القياس المحفوظ — ولا يحسب في الطلب.

    القياس يمرّ على مئات ملفّات الشموع. وتشغيله داخل طلبٍ يجعل
    الصفحة تنتظر دقائق، فيُغلقها المستخدم ويظنّها معطّلة.
    """
    import time

    from scanner import squeeze_scan

    from .views import MARKETS, UI_TIMEFRAMES

    market = (request.GET.get("market") or "").strip()
    tf = (request.GET.get("tf") or "").strip()
    if market and market not in MARKETS:
        market = ""
    if tf and tf not in UI_TIMEFRAMES:
        tf = ""

    wanted_m = [market] if market else list(MARKETS)
    wanted_t = [tf] if tf else [t for t in UI_TIMEFRAMES
                                if t in squeeze_scan.HORIZONS]

    groups, missing = [], []
    for m in wanted_m:
        for t in wanted_t:
            data = squeeze_scan.load(m, t)
            if not data:
                missing.append(f"{m}·{t}")
                continue
            age_h = (time.time() - float(data.get("measured_at") or 0)) / 3600
            prob = data.get("probability") or {}
            timing = data.get("timing") or {}
            groups.append({
                "market": m, "timeframe": t,
                "age_hours": round(age_h, 1),
                "stale": age_h > STALE_HOURS,
                "symbols_scanned": data.get("symbols_scanned"),
                "probability": prob,
                "timing": {
                    **timing,
                    "human": squeeze_scan.humanize(
                        timing.get("median_minutes")),
                    "horizon_human": squeeze_scan.humanize(
                        timing.get("horizon_minutes")),
                },
                # القياس محفوظ وقد يسبق الحظر — فيُصفّى عند القراءة
                "candidates": blocklist.drop_blocked(
                    data.get("candidates") or [], market=m)[:40],
            })

    groups.sort(key=lambda g: -(g["probability"].get("edge") or 0))
    return JsonResponse({
        "ok": True, "groups": groups, "missing": missing,
        "stale_hours": STALE_HOURS,
    })


@require_POST
def api_squeeze_refresh(request):
    """يعيد القياس في الخلفية لسوقٍ وفريم."""
    import threading

    from scanner import squeeze_scan

    from .views import MARKETS, UI_TIMEFRAMES

    market = (request.POST.get("market") or "").strip()
    tf = (request.POST.get("tf") or "").strip()
    if market not in MARKETS or tf not in UI_TIMEFRAMES:
        return JsonResponse({"ok": False, "reason": "سوق أو فريم غير معروف"},
                            status=400)

    def work():
        try:
            squeeze_scan.save(squeeze_scan.build(market, tf))
        except Exception:  # noqa: BLE001
            log.exception("تعذّر قياس الانضغاط %s %s", market, tf)

    threading.Thread(target=work, name=f"squeeze-{market}-{tf}",
                     daemon=True).start()
    return JsonResponse({"ok": True, "started": f"{market}·{tf}"})
