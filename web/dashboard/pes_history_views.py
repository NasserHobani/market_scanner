# -*- coding: utf-8 -*-
"""صفحة سجلّ الرصد — متى رُصد الرمز، وماذا جرى بعده.

═══ العتبة مرشِّح لا ثابت ═══

«هل انفجرت؟» جوابُه يتوقّف على العتبة. فهي هنا شريطٌ يحرّكه
المستخدم — يضعه على ‎5٪‎ فيرى نسبةً، وعلى ‎15٪‎ فيرى أخرى.

وهذا ليس ترفاً: نسبةُ نجاحٍ واحدة برقمٍ واحد تُصدَّق أو تُهمَل ولا
تُناقَش. أمّا رؤية النسبة وهي تنهار من ‎70٪‎ عند ‎3٪‎ إلى ‎12٪‎ عند
‎15٪‎ فتقول شيئاً عن الاستراتيجية لا يقوله أيّ رقمٍ مفرد.

═══ والعيّنة الصغيرة تُعلَن ═══

أوّل ما يُجمع سيكون رصداتٍ قليلة. و«نجح ٣ من ٤ — ٧٥٪» رقمٌ لا
يعني شيئاً، وفترة ثقته من ٣٠٪ إلى ٩٥٪. فتُعرض الفترة دائماً،
ويُعلَن صراحةً حين تكون العيّنة أرقّ من أن تُقرأ.
"""
from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.pes_history")

# العتبات المعروضة في الشاشة — والمستخدم يختار منها أو يكتب رقمه
PRESETS = (3.0, 5.0, 8.0, 12.0, 20.0)
DEFAULT_THRESHOLD = 8.0


def history_page(request):
    from scanner.strategies.pes import STATE_LABELS

    from . import pes_history
    from .views import MARKETS, market_options

    return render(request, "dashboard/pes_history.html", {
        "nav_page": "pes_history",
        "markets": MARKETS,
        "market_options": market_options(),
        "states": [{"key": k, "label": STATE_LABELS.get(k, k)}
                   for k in pes_history.TRACKED_STATES],
        "presets": PRESETS,
        "default_threshold": DEFAULT_THRESHOLD,
        "horizon_days": pes_history.HORIZON_DAYS,
    })


@require_GET
def api_pes_history(request):
    """السجلّ ملخَّصاً ومفصَّلاً عند العتبة المطلوبة."""
    from django.db.utils import OperationalError, ProgrammingError

    from . import pes_history
    from .models import PesDetection
    from .views import MARKETS

    market = (request.GET.get("market") or "").strip()
    state = (request.GET.get("state") or "").strip()
    try:
        threshold = float(request.GET.get("threshold")
                          or DEFAULT_THRESHOLD)
    except (TypeError, ValueError):
        threshold = DEFAULT_THRESHOLD
    threshold = max(0.0, min(200.0, threshold))

    try:
        qs = PesDetection.objects.all()
        if market in MARKETS:
            qs = qs.filter(market=market)
        if state:
            qs = qs.filter(state=state)
        rows = list(qs.order_by("-detected_at")[:600])
    except (OperationalError, ProgrammingError):
        return JsonResponse(
            {"ok": False,
             "reason": "شغّل: python web/manage.py migrate dashboard"},
            status=503)

    overall = pes_history.summarize(rows, threshold)

    # ═══ المقارنة بين الحالات هي الفائدة ═══
    #
    # «‏PES نسبته ٤٠٪» رقمٌ بلا مرجع. أمّا «‏STRONG_PRE_BREAKOUT
    # ‏٥٥٪ مقابل WATCH ‏٢٨٪» فتقول إنّ التصنيف يفرّق فعلاً —
    # أو لا يفرّق، وهذا أنفع.
    by_state = []
    for key in pes_history.TRACKED_STATES:
        subset = [r for r in rows if r.state == key]
        if not subset:
            continue
        s = pes_history.summarize(subset, threshold)
        s["state"] = key
        s["label"] = subset[0].state_label or key
        by_state.append(s)
    by_state.sort(key=lambda s: (s["rate"] is None, -(s["rate"] or 0)))

    # ═══ منحنى العتبة ═══
    #
    # النسبة عند كل عتبةٍ دفعةً واحدة. وانهيارُها السريع يعني أنّ
    # ما يُلتقط حركاتٌ صغيرة لا انفجارات — وهو ما تدّعيه
    # الاستراتيجية بالضبط.
    curve = [{"threshold": t,
              "rate": pes_history.summarize(rows, t)["rate"]}
             for t in PRESETS]

    return JsonResponse({
        "ok": True,
        "threshold": threshold,
        "horizon_days": pes_history.HORIZON_DAYS,
        "overall": overall,
        "by_state": by_state,
        "curve": curve,
        "rows": [_row(r, threshold) for r in rows[:200]],
    })


def _row(r, threshold: float) -> dict:
    hit = (r.max_gain_pct is not None and r.max_gain_pct >= threshold
           and r.outcome == "settled")
    return {
        "id": r.id, "symbol": r.symbol, "market": r.market,
        "state": r.state, "state_label": r.state_label or r.state,
        "detected_at": r.detected_at.isoformat() if r.detected_at else "",
        "candle_time": r.candle_time.isoformat() if r.candle_time else "",
        "price": r.price, "score": r.score,
        "momentum_score": r.momentum_score,
        "momentum_label": r.momentum_label,
        "distance_pct": r.distance_pct,
        "btc_label": r.btc_label,
        "bars_seen": r.bars_seen,
        "max_gain_pct": r.max_gain_pct,
        "hours_to_max": r.hours_to_max,
        "max_drawdown_pct": r.max_drawdown_pct,
        "broke_resistance": r.broke_resistance,
        "volatility_expanded": r.volatility_expanded,
        "outcome": r.outcome,
        # ‏«لم يُقَس بعد» ليست «فشل» — والشاشة تفرّق بينهما بلونٍ
        # ونصّ، لأنّ خلطهما يجعل كل رصدٍ حديث يبدو خاسراً.
        "hit": hit,
        "verdict": ("بلغ العتبة" if hit else
                    ("قيد المتابعة" if r.outcome == "watching" else
                     ("تعذّرت المتابعة" if r.outcome == "no_data"
                      else "لم يبلغها"))),
        "url": f"/symbol/{r.market}/{r.symbol}/?tf=4h",
    }


@require_POST
def api_pes_history_refresh(request):
    """يعيد حساب المسار الآن بدل انتظار الدورة."""
    from . import pes_history

    try:
        stats = pes_history.follow_up()
    except Exception as exc:  # noqa: BLE001
        log.exception("فشلت متابعة السجلّ")
        return JsonResponse({"ok": False, "reason": str(exc)[:200]},
                            status=500)
    return JsonResponse({"ok": True, **stats})
