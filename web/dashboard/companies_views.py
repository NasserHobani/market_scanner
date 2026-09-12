# -*- coding: utf-8 -*-
"""دليل الشركات — جلبٌ على مرحلتين مع تقدّم مرئيّ.

═══ لماذا مرحلتان ═══

سؤال «من في السوق؟» رخيصٌ ومجاني: ``/companies/`` يعطي تاسي ونمو
كاملين في طلبين. وسؤال «ما تاريخ هذا السهم؟» غالٍ: ثلاثمئة طلب،
دقائق من الانتظار.

وربطهما في زرٍّ واحد يعني أنّ أي تعثّر في الثاني يُضيّع الأوّل.
فالفصل يجعل السوق **معروفةً** خلال ثوانٍ، والتاريخ يُبنى على مهل
بعدها — وإن انقطع استُؤنف من حيث وقف.

═══ ولماذا التقدّم لا الانتظار ═══

الطلب المتزامن لثلاثمئة رمز عبر ياهو ينتهي بمهلة الخادم، فيرى
المستخدم خطأً بينما العمل كان يجري فعلاً. والخلفية مع استعلام
تقدّم تفصل «طال» عن «فشل» — وهما حالتان لا يجوز أن تبدوا واحدة.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from scanner import storage

from . import jobs
from .jsonsafe import JsonResponse
from .models import Company

log = logging.getLogger("dashboard.companies")

# ═══════════════════════════ المرحلة ١: الشركات ═══════════════════════

def _fetch_info(market: str, with_quotes: bool, with_fundamentals: bool,
                only_missing: bool = True) -> None:
    """المرحلة ١ — الأسماء دفعةً، ثمّ المعلومات رمزاً رمزاً.

    ═══ لماذا الاستئناف ═══

    ‏``/companies/`` لا يعطي القطاع؛ القطاع في ``/company/{symbol}/``
    وحده — أي **طلبٌ لكل شركة**، ثلاثمئة طلب وعدّة دقائق.

    وأي انقطاع في تلك الدقائق (إعادة تحميل الخادم عند تعديل ملف،
    انقطاع شبكة، حدّ معدّل) كان يُضيّع الجولة كلّها ويُلزم بإعادة
    الثلاثمئة من الصفر. ووقع فعلاً: توقّفت عند تسعٍ وعشرين، فبقي
    ٩١٪ من السوق بلا قطاع.

    فالافتراض الآن **إكمال الناقص**: تُتخطّى الشركة التي لها قطاع
    أصلاً. والضغط على الزر مرّةً بعد مرّة يُكمل حتى يكتمل، ولا يُعيد
    ما تمّ.
    """
    from scanner.adapters import get_adapter
    from scanner.config import load_market
    from django.conf import settings as dj

    try:
        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        adapter = get_adapter(getattr(cfg, "universe_adapter", "")
                              or cfg.adapter)
        rows = adapter.companies() if hasattr(adapter, "companies") else []
        if not rows:
            jobs.finish("info", "لم تُعِد المنصّة شركات", "قائمة فارغة")
            return

        jobs.set_total("info", len(rows) * (2 if with_quotes else 1))

        now = timezone.now()
        seen: list[str] = []
        for r in rows:
            sym = r["symbol"]
            seen.append(sym)
            Company.objects.update_or_create(
                market=market, symbol=sym,
                defaults={
                    "name_ar": (r.get("name") or "")[:160],
                    "sub_market": str(r.get("market") or "")[:32],
                    "info_updated_at": now,
                },
            )
            jobs.step("info", f"الشركات: {sym}")

        # الأسعار والأساسيات رمزاً رمزاً — الباقة المجانية لا تعطي
        # المجمَّع. تُجرى بعد حفظ الأسماء كي لا يضيع الدليل إن تعثّرت.
        if with_quotes:
            done_syms = set()
            if only_missing:
                # «مكتملة» = لها قطاع. القطاع أوّل ما يعطيه
                # ``/company/`` مجاناً، فغيابه دليلٌ كافٍ على أنّ
                # الشركة لم تُثرَ بعد.
                done_syms = set(Company.objects
                                .filter(market=market)
                                .exclude(sector="")
                                .values_list("symbol", flat=True))
                jobs.set_total("info",
                               len(rows) + len(seen) - len(done_syms))
            enriched = skipped = errored = 0
            for sym in seen:
                if sym in done_syms:
                    skipped += 1
                    continue
                fields: dict[str, Any] = {}
                try:
                    q = adapter.quote_one(sym)
                    price = _num(q.get("price"))
                    vol = _num(q.get("volume"))
                    fields.update(price=price, volume=vol,
                                  change_pct=_num(q.get("change_pct")))
                    if price is not None and vol is not None:
                        fields["quote_value"] = price * vol
                except Exception as exc:  # noqa: BLE001
                    log.debug("سعر %s: %s", sym, str(exc)[:80])
                if with_fundamentals and hasattr(adapter, "company_info"):
                    try:
                        fields.update(adapter.company_info(sym))
                    except Exception as exc:  # noqa: BLE001
                        log.debug("ملفّ %s: %s", sym, str(exc)[:80])
                if fields:
                    fields["info_updated_at"] = timezone.now()
                    Company.objects.filter(market=market, symbol=sym).update(
                        **fields)
                    enriched += 1
                else:
                    errored += 1
                jobs.step("info", f"المعلومات: {sym}"
                          f" — أُثريت {enriched} · تعذّرت {errored}")

            _refresh_candle_stats(market)
            remaining = Company.objects.filter(
                market=market, sector="").count()
            jobs.finish("info",
                        f"{len(seen)} شركة · أُثريت {enriched}"
                        + (f" · تُخطّيت {skipped} (مكتملة)" if skipped else "")
                        + (f" · تعذّرت {errored}" if errored else "")
                        + (f" · ما زال {remaining} بلا قطاع — اضغط ثانيةً"
                           if remaining else " · اكتمل السوق"))
            return

        _refresh_candle_stats(market)
        jobs.finish("info", f"حُفظت {len(seen)} شركة (بلا معلومات)")
    except Exception as exc:  # noqa: BLE001
        jobs.finish("info", "تعذّر الجلب", str(exc)[:250])


def _num(v) -> float | None:
    if v in (None, "", "-"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _refresh_candle_stats(market: str) -> None:
    """حالة التاريخ تُقرأ من **القرص** لا من المزوّد.

    الجدول يقول «هذه الشركة عندها ٨٠٠ شمعة» — ومصدر هذا الادّعاء
    يجب أن يكون الملف نفسه. سؤال المزوّد يجعل الجدول يعِد بما قد لا
    يكون عندنا.
    """
    from django.conf import settings as dj
    from scanner.config import load_market

    try:
        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        tf = cfg.timeframes[0]
    except Exception:  # noqa: BLE001
        tf = "1d"
    for c in Company.objects.filter(market=market).iterator():
        last = storage.last_time_on_disk(market, c.symbol, tf)
        n = 0
        if last is not None:
            df = storage.load(market, c.symbol, tf)
            n = 0 if df is None else len(df)
        if c.candles != n or (last is not None and c.last_candle != last):
            Company.objects.filter(pk=c.pk).update(
                candles=n,
                last_candle=(None if last is None else last.to_pydatetime()),
            )


# ═══════════════════════════ المرحلة ٢: التاريخ ═══════════════════════

def _fetch_history(market: str, only_missing: bool, *, limit: int = 0) -> None:
    from django.conf import settings as dj
    from scanner.adapters import get_adapter
    from scanner.config import load_market

    try:
        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        tf = cfg.timeframes[0]
        adapter = get_adapter(cfg.adapter)

        qs = Company.objects.filter(market=market)
        if only_missing:
            qs = qs.filter(candles=0)
        symbols = list(qs.values_list("symbol", flat=True))
        if limit:
            symbols = symbols[:limit]
        if not symbols:
            jobs.finish("history", "لا شركات تنتظر التاريخ — اجلب الشركات أوّلاً"
                    if not Company.objects.filter(market=market).exists()
                    else "كل الشركات لها تاريخ")
            return

        jobs.set_total("history", len(symbols))

        ok = failed = 0
        for sym in symbols:
            try:
                cached = storage.load(market, sym, tf)
                need = storage.bars_needed(cached, tf, cfg.candles)
                if need > 0:
                    fresh = adapter.fetch(sym, tf, need)
                    merged = storage.merge(cached, fresh)
                    storage.save(market, sym, tf, merged)
                    n = len(merged)
                    last = storage.last_time(merged)
                else:
                    n = 0 if cached is None else len(cached)
                    last = storage.last_time(cached)
                Company.objects.filter(market=market, symbol=sym).update(
                    candles=n,
                    last_candle=(None if last is None else last.to_pydatetime()),
                )
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                log.debug("تاريخ %s: %s", sym, str(exc)[:100])
            jobs.step("history", f"{sym} — نجح {ok} · تعذّر {failed}")

        jobs.finish("history", f"اكتمل: {ok} نجحت · {failed} تعذّرت")
    except Exception as exc:  # noqa: BLE001
        jobs.finish("history", "تعذّر جلب التاريخ", str(exc)[:250])


# ═════════════════════════════ نقاط النهاية ═══════════════════════════

@require_POST
def api_companies_fetch(request):
    market = (request.POST.get("market") or request.GET.get("market")
              or "saudi").strip().lower()
    with_quotes = (request.POST.get("quotes") or "1") != "0"
    with_fund = (request.POST.get("fundamentals") or "1") != "0"

    if not jobs.begin("info", scope=market, note="يبدأ…"):
        return JsonResponse({"ok": True, "already": True, **jobs.snapshot("info")})
    only_missing = (request.POST.get("only_missing") or "1") != "0"
    jobs.run_in_thread("info", _fetch_info, market, with_quotes, with_fund,
                       only_missing, name="companies-info")
    return JsonResponse({"ok": True, **jobs.snapshot("info")})


@require_POST
def api_companies_history(request):
    market = (request.POST.get("market") or "saudi").strip().lower()
    only_missing = (request.POST.get("only_missing") or "1") != "0"
    if not jobs.begin("history", scope=market, note="يبدأ…"):
        return JsonResponse({"ok": True, "already": True,
                             **jobs.snapshot("history")})
    jobs.run_in_thread("history", _fetch_history, market, only_missing,
                       name="companies-history")
    return JsonResponse({"ok": True, **jobs.snapshot("history")})


@require_GET
def api_companies_status(request):
    return JsonResponse({"ok": True, "info": jobs.snapshot("info"),
                         "history": jobs.snapshot("history")})


@require_GET
def api_companies(request):
    market = (request.GET.get("market") or "saudi").strip().lower()
    q = (request.GET.get("q") or "").strip()
    sector = (request.GET.get("sector") or "").strip()

    qs = Company.objects.filter(market=market)
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(symbol__icontains=q) | Q(name_ar__icontains=q)
                       | Q(name_en__icontains=q))
    if sector:
        qs = qs.filter(sector=sector)

    rows = [{
        "symbol": c.symbol,
        "name": c.name_ar or c.name_en or c.symbol,
        "sector": c.sector,
        "sub_market": c.sub_market,
        "price": c.price,
        "change_pct": c.change_pct,
        "volume": c.volume,
        "quote_value": c.quote_value,
        "pe": c.pe,
        "eps": c.eps,
        "week52_high": c.week52_high,
        "week52_low": c.week52_low,
        "candles": c.candles,
        "last_candle": c.last_candle.isoformat() if c.last_candle else None,
    } for c in qs[:2000]]

    total = Company.objects.filter(market=market).count()
    with_hist = Company.objects.filter(market=market,
                                       candles__gt=0).count()
    sectors = sorted({c["sector"] for c in rows if c["sector"]})
    return JsonResponse({
        "ok": True, "market": market, "rows": rows,
        "total": total, "with_history": with_hist,
        "without_history": total - with_hist,
        "sectors": sectors,
    })


# ═══════════════════════════ تحليل القطاعات ══════════════════════════

# ═══ لماذا حدُّ تغطية ═══
#
# حين طُلب تحليل القطاعات كان ٢٩٨ من ٣٢٦ شركة **بلا قطاع** — أي أنّ
# أي رسم بياني كان سيصف ٨٫٥٪ من السوق ويبدو كأنّه يصفه كلّه.
#
# وهذا أخطر من الامتناع: قارئ الرسم لا يرى ما ليس فيه. يرى «المواد
# الأساسية ١٠ شركات» فيظنّها القطاع كلّه، وهي عشرٌ من خمسين.
#
# فالتغطية تُعرَض دائماً، وتحت ``MIN_COVERAGE`` يُعلَن الحكم غير
# قابل للقراءة صراحةً — لا يُخفى الرقم، بل يُقال إنّه لا يُقرأ بعد.
MIN_COVERAGE_PCT = 60.0

# قطاعٌ بشركةٍ أو شركتين ليس قطاعاً بل حالتين. الوسيط عليهما لا يعني
# شيئاً، وترتيب القطاعات به يجعل الأصغر دائماً في الطرفين.
MIN_SECTOR_N = 3


def _median(xs: list[float]) -> float | None:
    vals = sorted(v for v in xs if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


@require_GET
def api_companies_sectors(request):
    """تجميع القطاعات — مع إعلان ما لا يُعرَف."""
    market = (request.GET.get("market") or "saudi").strip().lower()
    sub = (request.GET.get("sub_market") or "").strip().upper()

    qs = Company.objects.filter(market=market)
    if sub:
        qs = qs.filter(sub_market=sub)

    rows = list(qs.values("symbol", "sector", "sub_market", "price",
                          "change_pct", "quote_value", "pe", "candles"))
    total = len(rows)
    if not total:
        return JsonResponse({"ok": True, "market": market, "total": 0,
                             "sectors": [], "coverage": {},
                             "readable": False,
                             "note": "لا شركات — اجلب الشركات أوّلاً"})

    with_sector = [r for r in rows if (r["sector"] or "").strip()]
    cov_sector = 100.0 * len(with_sector) / total
    cov_price = 100.0 * sum(1 for r in rows if r["price"]) / total
    cov_hist = 100.0 * sum(1 for r in rows if (r["candles"] or 0) > 0) / total

    buckets: dict[str, list[dict]] = {}
    for r in with_sector:
        buckets.setdefault(r["sector"].strip(), []).append(r)

    sectors = []
    for name, items in buckets.items():
        chg = [r["change_pct"] for r in items if r["change_pct"] is not None]
        pes = [r["pe"] for r in items if r["pe"]]
        vals = [r["quote_value"] for r in items if r["quote_value"]]
        n_hist = sum(1 for r in items if (r["candles"] or 0) > 0)
        up = sum(1 for v in chg if v > 0)
        sectors.append({
            "sector": name,
            "count": len(items),
            # الفروع تُحصى: قطاعٌ نصفه نمو ونصفه تاسي ليس قطاعاً واحداً
            "nomu": sum(1 for r in items if r["sub_market"] == "NOMU"),
            "with_price": len(chg),
            "with_history": n_hist,
            "median_change": _median(chg),
            "advancers": up,
            "decliners": len(chg) - up,
            "median_pe": _median(pes),
            "total_value": round(sum(vals), 2) if vals else None,
            # عيّنةٌ دون الحدّ تُعرَض ولا يُحكَم بها
            "thin": len(items) < MIN_SECTOR_N,
        })

    # الترتيب بالعدد لا بالأداء: الترتيب بالأداء على تغطية ناقصة
    # يضع في القمّة أصغر القطاعات عيّنةً — وهو ترتيبٌ للضجيج.
    sectors.sort(key=lambda s: (-s["count"], s["sector"]))

    readable = cov_sector >= MIN_COVERAGE_PCT
    if readable:
        note = f"التغطية {cov_sector:.0f}٪ — قابل للقراءة"
    else:
        note = (f"التغطية {cov_sector:.0f}٪ فقط "
                f"({len(with_sector)} من {total}). "
                "الأرقام أدناه تصف هذه الشريحة لا السوق — "
                "أكمل «جلب الشركات ومعلوماتها» حتى تتجاوز "
                f"{MIN_COVERAGE_PCT:.0f}٪.")

    return JsonResponse({
        "ok": True, "market": market, "total": total,
        "sectors": sectors,
        "unclassified": total - len(with_sector),
        "coverage": {
            "sector": round(cov_sector, 1),
            "price": round(cov_price, 1),
            "history": round(cov_hist, 1),
        },
        "min_coverage": MIN_COVERAGE_PCT,
        "min_sector_n": MIN_SECTOR_N,
        "readable": readable,
        "note": note,
    })
