# -*- coding: utf-8 -*-
"""الصفقات الذهبية — أفضل مرشّح من كل سوق، وسبب اختياره.

═══ ما «الذهبية» هنا ═══

ليست الأعلى نقاطاً. النقاط رقمٌ يعطيه النظام لنفسه، وقِيس على
٢٩٥ صفقة محسومة فلم يفصل التصنيف A عن C بفارقٍ يتجاوز الصدفة.

فالترتيب هنا مركّب ومُعلَن، ولكل مرشّح **سبب اختياره مكتوباً**:

    · عائد/مخاطرة        — الوحيد المعروف قبل الدخول يقيناً
    · التقاء العوامل      — كم عاملاً اجتمع
    · سجلّ أسباب الإشارة  — من ``why``: كم سبباً أثبت نفسه، وكم يعمل ضدّك
    · النقاط             — بوزنٍ أقلّ، لما سبق

و«ذهبية» لا تعني «رابحة». تعني: أفضل ما في السوق **اليوم** بمقياسٍ
مكتوب. وإن كان أفضل ما في السوق ضعيفاً فذلك يُقال.

═══ واحدة من كل سوق ═══

الحدّ ليس تجميلاً: التركيز على ثلاث فرص يجعل حجم المركز محسوباً
وقابلاً للمتابعة. وعشرون فرصة في الشاشة تعني ألّا تُتابَع واحدة.
"""
from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.golden")

# لا يُعرض مرشّح أقدم من هذا: إشارةٌ عمرها ثلاثة أيام سعرُها تغيّر
MAX_AGE_HOURS = 48

# عائد/مخاطرة دون هذا لا يُسمّى فرصة مهما بلغت نقاطه
MIN_RR = 1.5


def _candidates(market: str, limit: int = 40) -> list:
    """أحدث المرشّحين القابلين للتنفيذ في سوقٍ واحد."""
    from datetime import timedelta

    from django.utils import timezone

    from .models import ScanResult

    cutoff = timezone.now() - timedelta(hours=MAX_AGE_HOURS)
    rows = list(
        ScanResult.objects
        .filter(market=market, action__in=("now", "pending"),
                candle_time__gte=cutoff)
        .exclude(entry__isnull=True).exclude(stop__isnull=True)
        .exclude(target1__isnull=True)
        .order_by("-candle_time", "-score")[:limit * 2]
    )
    # المحظور لا يُرشَّح — ويُؤخذ ضِعف الحدّ قبل الترشيح كي لا
    # تنقص القائمة بعده
    from . import blocklist

    return blocklist.drop_blocked(rows, market=market)[:limit]


def _population() -> list[dict]:
    """الصفقات المحسومة — أساس كل نسبة تُذكَر."""
    from .models import Trade

    fields = ("id", "symbol", "market", "timeframe", "side", "status",
              "r_multiple", "score", "rr", "grade", "source", "action",
              "reasons")
    have = {f.name for f in Trade._meta.get_fields() if hasattr(f, "name")}
    cols = [c for c in fields if c in have]
    return list(Trade.objects.filter(status__in=("won", "lost")).values(*cols))


def _score_candidate(row, population) -> dict:
    """يرتّب مرشّحاً ويكتب سبب ترتيبه — لا رقماً مبهماً.

    كل مركّبٍ يُعرض بوزنه وقيمته، فيمكن للقارئ أن يخالف الترتيب
    وهو يعرف على ماذا بُني. ودرجةٌ بلا تفصيل تُصدَّق أو تُهمَل،
    ولا تُناقَش.
    """
    from scanner.ai_advisor import why as why_mod

    parts: list[dict] = []
    total = 0.0

    rr = float(row.rr or 0)
    # عائد/مخاطرة: الوحيد المعروف يقيناً قبل الدخول — الباقي تقدير
    rr_pts = min(30.0, max(0.0, (rr - 1.0) * 15.0))
    parts.append({"label": "عائد/مخاطرة", "value": f"{rr:.2f}",
                  "points": round(rr_pts, 1), "max": 30})
    total += rr_pts

    conf = int(row.confluence or 0)
    conf_pts = min(20.0, conf * 6.5)
    parts.append({"label": "التقاء العوامل", "value": f"{conf}/3",
                  "points": round(conf_pts, 1), "max": 20})
    total += conf_pts

    # ═══ سجلّ الأسباب — الوزن الأكبر ═══
    #
    # هذا وحده مبنيّ على نتائج حقيقية. والباقي أوصافٌ للحاضر.
    w = why_mod.explain({"reasons": row.reasons or ""}, population)
    support = len(w.supporting)
    against = len(w.opposing)
    hist_pts = min(35.0, support * 12.0) - min(35.0, against * 18.0)
    parts.append({"label": "سجلّ أسباب الإشارة",
                  "value": f"{support} مؤيّد · {against} مضادّ",
                  "points": round(hist_pts, 1), "max": 35})
    total += hist_pts

    score = float(row.score or 0)
    score_pts = min(15.0, score / 4.0)
    parts.append({"label": "نقاط النظام", "value": f"{score:.1f}",
                  "points": round(score_pts, 1), "max": 15})
    total += score_pts

    return {"total": round(total, 1), "parts": parts, "why": w}


def _card(row, population) -> dict:
    s = _score_candidate(row, population)
    w = s["why"]
    entry, stop, target = row.entry, row.stop, row.target1
    risk_pct = None
    if entry and stop and float(entry):
        risk_pct = round(abs(float(entry) - float(stop)) / float(entry) * 100, 2)
    gain_pct = None
    if entry and target and float(entry):
        gain_pct = round((float(target) - float(entry)) / float(entry) * 100, 2)

    return {
        "symbol": row.symbol, "market": row.market,
        "timeframe": row.timeframe,
        "candle_time": row.candle_time.isoformat() if row.candle_time else "",
        "action": row.action, "grade": row.grade,
        "entry": entry, "stop": stop, "target1": target,
        "rr": row.rr, "close": row.close, "score": row.score,
        "confluence": row.confluence,
        "reasons": row.reasons or "",
        "url": f"/symbol/{row.market}/{row.symbol}/?tf={row.timeframe}",
        "chart_url": row.chart_url or "",
        # ═══ الحركة بالنسبة المئوية ═══
        #
        # الهدف بالسعر لا يقول كم يلزم من حركة. و«الهدف يبعد 4.2٪»
        # تُقارَن مباشرةً بما تتوقّعه من السوق اليوم.
        "risk_pct": risk_pct, "gain_pct": gain_pct,
        "rank_total": s["total"], "rank_parts": s["parts"],
        "why": {
            "headline": w.headline(),
            "supporting": [r.arabic() for r in w.supporting],
            "opposing": [r.arabic() for r in w.opposing],
            "tested": w.tested, "survived": w.survived,
            "untested": len(w.untested),
        },
    }


def golden_page(request):
    from .views import MARKETS, market_options

    return render(request, "dashboard/golden.html", {
        "nav_page": "golden",
        "markets": MARKETS,
        "market_options": market_options(),
    })


@require_GET
def api_golden(request):
    """أفضل مرشّح من كل سوق — أو إعلانٌ بأن لا مرشّح."""
    from django.db.utils import OperationalError, ProgrammingError

    from .views import MARKETS, MARKET_LABELS

    try:
        population = _population()
    except (OperationalError, ProgrammingError):
        return JsonResponse({"ok": False,
                             "reason": "شغّل: python web/manage.py migrate"},
                            status=503)

    out = []
    for market in MARKETS:
        rows = _candidates(market)
        # ═══ الرفض يُعلَن بسببه ═══
        #
        # بطاقةٌ فارغة تُقرأ «السوق هادئ»، وقد يكون السبب أنّ
        # المسح لم يعمل منذ يومين. والفرق يغيّر ما يفعله القارئ.
        if not rows:
            out.append({"market": market,
                        "label": MARKET_LABELS.get(market, market),
                        "candidate": None,
                        "reason": f"لا إشارة قابلة للتنفيذ خلال "
                                  f"{MAX_AGE_HOURS} ساعة"})
            continue
        usable = [r for r in rows if float(r.rr or 0) >= MIN_RR]
        if not usable:
            best_rr = max((float(r.rr or 0) for r in rows), default=0)
            out.append({"market": market,
                        "label": MARKET_LABELS.get(market, market),
                        "candidate": None,
                        "reason": f"{len(rows)} إشارة، وأفضل عائد/مخاطرة "
                                  f"{best_rr:.2f} دون الحدّ {MIN_RR}"})
            continue
        cards = [_card(r, population) for r in usable]
        cards.sort(key=lambda c: -c["rank_total"])
        best = cards[0]
        best["considered"] = len(usable)
        out.append({"market": market,
                    "label": MARKET_LABELS.get(market, market),
                    "candidate": best, "reason": ""})

    return JsonResponse({
        "ok": True, "markets": out,
        "population": len(population),
        "max_age_hours": MAX_AGE_HOURS, "min_rr": MIN_RR,
    })
