# -*- coding: utf-8 -*-
"""صفحة المحفظة الورقية — الرصيد والصفقات والإعدادات."""
from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import paper
from .jsonsafe import JsonResponse
from .models import PaperTrade

log = logging.getLogger("dashboard.paper")


def _row(t) -> dict:
    unreal = None
    if t.status == "open" and t.last_price:
        gross = t.quantity * float(t.last_price) - t.notional
        # الرسوم المقدَّرة للخروج تُطرح: الربح غير المحقّق الذي
        # يتجاهلها يُبشّر بما لا يصل إلى الجيب.
        unreal = round(gross - t.fee_in
                       - paper.fees_on(t.quantity * float(t.last_price),
                                       {"fee_pct": 0.1}), 2)
    return {
        "id": t.id, "symbol": t.symbol, "market": t.market,
        "timeframe": t.timeframe, "source": t.source,
        "entry": t.entry, "stop": t.stop, "target": t.target,
        "quantity": t.quantity, "notional": round(t.notional, 2),
        "risk_amount": round(t.risk_amount, 2),
        "last_price": t.last_price, "exit_price": t.exit_price,
        "exit_reason": t.exit_reason,
        "fees": round(float(t.fee_in or 0) + float(t.fee_out or 0), 4),
        "pnl": round(float(t.pnl or 0), 2),
        "unrealized": unreal,
        "r_multiple": (round(t.r_multiple, 2)
                       if t.r_multiple is not None else None),
        "status": t.status, "status_label": t.get_status_display(),
        "opened_at": t.opened_at.isoformat() if t.opened_at else "",
        "closed_at": t.closed_at.isoformat() if t.closed_at else "",
        "note": t.note,
    }


def paper_page(request):
    return render(request, "dashboard/paper.html", {
        "nav_page": "paper",
        "defaults": paper.DEFAULTS,
    })


@require_GET
def api_paper(request):
    from django.db.utils import OperationalError, ProgrammingError

    try:
        acc = paper.get_or_create_account()
    except (OperationalError, ProgrammingError):
        return JsonResponse({"ok": False,
                             "reason": "شغّل: python web/manage.py migrate"},
                            status=503)

    status = (request.GET.get("status") or "").strip()
    qs = PaperTrade.objects.filter(account=acc)
    if status in ("open", "won", "lost"):
        qs = qs.filter(status=status)
    else:
        qs = qs.exclude(status="cancelled")

    return JsonResponse({
        "ok": True,
        "summary": paper.summary(acc),
        "settings": paper.settings_for(acc),
        "defaults": paper.DEFAULTS,
        "trades": [_row(t) for t in qs.order_by("-opened_at")[:200]],
    })


@require_POST
def api_paper_settings(request):
    """يحفظ الإعدادات — ويتحقّق من كل قيمة قبل الحفظ.

    قيمةٌ سالبة أو صفرية في المخاطرة تُنتج كمّياتٍ سخيفة أو قسمةً
    على صفر بعد ساعات، فيُرفض هنا لا هناك.
    """
    acc = paper.get_or_create_account()
    cur = dict(acc.settings or {})
    errors: list[str] = []

    NUM = {
        "risk_per_trade_pct": (0.05, 10.0),
        "max_position_pct": (1.0, 100.0),
        "max_daily_loss_pct": (0.0, 50.0),
        "target_total_pct": (0.0, 500.0),
        "min_rr": (0.5, 10.0),
        "fee_pct": (0.0, 1.0),
        "slippage_pct": (0.0, 2.0),
        "min_score": (0.0, 100.0),
    }
    for key, (lo, hi) in NUM.items():
        raw = request.POST.get(key)
        if raw in (None, ""):
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{key}: ليس رقماً")
            continue
        if not (lo <= v <= hi):
            errors.append(f"{key}: خارج المدى {lo}–{hi}")
            continue
        cur[key] = v

    raw = request.POST.get("max_open_positions")
    if raw not in (None, ""):
        try:
            n = int(float(raw))
            if 1 <= n <= 50:
                cur["max_open_positions"] = n
            else:
                errors.append("max_open_positions: خارج 1–50")
        except (TypeError, ValueError):
            errors.append("max_open_positions: ليس رقماً")

    for flag in ("require_btc_bullish", "one_trade_per_symbol"):
        raw = request.POST.get(flag)
        if raw is not None:
            cur[flag] = raw in ("1", "true", "on", "yes")

    src = (request.POST.get("source") or "").strip()
    if src in ("pes", "scanner", "golden"):
        cur["source"] = src

    if errors:
        return JsonResponse({"ok": False, "reason": " · ".join(errors)},
                            status=400)
    acc.settings = cur
    acc.save(update_fields=["settings", "updated_at"])
    return JsonResponse({"ok": True, "settings": paper.settings_for(acc)})


@require_POST
def api_paper_reset(request):
    """يعيد المحفظة إلى رأس مالها — ويحذف صفقاتها.

    الحذف صريحٌ ومقصود: محفظةٌ جديدة برصيدٍ جديد وصفقاتٍ قديمة
    تُنتج إحصاءً لا معنى له.
    """
    acc = paper.get_or_create_account()
    try:
        start = float(request.POST.get("initial_balance")
                      or acc.initial_balance)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "reason": "رأس مال غير صالح"},
                            status=400)
    if start <= 0:
        return JsonResponse({"ok": False, "reason": "رأس المال يجب أن يكون موجباً"},
                            status=400)
    n = PaperTrade.objects.filter(account=acc).delete()[0]
    acc.initial_balance = start
    acc.balance = start
    acc.save(update_fields=["initial_balance", "balance", "updated_at"])
    return JsonResponse({"ok": True, "deleted": n, "balance": start})


@require_POST
def api_paper_close(request, trade_id: int):
    """إغلاق يدويّ بسعر السوق."""
    acc = paper.get_or_create_account()
    t = PaperTrade.objects.filter(account=acc, pk=trade_id,
                                  status="open").first()
    if t is None:
        return JsonResponse({"ok": False, "reason": "لا صفقة مفتوحة بهذا الرقم"},
                            status=404)
    px = t.last_price or t.entry
    return JsonResponse(paper.close_trade(acc, t, float(px), "يدويّ"))


@require_POST
def api_paper_tick(request):
    """دورة يدوية: تقييم المفتوحة ثمّ فتح ما تسمح به القواعد."""
    import threading

    def work():
        try:
            from . import paper_engine

            paper_engine.tick()
        except Exception:  # noqa: BLE001
            log.exception("تعذّرت دورة المحفظة")

    threading.Thread(target=work, name="paper-tick", daemon=True).start()
    return JsonResponse({"ok": True, "started": True})
