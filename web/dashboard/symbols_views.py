# -*- coding: utf-8 -*-
"""دليل الرموز — جردٌ لما يملكه النظام، بلا تحليل ولا حكم.

═══ لماذا شاشةٌ بلا تحليل ═══

كل شاشةٍ أخرى تعرض ما **نجا** من مرشِّح: الماسح يعرض من تجاوز
عتبة، و‏PES يعرض من بلغ مرحلة. فالرمز الغائب عنها غائبٌ لسببين لا
يمكن التمييز بينهما من الشاشة:

    لم يجتز الشرط      ← النظام يعمل
    لا شموع له أصلاً   ← النظام أعمى عنه

وهذا الالتباس كلّفنا هذه الجلسة مرّتين: سوقٌ كريبتو بعشرة رموز
بدا سوقاً هادئاً، وسوقٌ سعوديٌّ بصفر رمز بدا سوقاً بلا فرص.

فهذه الشاشة لا تُرشِّح شيئاً. تقول: هذا ما اكتُشف، وهذا ما له
شموع، وهذه آخر شمعة. والناقص يظهر بوصفه ناقصاً.

═══ ولا تحسب شيئاً ═══

لا مؤشّر ولا درجة ولا توصية. قراءةُ ذيل ملفٍّ لكل رمز — وهي أسرع
من تحميله بمئة مرّة، فتُحتمَل داخل الطلب بلا ملفٍّ محفوظ.
"""
from __future__ import annotations

import logging
import time

from django.shortcuts import render
from django.views.decorators.http import require_GET

from . import blocklist
from .jsonsafe import JsonResponse

log = logging.getLogger("dashboard.symbols")

#: الفريمات المعروضة في عمود «الشموع» — ترتيبها ثابت
TFS = ("15m", "1h", "4h", "1d")


def symbols_page(request):
    from .views import MARKETS, market_options

    return render(request, "dashboard/symbols.html", {
        "nav_page": "symbols",
        "markets": MARKETS,
        "market_options": market_options(),
        "timeframes": list(TFS),
    })


@require_GET
def api_symbols(request):
    from scanner import storage
    from scanner.market_sync import get_service

    from .views import MARKETS

    market = (request.GET.get("market") or "").strip()
    q = (request.GET.get("q") or "").strip().upper()
    only = (request.GET.get("only") or "").strip()   # "missing" | "blocked"

    wanted = [market] if market in MARKETS else list(MARKETS)
    groups, missing_scan = [], []

    for m in wanted:
        t0 = time.perf_counter()
        # ═══ الكون أوّلاً ثمّ القرص ═══
        #
        # البدء من القرص يُظهر الموجود وحده — وهو بالضبط ما يخفي
        # النقص. فالقائمة من الاكتشاف، والقرص يملأ حالتها.
        try:
            universe = list(get_service().resolve_symbols(m))
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر اكتشاف كون %s: %s", m, str(exc)[:120])
            universe = []
            missing_scan.append(m)

        on_disk = {tf: set(storage.stored_symbols(m, tf)) for tf in TFS}
        # ورموزٌ لها شموع ولم يعد الاكتشاف يذكرها: مشطوبة أو
        # هبط حجمها. تُعرَض أيضاً — وإلّا اختفت بلا خبر.
        extra = sorted(set().union(*on_disk.values()) - set(universe))
        allsyms = list(universe) + extra

        rows = []
        for s in allsyms:
            if q and q not in s.upper():
                continue
            have = [tf for tf in TFS if s in on_disk[tf]]
            last_t, bars = None, None
            if have:
                # آخر فريمٍ متاح: ذيلُ الملفّ لا تحميله
                tf = have[-1]
                try:
                    t = storage.last_time_on_disk(m, s, tf)
                    last_t = None if t is None else t.isoformat()
                except Exception:  # noqa: BLE001
                    last_t = None
            blocked = False
            try:
                blocked = bool(blocklist.is_blocked(m, s))
            except Exception:  # noqa: BLE001
                pass
            row = {
                "symbol": s, "market": m,
                "timeframes": have,
                "tf_count": len(have),
                "last_candle": last_t,
                "blocked": blocked,
                "discovered": s in set(universe),
                "bars": bars,
            }
            if only == "missing" and have:
                continue
            if only == "blocked" and not blocked:
                continue
            rows.append(row)

        groups.append({
            "market": m,
            "discovered": len(universe),
            "listed": len(rows),
            "total": len(allsyms),
            "with_candles": sum(1 for r in rows if r["tf_count"]),
            "without_candles": sum(1 for r in rows if not r["tf_count"]),
            "blocked": sum(1 for r in rows if r["blocked"]),
            "orphans": len(extra),
            "elapsed_ms": round((time.perf_counter() - t0) * 1000),
            # ═══ السقف يُعلَن ═══
            #
            # قصٌّ صامت عند ٥٠٠ يجعل «٥٠٠ رمزاً» تُقرأ سوقاً من
            # خمسمئة — وقد يكون ألفاً.
            "rows": rows[:500],
            "truncated": max(0, len(rows) - 500),
        })

    return JsonResponse({"ok": True, "groups": groups,
                         "timeframes": list(TFS),
                         "discovery_failed": missing_scan})


# ═══════════════════════════════════════════════════════════════
#  جلب كل رموز سوق — زرٌّ في الإعدادات
# ═══════════════════════════════════════════════════════════════
#
# ═══ لماذا في خيطٍ وبحالةٍ تُسأل ═══
#
# ملءُ سوقٍ كامل مئاتُ الطلبات وعشراتُ الدقائق. وتشغيلُه داخل
# الطلب يعني متصفّحاً ينتظر حتى ينقطع، وخادماً يظنّ المستخدم أنّه
# تعلّق. فيبدأ في خيطٍ، وتُسأل حالتُه من الواجهة.
#
# ولا يُستبدَل بمهمّة ``market_sync`` المجدولة: تلك للتحديث
# الدوريّ، وهذا للملء **الأوّل** حين يكون السوق فارغاً.

_FILL: dict[str, dict] = {}


def _fill_worker(market: str) -> None:
    from scanner import storage
    from scanner.market_sync import get_service

    st = _FILL[market]
    try:
        svc = get_service()
        universe = list(svc.resolve_symbols(market))
        have = set(storage.stored_symbols(market, "4h"))
        todo = [s for s in universe if s not in have]
        st.update(discovered=len(universe), missing=len(todo),
                  phase="sync" if todo else "done")
        if not todo:
            st.update(running=False, ok=True,
                      note="لا ينقص شيء — كل رمزٍ مكتشَف له شموع")
            return
        out = svc.sync_market(market, symbols=todo)
        st.update(
            running=False, ok=True, phase="done",
            synced=int(out.get("successful") or 0),
            failed=int(out.get("failed") or 0),
            note=f"نجح {out.get('successful')} · فشل {out.get('failed')}",
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("تعذّر ملء %s", market)
        st.update(running=False, ok=False, phase="error",
                  note=str(exc)[:200])


def api_fill_market(request):
    import threading

    from .views import MARKETS

    if request.method != "POST":
        # الحالة تُقرأ بـGET — الواجهة تسأل كل بضع ثوانٍ
        return JsonResponse({"ok": True, "state": _FILL})

    market = (request.POST.get("market") or "").strip()
    if market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "سوق غير معروف"},
                            status=400)
    cur = _FILL.get(market)
    # ═══ لا تشغيلان معاً ═══
    #
    # ضغطتان على الزرّ تعنيان ضعف الطلبات على المنصّة نفسها —
    # وأسرعُ طريقٍ إلى حدّ المعدّل هو الاستعجال.
    if cur and cur.get("running"):
        return JsonResponse({"ok": False, "reason": "جارٍ بالفعل",
                             "state": cur})

    _FILL[market] = {"running": True, "ok": None, "phase": "discover",
                     "started_at": time.time(), "market": market,
                     "discovered": None, "missing": None,
                     "synced": 0, "failed": 0, "note": ""}
    threading.Thread(target=_fill_worker, args=(market,),
                     name=f"fill-{market}", daemon=True).start()
    return JsonResponse({"ok": True, "started": market,
                         "state": _FILL[market]})
