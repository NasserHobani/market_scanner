# -*- coding: utf-8 -*-
"""المحفظة الحقيقية — عرضٌ وقواعدُ خروج، بلا تنفيذ.

═══ توزيع العمل بين الخادم والمتصفّح ═══

    الخادم    ما يتغيّر ببطء: الأرصدة، متوسّط التكلفة، التاريخ
    المتصفّح  ما يتغيّر كل ثانية: السعر، والربح غير المحقّق

وهذا هو ما يجعل الشاشة **حيّة** بلا بنيةٍ جديدة: ``LiveFeed``
القائم يفتح بثّ Binance العام من المتصفّح، والربح يُحسب من
``(السعر − متوسّط التكلفة) × الكمّية`` لحظةً بلحظة.

والبديل — أن يحسب الخادم الربح ويُرسله كل ثانية — يعني نداءً في
الثانية لكل متصفّح، ومفاتيحَ حسابٍ تُستعمل ستّين مرّة في الدقيقة
بلا حاجة.

═══ والقراءة مخبّأة ═══

``/api/v3/myTrades`` نداءٌ لكل رمز. وحسابٌ فيه عشرون أصلاً يعني
عشرين طلباً — وفتحُ الصفحة مرّتين يضاعفها. فتُخبّأ الصورة دقائق،
ويُجبَر التحديث بزرّ.
"""
from __future__ import annotations

import json
import logging
import time

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.wallet")

_CACHE: dict = {}
_TTL = 180.0


def _snapshot(force: bool = False) -> dict:
    hit = _CACHE.get("snap")
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return {**hit[1], "cached": True,
                "age": int(time.time() - hit[0])}

    from scanner.portfolio import binance_positions as bp

    data = bp.build()
    _CACHE["snap"] = (time.time(), data)
    return {**data, "cached": False, "age": 0}


def wallet_page(request):
    from scanner.adapters import binance_account as ba

    return render(request, "dashboard/wallet.html", {
        "nav_page": "wallet",
        "configured": ba.configured(),
    })


@require_GET
def api_wallet(request):
    """المراكز ومتوسّط التكلفة — والأسعار تأتي للمتصفّح من البثّ."""
    from .models import WalletRule

    force = request.GET.get("refresh") == "1"
    snap = _snapshot(force=force)

    rules: dict[str, list] = {}
    for r in WalletRule.objects.all():
        rules.setdefault(r.symbol.upper(), []).append({
            "id": r.id, "kind": r.kind,
            "kind_label": dict(r.KINDS).get(r.kind, r.kind),
            "price": r.price, "pct": r.pct, "active": r.active,
            "peak": r.peak, "note": r.note,
            "fired_at": r.fired_at.isoformat() if r.fired_at else None,
            "fire_count": r.fire_count,
        })

    for p in snap.get("positions", []):
        p["rules"] = rules.get(p["symbol"].upper(), [])

    return JsonResponse({**snap, "rules_count": sum(
        len(v) for v in rules.values())})


@require_GET
def api_wallet_health(request):
    """صلاحيات المفتاح — وهو أوّل ما يجب أن يُرى.

    مفتاحٌ يسمح بالسحب على خادمٍ بلا HTTPS خطرٌ حقيقيّ، وإخفاؤه
    خلف شاشةٍ جميلة لا يجعله أقلّ خطراً.
    """
    from scanner.adapters import binance_account as ba

    if not ba.configured():
        return JsonResponse({
            "ok": False, "configured": False,
            "why": "مفاتيح Binance غير مضبوطة. أنشئ مفتاحاً **للقراءة "
                   "فقط** وأضفه في بورتينر ← Environment variables: "
                   "BINANCE_API_KEY و BINANCE_API_SECRET.",
        })
    try:
        return JsonResponse({"ok": True, "configured": True,
                             **ba.restrictions()})
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "configured": True,
                             "why": str(exc)[:240]})


@require_GET
def api_wallet_trades(request):
    """تاريخ صفقات رمزٍ واحد — بنداءٍ صريح لا مع كل فتح صفحة."""
    from scanner.adapters import binance_account as ba

    symbol = (request.GET.get("symbol") or "").strip().upper()
    if not symbol.isalnum() or len(symbol) > 24:
        return JsonResponse({"ok": False, "reason": "رمز غير صالح"},
                            status=400)
    try:
        trades = ba.my_trades(symbol)
    except ba.BinanceAuthError as exc:
        return JsonResponse({"ok": False, "reason": str(exc)[:240]},
                            status=400)

    from scanner.portfolio.binance_positions import cost_basis, roundtrips

    return JsonResponse({"ok": True, "symbol": symbol,
                         "trades": trades[::-1],      # الأحدث أوّلاً
                         "basis": cost_basis(trades),
                         # كل بيعٍ صفقةٌ مغلقة بربحها الصافي
                         "roundtrips": roundtrips(trades, symbol)})


@require_GET
def api_wallet_closed(request):
    """الصفقات المغلقة عبر الحساب كلّه — ربحاً وخسارةً بعد العمولة.

    ═══ ولماذا نداءٌ منفصل ═══

    ``myTrades`` نداءٌ **لكل رمز**. وحسابٌ فيه عشرون أصلاً يعني
    عشرين طلباً — ووضعُها في نداء المراكز يجعل فتح الصفحة ينتظرها
    كلّها. فتُطلَب حين تُطلَب، وتُخبّأ.
    """
    from scanner.adapters import binance_account as ba
    from scanner.portfolio.binance_positions import roundtrips

    hit = _CACHE.get("closed")
    force = request.GET.get("refresh") == "1"
    if hit and not force and (time.time() - hit[0]) < _TTL:
        return JsonResponse({"ok": True, "cached": True, **hit[1]})

    snap = _snapshot()
    if not snap.get("ok"):
        return JsonResponse({"ok": False, "why": snap.get("why", "تعذّر")})

    # ═══ الرموز التي لها تاريخ ═══
    #
    # المراكز القائمة **وحدها** لا تكفي: من باع كل ما يملك من رمزٍ
    # لم يعد له رصيد، وصفقاته المغلقة هي بالضبط ما يُسأل عنه.
    # فتُضاف رموز الأوامر المعلّقة وقواعد الخروج معها.
    from .models import WalletRule

    symbols = {p["symbol"].upper() for p in snap.get("positions", [])}
    try:
        symbols |= {o["symbol"].upper() for o in ba.open_orders()}
    except ba.BinanceAuthError:
        pass
    symbols |= {r.symbol.upper() for r in WalletRule.objects.all()}
    extra = (request.GET.get("symbols") or "").upper()
    symbols |= {s.strip() for s in extra.split(",") if s.strip().isalnum()}

    from scanner.portfolio.binance_positions import trades_for

    groups, failed = [], []
    for sym in sorted(symbols)[:40]:
        try:
            # ``trades_for`` لا ``my_trades``: ``build`` جلبها قبل
            # قليل لحساب متوسّط التكلفة، وإعادةُ جلبها ضِعفُ
            # الطلبات لنفس البيانات وضِعفُ انتظار الصفحة.
            rt = roundtrips(trades_for(sym), sym)
        except ba.BinanceAuthError as exc:
            failed.append(f"{sym}: {str(exc)[:60]}")
            continue
        if rt["n"]:
            groups.append(rt)

    closed = [r for g in groups for r in g["closed"]]
    closed.sort(key=lambda r: r.get("closed_at") or 0, reverse=True)
    wins = [r for r in closed if r["won"]]

    other: dict[str, float] = {}
    for g in groups:
        for k, v in (g.get("other_fees") or {}).items():
            other[k] = round(other.get(k, 0.0) + v, 8)

    data = {
        "closed": closed,
        "n": len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "win_rate": round(len(wins) / len(closed) * 100.0, 1) if closed else None,
        "net": round(sum(r["net"] for r in closed), 8),
        "gross_win": round(sum(r["net"] for r in wins), 8),
        "gross_loss": round(sum(r["net"] for r in closed if not r["won"]), 8),
        "fees_quote": round(sum(r["fee_quote"] for r in closed), 8),
        "other_fees": other,
        "symbols": len(groups),
        "failed": failed,
        "method": "FIFO",
        "notes": sorted({n for g in groups for n in g.get("notes", [])}),
    }
    _CACHE["closed"] = (time.time(), data)
    return JsonResponse({"ok": True, "cached": False, **data})


@require_GET
def api_wallet_orders(request):
    from scanner.adapters import binance_account as ba

    try:
        return JsonResponse({"ok": True, "orders": ba.open_orders()})
    except ba.BinanceAuthError as exc:
        return JsonResponse({"ok": False, "reason": str(exc)[:240]},
                            status=400)


# ═══════════════════════════════════════════════════════════════
#  قواعد الخروج
# ═══════════════════════════════════════════════════════════════

VALID_KINDS = ("stop", "target", "trail", "signal")


@require_POST
def api_rule_save(request):
    """يحفظ قاعدة خروج — ويتحقّق قبل الحفظ لا بعده."""
    from .models import WalletRule

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "reason": "صيغة غير صالحة"},
                            status=400)

    symbol = str(body.get("symbol") or "").strip().upper()
    kind = str(body.get("kind") or "").strip()
    if not symbol or kind not in VALID_KINDS:
        return JsonResponse({"ok": False, "reason": "رمز أو نوع غير صالح"},
                            status=400)

    price = body.get("price")
    pct = body.get("pct")
    # ═══ الشرط المعطوب يُرفَض قبل الحفظ ═══
    #
    # وقفٌ بلا سعر أو تراجعٌ بلا نسبة يُحفَظ فيفشل صامتاً عند كل
    # دورة: لا تنبيه، ولا شيء يقول لماذا.
    if kind in ("stop", "target"):
        try:
            price = float(price)
        except (TypeError, ValueError):
            return JsonResponse(
                {"ok": False, "reason": "هذا النوع يحتاج سعراً"}, status=400)
        if price <= 0:
            return JsonResponse({"ok": False, "reason": "السعر يجب أن يكون موجباً"},
                                status=400)
        pct = None
    elif kind == "trail":
        try:
            pct = float(pct)
        except (TypeError, ValueError):
            return JsonResponse(
                {"ok": False, "reason": "التراجع يحتاج نسبة مئوية"},
                status=400)
        if not (0 < pct < 100):
            return JsonResponse(
                {"ok": False, "reason": "النسبة بين 0 و 100"}, status=400)
        price = None
    else:
        price = pct = None

    rule, _ = WalletRule.objects.update_or_create(
        symbol=symbol, kind=kind,
        defaults={
            "asset": str(body.get("asset") or "")[:16],
            "price": price, "pct": pct,
            "active": bool(body.get("active", True)),
            "note": str(body.get("note") or "")[:160],
        })
    # ═══ والقمّة تُصفَّر عند التعديل ═══
    #
    # نسبةُ تراجعٍ جديدة على قمّةٍ قديمة تقيس ما لم يُقصَد — وقد
    # تُطلق فوراً على قمّةٍ بلغها الرمز قبل أسابيع.
    if kind == "trail":
        rule.peak = None
        rule.peak_at = None
        rule.fired_at = None
        rule.save(update_fields=["peak", "peak_at", "fired_at", "updated_at"])

    return JsonResponse({"ok": True, "id": rule.id})


@require_POST
def api_rule_delete(request):
    from .models import WalletRule

    rid = (request.POST.get("id") or "").strip()
    if not rid.isdigit():
        return JsonResponse({"ok": False, "reason": "معرّف غير صالح"},
                            status=400)
    n, _ = WalletRule.objects.filter(pk=int(rid)).delete()
    return JsonResponse({"ok": bool(n)})


@require_POST
def api_wallet_check(request):
    """فحصٌ فوريّ للقواعد — بدل انتظار الدورة."""
    from . import wallet_monitor

    try:
        return JsonResponse({"ok": True, **wallet_monitor.run_once()})
    except Exception as exc:  # noqa: BLE001
        log.exception("تعذّر فحص قواعد المحفظة")
        return JsonResponse({"ok": False, "reason": str(exc)[:240]},
                            status=500)
