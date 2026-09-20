# -*- coding: utf-8 -*-
"""شاشة «من الأعلى للأسفل» — الأسبوعيّ يأذن، واليوميّ يوافق، والـ4س يوقّت.

تقرأ الملفّ المحفوظ ولا تحسب في الطلب: مئة رمزٍ × ثلاثة فريمات
تشغل خيط الخادم دقائق، والمتصفّح يحدّ اتصالاته بستّة — فتتجمّد
الواجهة كلّها بفتح صفحة.
"""
from __future__ import annotations

import logging
import time

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import blocklist
from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.topdown")

STALE_HOURS = 12


def topdown_page(request):
    from scanner.strategies.topdown_scan import STAGE_LABELS, STAGES

    from .views import MARKETS, market_options

    # المراحل تُشتقّ من المصدر لا تُكتب هنا — وإلّا ظهرت مرحلةٌ
    # في الفرز ولم تظهر في المرشِّح، أو العكس.
    return render(request, "dashboard/topdown.html", {
        "nav_page": "topdown",
        "markets": MARKETS,
        "market_options": market_options(),
        "stages": [{"key": k, "label": STAGE_LABELS.get(k, k)}
                   for k in reversed(STAGES)],
    })


@require_GET
def api_topdown(request):
    from scanner.strategies import topdown_scan

    from .views import MARKETS

    market = (request.GET.get("market") or "").strip()
    stage = (request.GET.get("stage") or "").strip()

    wanted = [market] if market in MARKETS else list(MARKETS)
    groups, missing = [], []
    for m in wanted:
        data = topdown_scan.load(m)
        if not data:
            missing.append(m)
            continue
        rows = blocklist.drop_blocked(data.get("rows") or [], market=m)
        if stage:
            rows = [r for r in rows if r.get("stage") == stage]
        else:
            # ═══ الافتراضي: الجاهز ومن ينتظر الارتداد ═══
            #
            # ومن سقط عند الأسبوعيّ لا يُعرَض: هو أغلب السوق، وعرضُه
            # يدفن الثلاثة التي تهمّ. والعدّ يبقى في ``by_stage``
            # فلا يختفي الخبر — يختفي الصفّ وحده.
            rows = [r for r in rows if r.get("stage") in ("ready", "entry")]
        age_h = (time.time() - float(data.get("measured_at") or 0)) / 3600
        groups.append({
            "market": m,
            "age_hours": round(age_h, 1),
            "stale": age_h > STALE_HOURS,
            "evaluated": data.get("evaluated"),
            "by_stage": data.get("by_stage") or {},
            "ready_count": len(data.get("ready") or []),
            # ما اكتُشف ولم تصله المزامنة — يُعرَض ولا يُبتلَع
            "coverage": data.get("coverage") or {},
            "coverage_text": data.get("coverage_text") or "",
            "rows": rows[:60],
            "shown": len(rows),
        })
    return JsonResponse({"ok": True, "groups": groups, "missing": missing,
                         "stale_hours": STALE_HOURS})


@require_POST
def api_topdown_refresh(request):
    import threading

    from scanner.strategies import topdown_scan

    from .views import MARKETS

    market = (request.POST.get("market") or "").strip()
    if market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "سوق غير معروف"},
                            status=400)

    def work():
        try:
            topdown_scan.scan(market)
        except Exception:  # noqa: BLE001
            log.exception("تعذّر مسح topdown %s", market)

    threading.Thread(target=work, name=f"topdown-{market}",
                     daemon=True).start()
    return JsonResponse({"ok": True, "started": market})
