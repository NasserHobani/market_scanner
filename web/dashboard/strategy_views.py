# -*- coding: utf-8 -*-
"""بناء الاستراتيجيات وعرض نتائجها بطاقاتٍ في أعمدة.

شاشتان:

    /strategies/        البناء — اختر حقولاً وضع عتبات واحفظ
    /board/             اللوحة — عمودٌ لكلّ استراتيجية وبطاقةٌ لكل رمز

وكلتاهما تقرأ مسح ‏PES المحفوظ ولا تحسب شيئاً: الفرز على قيمٍ
مخزّنة، فيُنفَّذ داخل الطلب بلا أن يشغل الخادم دقائق.
"""
from __future__ import annotations

import json
import logging

from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.strategies")


def builder_page(request):
    from scanner.strategies import custom

    from .views import MARKETS, market_options

    return render(request, "dashboard/strategy_builder.html", {
        "nav_page": "strategies",
        "markets": MARKETS,
        "market_options": market_options(),
        # ═══ الحقول من السجلّ لا من القالب ═══
        #
        # كتابتها في القالب تعني أنّ إضافة حقلٍ تحتاج تعديلين —
        # ويُنسى أحدهما، فيُعرَض حقلٌ لا يُفرَز به أو العكس.
        #
        # ═══ وتُمرَّر كائناً لا نصّاً ═══
        #
        # ‏``json_script`` يُسلسِل ما يُعطى. وتمريرُ ``json.dumps``
        # إليه يُشفّرها مرّتين: يصير محتوى الوسم **نصّاً** لا
        # مصفوفة، فيعيد ``JSON.parse`` سلسلةً — و‏``FIELDS.forEach
        # is not a function``.
        "catalog": custom.field_catalog(),
        "ops": {k: {"label": v["label"], "arity": v["arity"]}
                for k, v in custom.OPS.items()},
    })


def board_page(request):
    from .views import MARKETS, market_options

    return render(request, "dashboard/strategy_board.html", {
        "nav_page": "board",
        "markets": MARKETS,
        "market_options": market_options(),
    })


# ═══════════════════════════════════════════════════════════════
#  واجهة البيانات
# ═══════════════════════════════════════════════════════════════

@require_GET
def api_strategies(request):
    from scanner.strategies import custom_store as store

    return JsonResponse({"ok": True, "strategies": store.list_all(),
                         "max": store.MAX_STRATEGIES})


@require_POST
def api_strategy_save(request):
    from scanner.strategies import custom_store as store

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"ok": False, "reason": "صيغة غير صالحة"},
                            status=400)

    ok, why = store.save(payload)
    if not ok:
        # ═══ السبب يُعاد للواجهة ═══
        #
        # «تعذّر الحفظ» وحدها تترك المستخدم يخمّن. والسبب هنا
        # نصٌّ جاهز من ``validate`` يذكر رقم الشرط وما فيه.
        return JsonResponse({"ok": False, "reason": why}, status=400)
    return JsonResponse({"ok": True, "saved": payload.get("name")})


@require_POST
def api_strategy_delete(request):
    from scanner.strategies import custom_store as store

    name = (request.POST.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": False, "reason": "بلا اسم"}, status=400)
    return JsonResponse({"ok": store.delete(name)})


@require_GET
def api_board(request):
    """أعمدة اللوحة — عمودٌ لكل استراتيجية فعّالة."""
    from scanner.strategies import custom_store as store

    from .views import MARKETS

    market = (request.GET.get("market") or "").strip()
    only = (request.GET.get("strategy") or "").strip()
    wanted = [market] if market in MARKETS else None

    columns = []
    for s in store.list_all():
        if only and s.get("name") != only:
            continue
        if not s.get("active", True):
            continue
        try:
            columns.append(store.run(s, markets=wanted))
        except Exception as exc:  # noqa: BLE001
            # ═══ عمودٌ يفشل لا يُسقط اللوحة ═══
            #
            # استراتيجيةٌ واحدة معطوبة كانت ستُخفي البقيّة. وهي
            # تظهر الآن عموداً فيه سببُ فشلها.
            log.warning("تعذّر تشغيل «%s»: %s", s.get("name"),
                        str(exc)[:140])
            columns.append({"name": s.get("name"), "error": str(exc)[:160],
                            "cards": [], "matched": 0, "scanned": 0})
    return JsonResponse({"ok": True, "columns": columns})
