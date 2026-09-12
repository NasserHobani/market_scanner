# -*- coding: utf-8 -*-
"""صفحة PES — ما قبل الانفجار، بفلتر السوق والفريم والمرحلة."""
from __future__ import annotations

import logging
import time

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import blocklist
from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.pes")

STALE_HOURS = 8


def pes_page(request):
    from scanner.strategies.pes import STATE_LABELS, STATES

    from .views import MARKETS, market_options

    # ═══ القائمة تُشتقّ ولا تُكتب ═══
    #
    # كانت هنا ستّ حالاتٍ مكتوبة بيدها. وأيّ حالةٍ جديدة تُضاف إلى
    # ``STATES`` كانت تصنَّف ولا تظهر في المرشِّح — أي أنّ الرمز
    # يُصنَّف تصنيفاً لا يستطيع المستخدم أن يبحث عنه، بلا خطأ ولا
    # أثر. وقد وقع هذا فعلاً عند إضافة الحالات الثلاث الجديدة.
    #
    # و``STATES`` مرتّبة من الأضعف إلى الأقوى، والعرض بالعكس.
    # و``NONE`` تُستبعد: هي «لا شيء» لا حالة تُرشَّح.
    order = [s for s in reversed(STATES) if s != "NONE"]
    return render(request, "dashboard/pes.html", {
        "nav_page": "pes",
        "markets": MARKETS,
        "market_options": market_options(),
        "states": [{"key": k, "label": STATE_LABELS[k]} for k in order],
    })


@require_GET
def api_pes(request):
    from scanner.strategies import pes_scan

    from .views import MARKETS

    market = (request.GET.get("market") or "").strip()
    state = (request.GET.get("state") or "").strip()
    try:
        min_score = float(request.GET.get("min_score") or 0)
    except (TypeError, ValueError):
        min_score = 0.0

    wanted = [market] if market in MARKETS else list(MARKETS)
    groups, missing = [], []
    for m in wanted:
        data = pes_scan.load(m)
        if not data:
            missing.append(m)
            continue
        # مصفّى عند المسح، ويُعاد ترشيحه هنا: من حُظر بعد آخر مسح
        # يبقى في الملفّ المحفوظ.
        rows = blocklist.drop_blocked(data.get("rows") or [], market=m)
        if state:
            rows = [r for r in rows if r.get("state") == state]
        else:
            # الافتراضي يُخفي «لا إشارة»: عرض ٦٢ صفّاً بلا إشارة
            # يدفن الثلاثة التي لها إشارة.
            rows = [r for r in rows if r.get("state") not in ("NONE",)]
        if min_score:
            rows = [r for r in rows if float(r.get("score") or 0) >= min_score]
        age_h = (time.time() - float(data.get("measured_at") or 0)) / 3600
        groups.append({
            "market": m, "age_hours": round(age_h, 1),
            "stale": age_h > STALE_HOURS,
            "btc": data.get("btc") or {},
            "evaluated": data.get("evaluated"),
            "by_state": data.get("by_state") or {},
            "rows": rows[:60],
            "shown": len(rows),
        })
    return JsonResponse({"ok": True, "groups": groups, "missing": missing,
                         "stale_hours": STALE_HOURS})


@require_POST
def api_pes_refresh(request):
    import threading

    from scanner.strategies import pes_scan

    from .views import MARKETS

    market = (request.POST.get("market") or "").strip()
    if market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "سوق غير معروف"},
                            status=400)

    def work():
        try:
            pes_scan.save(pes_scan.scan(market))
        except Exception:  # noqa: BLE001
            log.exception("تعذّر مسح PES %s", market)

    threading.Thread(target=work, name=f"pes-{market}", daemon=True).start()
    return JsonResponse({"ok": True, "started": market})
