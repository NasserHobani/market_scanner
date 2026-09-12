# -*- coding: utf-8 -*-
"""إدارة الرموز المحظورة — قرار المستخدم، والنظام ينفّذ.

النظام لا يفتي ولا يضيف رمزاً هنا من تلقائه. وحقل «المصدر» ليس
توثيقاً للبرنامج بل تذكرةً لصاحب القرار: على أيّ هيئةٍ أو فتوى
بنى، ومتى يراجع.
"""
from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from . import blocklist
from .jsonsafe import JsonResponse
from .models import BlockedSymbol

log = logging.getLogger("dashboard.blocked")


def _row(b) -> dict:
    return {
        "id": b.id, "market": b.market, "symbol": b.symbol,
        "scope": b.scope, "scope_label": b.get_scope_display(),
        "reason": b.reason, "source": b.source, "note": b.note,
        "active": b.active,
        "created_at": b.created_at.isoformat() if b.created_at else "",
    }


def blocked_page(request):
    from .views import MARKETS, market_options

    return render(request, "dashboard/blocked.html", {
        "nav_page": "blocked",
        "markets": MARKETS,
        "market_options": market_options(),
        "scopes": BlockedSymbol.SCOPES,
    })


@require_GET
def api_blocked(request):
    from django.db.utils import OperationalError, ProgrammingError

    try:
        rows = list(BlockedSymbol.objects.all())
    except (OperationalError, ProgrammingError):
        return JsonResponse({"ok": False,
                             "reason": "شغّل: python web/manage.py migrate"},
                            status=503)
    market = (request.GET.get("market") or "").strip()
    if market:
        rows = [b for b in rows if b.market == market]
    return JsonResponse({"ok": True, "blocked": [_row(b) for b in rows],
                         "total": len(rows)})


@require_POST
def api_block_add(request):
    """يحظر رمزاً — أو عدّة رموز ملصوقة دفعةً واحدة.

    اللصق الجماعي مقصود: من عنده قائمة هيئةٍ بخمسين رمزاً لا
    يُدخلها واحداً واحداً، ولو لزمه ذلك لما فعل.
    """
    from .views import MARKETS

    market = (request.POST.get("market") or "").strip()
    if market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "سوق غير معروف"},
                            status=400)
    raw = (request.POST.get("symbols") or request.POST.get("symbol") or "")
    # يُقبل الفاصل بالسطر أو الفاصلة أو المسافة — لا يُفرض شكل
    parts = [p.strip().upper() for p in
             raw.replace(",", "\n").replace(" ", "\n").split("\n")
             if p.strip()]
    if not parts:
        return JsonResponse({"ok": False, "reason": "لا رمز"}, status=400)

    scope = (request.POST.get("scope") or "base").strip()
    if scope not in dict(BlockedSymbol.SCOPES):
        scope = "base"
    reason = (request.POST.get("reason") or "").strip()[:200]
    source = (request.POST.get("source") or "").strip()[:200]
    note = (request.POST.get("note") or "").strip()[:2000]

    added, existed = [], []
    for sym in parts[:500]:
        obj, created = BlockedSymbol.objects.get_or_create(
            market=market, symbol=sym,
            defaults={"scope": scope, "reason": reason, "source": source,
                      "note": note, "active": True},
        )
        if created:
            added.append(sym)
        else:
            # الموجود يُعاد تفعيله ولا يُكرَّر — ولا يُمحى سببُه
            # القديم بفراغ.
            existed.append(sym)
            changed = []
            if not obj.active:
                obj.active, _ = True, changed.append("active")
            if reason and not obj.reason:
                obj.reason = reason
                changed.append("reason")
            if source and not obj.source:
                obj.source = source
                changed.append("source")
            if changed:
                obj.save()
    blocklist.refresh()
    return JsonResponse({"ok": True, "added": added, "existed": existed,
                         "count": len(added)})


@require_POST
def api_block_remove(request, block_id: int):
    b = BlockedSymbol.objects.filter(pk=block_id).first()
    if b is None:
        return JsonResponse({"ok": False, "reason": "غير موجود"}, status=404)
    sym = b.symbol
    b.delete()
    blocklist.refresh()
    return JsonResponse({"ok": True, "removed": sym})


@require_POST
def api_block_toggle(request, block_id: int):
    """يعطّل الحظر مؤقّتاً بلا حذفه — فيبقى السبب والمصدر."""
    b = BlockedSymbol.objects.filter(pk=block_id).first()
    if b is None:
        return JsonResponse({"ok": False, "reason": "غير موجود"}, status=404)
    b.active = not b.active
    b.save(update_fields=["active", "updated_at"])
    blocklist.refresh()
    return JsonResponse({"ok": True, "active": b.active, "row": _row(b)})


@require_GET
def api_block_check(request):
    """هل هذا الرمز محظور؟ — لأزرار الواجهة."""
    market = (request.GET.get("market") or "").strip()
    symbol = (request.GET.get("symbol") or "").strip()
    return JsonResponse({"ok": True,
                         "blocked": blocklist.is_blocked(market, symbol),
                         "base": blocklist.base_of(symbol, market)})
