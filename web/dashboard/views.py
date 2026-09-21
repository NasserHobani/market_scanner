"""عروض اللوحة + واجهة JSON للتحديث الحي."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from django.db.models import Max
from django.http import Http404, HttpResponse
from . import blocklist
from .jsonsafe import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from scanner.adapters import get_adapter
from scanner.live import TIMEFRAME_LABELS, TIMEFRAME_SECONDS, UI_TIMEFRAMES, next_close

from scanner import liquidity
from scanner import search as symbol_search
from scanner import settings_schema
from scanner import tracking

from . import appsettings
from . import scheduler
from . import trades as trade_svc
from .models import ScanResult, ScanRun, SignalAlert, Trade, Watch

# سجلٌّ للوحدة: العطب العرضي (مؤشّر لا يُحسب مثلاً) يُكتب ولا
# يُسقط الصفحة — وبلا سجلٍّ يختفي بلا أثر.
log = logging.getLogger("dashboard.views")

MARKETS = ["crypto", "us", "saudi", "gold"]

# ═══ أسماء الأسواق بالعربية ═══
#
# المفاتيح إنجليزية لأنّها تُخزَّن وتُمرَّر في العناوين. وعرضُها
# كما هي يضع «crypto» و«saudi» في قائمةٍ عنوانها «نوع السوق» وسط
# واجهةٍ عربية — فيُقرأ الاختيار على أنّه اسم تقنيّ لا معنى له.
#
# والخريطة هنا لا في القالب: ثلاثة قوالب تعرض الأسواق، ونسخةٌ في
# كلٍّ منها تعني أنّ إضافة سوقٍ رابع تحتاج ثلاثة تعديلات — ويُنسى
# أحدها فيظهر المفتاح الخام في مكانٍ واحد.
MARKET_LABELS = {"crypto": "العملات", "us": "الأمريكي", "saudi": "السعودي",
                 "gold": "الذهب"}


def market_options() -> list[dict]:
    """خيارات السوق للقوائم المنسدلة — بمفتاحها واسمها."""
    return [{"key": m, "label": MARKET_LABELS.get(m, m)} for m in MARKETS]

# الأسواق التي لها بثّ WebSocket مباشر في المتصفح
STREAMING_MARKETS = {"crypto"}

# ذاكرة مؤقتة للأسعار: Yahoo تحدّ الطلبات، وعشرة متصفحين مفتوحين
# سيقصفونها بلا هذا الحاجز
_QUOTE_CACHE: dict[str, tuple[float, dict]] = {}
_QUOTE_LOCKS: dict[str, "threading.Lock"] = {}

# كانت 20.0 — أي مساوية تماماً لفترة استعلام الواجهة (QUOTE_MS).
#
# والتساوي يعني أن الذاكرة تنتهي في اللحظة التي يصل فيها الاستعلام
# التالي، فلا تُصيب أبداً: كل استعلام نداء شبكة كامل. رفعُها فوق فترة
# الاستعلام يجعلها تخدم ما وُجدت له — التبويبات واللوحات المتزامنة —
# دون أن يزيد تقادم السعر عمّا كان (السعر أصلاً مؤجَّل).
QUOTE_TTL = 26.0


def _latest_run(market: str, timeframe: str | None = None) -> ScanRun | None:
    """آخر مسح كامل — التحليلات المفردة مستبعدة عمداً."""
    qs = ScanRun.objects.filter(market=market, kind="scan")
    if timeframe:
        hit = qs.filter(timeframe=timeframe).first()
        if hit:
            return hit
    return qs.first()


def _run_age(run: ScanRun) -> dict:
    """عمر الدورة وهل هو مقلق — بزمن السوق لا بساعة الحائط.

    القياس بزمن السوق المفتوح لأن دورةً من إغلاق الجمعة ليست قديمة
    يوم السبت. وحدّ الإنذار جلستان: أطول من ذلك يعني أن المسح
    التلقائي لا يشمل هذا السوق أصلاً — وهو ما وقع.
    """
    import pandas as pd

    from scanner import sessions

    started = run.started_at
    now = pd.Timestamp.now("UTC")
    try:
        wall = (now - pd.Timestamp(started)).total_seconds()
        sess = sessions.session_seconds(run.market)
        if sess:
            open_s = sessions.open_seconds_between(started, now, run.market)
            sessions_old = open_s / sess
        else:
            sessions_old = wall / 86400.0          # سوق لا يغلق: باليوم
    except Exception:  # noqa: BLE001
        wall, sessions_old = 0.0, 0.0

    return {
        "age_seconds": round(max(0.0, wall), 1),
        "age_sessions": round(max(0.0, sessions_old), 2),
        "run_stale": sessions_old > 2.0,
        "market_open": sessions.is_open(run.market),
    }


def _market_has_run(market: str, timeframe: str) -> bool:
    return ScanRun.objects.filter(
        market=market, kind="scan", timeframe=timeframe,
    ).exists()


def _scan_frames(market: str) -> list[str]:
    """الفريمات المُهيّأة للمسح — الإعداد أوّلاً ثمّ ملفّ السوق.

    مصدرٌ واحد لهذه القائمة: كانت تُقرأ من ``cfg.timeframes`` في
    موضعين، فصار الإعداد الجديد يُطبَّق على المسح ولا تعرفه رسالة
    التنويه — فتقول «أضفه إلى ‎config/crypto.yaml‎» وهو مُضافٌ
    فعلاً من الشاشة.
    """
    from scanner import tf_prefs

    out = tf_prefs.scan_for(market)
    if out:
        return out
    try:
        from django.conf import settings as dj

        from scanner.config import load_market

        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        return list(cfg.timeframes or [])
    except Exception:  # noqa: BLE001
        return []


def _default_scanner_timeframe(market: str, requested: str | None = None) -> str:
    """فريم افتراضي مناسب لكل سوق — لا نفترض 4h للجميع."""
    if requested and _market_has_run(market, requested):
        return requested
    run = _latest_run(market)
    if run:
        return run.timeframe
    frames = _scan_frames(market)
    return frames[0] if frames else "4h"


def _timeframe_notice(market: str, requested: str | None,
                      served: str) -> dict:
    """يشرح لماذا لم يُعرَض الفريم المطلوب — إن لم يُعرَض.

    ═══ الاستبدال الصامت أسوأ من الفراغ ═══

    ‏``_default_scanner_timeframe`` يستبدل المطلوبَ بأحدث ما مُسح
    فعلاً. فمن اختار «4 ساعات» للسوق الأمريكي كان يرى بيانات
    **يومية** بلا كلمة — اختيارٌ يُلغى بصمت، فيبدو الزرّ معطوباً
    وهو يعمل كما بُرمج.

    وهذا ما بلّغ عنه المستخدم بـ «الفريم 4 ساعات لا يعمل».

    فالسبب يُقال هنا: هل الفريم غير مُهيّأ للمسح في هذا السوق أصلاً،
    أم مُهيّأ ولم يُمسح بعد؟ والفرق يغيّر ما يفعله القارئ.
    """
    if not requested or requested == served:
        return {}

    configured = _scan_frames(market)

    if configured and requested not in configured:
        # ═══ والعلاج من الشاشة لا من الملفّ ═══
        #
        # كانت الرسالة تحيل إلى ‎config/<سوق>.yaml‎ — ملفٍّ داخل
        # الصورة لا يبلغه المستخدم إلّا بإعادة نشر. وصار الفريم
        # يُفعَّل من الإعدادات، فالرسالة تدلّ على ما يمكن فعله.
        why = (f"هذا السوق مُهيّأ للمسح على {' و'.join(configured)} فقط. "
               f"لتشغيل {requested} أضفه في الإعدادات ← «فريمات المسح "
               f"لكل سوق»: {market}={requested}, "
               f"{','.join(configured)} — ثمّ شغّل مهمّة المسح. "
               f"(الشموع ستُزامَن تلقائياً.)")
    else:
        why = (f"الفريم {requested} مُهيّأ لكنّه لم يُمسح بعد في هذا "
               "السوق. شغّل المسح عليه أو انتظر الدورة القادمة.")

    return {"requested": requested, "served": served,
            "substituted": True, "configured": configured, "why": why}


def _countdown(timeframe: str) -> dict:
    """ثوانٍ متبقية حتى إغلاق الشمعة — الواجهة تعرض عدّاً تنازلياً منها."""
    if timeframe not in TIMEFRAME_SECONDS:
        return {"seconds": None, "timeframe": timeframe}
    return {
        "seconds": int(max(0, next_close(timeframe) - time.time())),
        "period": TIMEFRAME_SECONDS[timeframe],
        "timeframe": timeframe,
    }


PAGE_SIZES = (50, 100, 250)
DEFAULT_PAGE_SIZE = 100


def _paginate(queryset, request):
    """صفحة واحدة من الاستعلام — بحدّ أعلى لا يُتجاوز.

    كان الجدول يعرض 400 صفّاً × 15 عموداً = ستّة آلاف خلية في طلب
    واحد، والصفحة تُحدَّث كل عشرين ثانية. الكلفة في بناء الـ DOM
    وإعادة حساب التخطيط، لا في الاستعلام.

    والحدّ الأعلى مقصود: ``?size=100000`` من شريط العنوان كان سيعيد
    المشكلة كاملةً. المستخدم يختار من قائمة، والخادم لا يثق بالقائمة.
    """
    from django.core.paginator import Paginator

    try:
        size = int(request.GET.get("size") or DEFAULT_PAGE_SIZE)
    except (TypeError, ValueError):
        size = DEFAULT_PAGE_SIZE
    if size not in PAGE_SIZES:
        size = DEFAULT_PAGE_SIZE

    paginator = Paginator(queryset, size)
    try:
        number = int(request.GET.get("page") or 1)
    except (TypeError, ValueError):
        number = 1
    # صفحة خارج المدى تُقصّ بدل أن ترفع 404: تغيير الفلتر والمستخدم
    # في الصفحة السابعة حالة عادية لا خطأ
    return paginator.get_page(min(max(1, number), paginator.num_pages))


_NOTICE_CACHE: dict = {}
_NOTICE_TTL = 300.0


def _data_notice(market: str) -> dict | None:
    """تحذير جودة البيانات — يُقرأ من الذاكرة، **بلا أي نداء شبكة**.

    السبب أن تغذية IEX تعطي ~2.5٪ من حجم السوق، وكل مؤشرات الحجم في
    النظام تُحسب منها. رقم مبنيّ على عيّنة جزئية يبدو كرقم كامل تماماً،
    فالمكان الوحيد المفيد للتحذير هو الصفحة التي يُقرأ فيها.

    ولا شبكة هنا. كانت هذه الدالة تجسّ Alpaca عند كل فتح للّوحة، فمع
    مفاتيح خاطئة انتظرت الصفحة ثلاث محاولات × 25 ثانية — تعليق يقارب
    الدقيقة والنصف ثم صفحة بلا بيانات. عرضٌ ينتظر الشبكة عطبٌ مهما
    كان ما ينتظره مفيداً؛ الجسّ يجري في المسح والعرض يقرأ نتيجته.
    """
    import time as _t

    hit = _NOTICE_CACHE.get(market)
    if hit and (_t.time() - hit[0]) < _NOTICE_TTL:
        return hit[1]

    notice = None
    try:
        from django.conf import settings as dj

        from scanner.adapters import get_adapter
        from scanner.config import load_market

        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        adapter = get_adapter(cfg.adapter)
        if hasattr(adapter, "feed_notice"):
            info = adapter.feed_notice(probe=False)   # لا شبكة
            if info.get("partial"):
                notice = {"level": "warn", "text": info["text"]}
    except Exception:  # noqa: BLE001
        # تحذير تعذّر بناؤه يجب ألّا يمنع عرض اللوحة
        notice = None

    _NOTICE_CACHE[market] = (_t.time(), notice)
    return notice


def _setup_hint(market: str) -> str:
    """ما ينقص هذا السوق ليعمل — فحص محلّي فوري بلا شبكة.

    «لا نتائج» أمام مستخدم ضبط مفاتيحه للتوّ رسالة عديمة النفع: تصف
    ما يراه لا ما يفعله. وهذا الفحص يقرأ متغيّرات البيئة وملف
    الإعدادات فقط — لا طلب واحد — فلا يعيد إدخال التعليق الذي أصلحناه.
    """
    try:
        from django.conf import settings as dj

        from scanner.config import load_market

        cfg = load_market(dj.SCANNER_CONFIG_DIR / f"{market}.yaml")
        if cfg.adapter == "alpaca":
            from scanner.adapters.alpaca import credentials

            key, secret = credentials()
            if not key or not secret:
                # ═══ الإرشاد يتبع مكان التشغيل ═══
                #
                # «أضف إلى ملفّ ‎.env‎ في جذر المشروع» نصيحةٌ خاطئة
                # داخل حاوية: الملفّ في طبقة الصورة، يمحوه كل
                # ``Pull and redeploy``. فمن اتّبعها ضبط المفاتيح
                # ثمّ فقدها عند أوّل تحديث، ولا شيء يقول لماذا.
                if Path("/.dockerenv").exists():
                    return ("مفاتيح Alpaca غير مضبوطة. أضفها في "
                            "بورتينر ← Stacks ← market-scanner ← "
                            "Environment variables: ALPACA_API_KEY و "
                            "ALPACA_SECRET_KEY، وللحساب الورقي (مفتاح "
                            "يبدأ بـ PK) أضف ALPACA_PAPER=1، ثم "
                            "Update the stack. ولا تضعها في ملفّ ‎.env‎ "
                            "داخل الحاوية — يُمحى مع كل نشر.")
                return ("مفاتيح Alpaca غير مضبوطة. أضف إلى ملف "
                        ".env في جذر المشروع: ALPACA_API_KEY_ID و "
                        "ALPACA_API_SECRET_KEY، وللحساب الورقي "
                        "(مفتاح يبدأ بـ PK) أضف ALPACA_PAPER=1، ثم "
                        "أعد تشغيل الخادم.")
            if not key.upper().startswith(("PK", "AK")):
                return ("مفتاح Alpaca لا يبدأ بـ PK ولا AK — تأكّد أنه "
                        "مفتاح تداول لا مفتاح Broker.")
    except Exception:  # noqa: BLE001
        return ""
    return ""


def dashboard(request):
    """لوحة التشغيل — هل يمكنني الوثوق بالنظام الآن؟"""
    market = request.GET.get("market", "crypto")
    if market not in MARKETS:
        market = "crypto"
    return render(request, "dashboard/dashboard.html", {
        "nav_page": "dashboard",
        "markets": MARKETS,
        "market": market,
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": "4h",
        "show_market_chips": False,
        # ‏لوحة التشغيل ليست موجَّهة بفريم واحد، فرقائق الفريم في الترويسة
        # توحي بمرشّح لا وجود له.
        "tf_in_page": True,
        "payload": {"countdown": None, "market": market, "query": ""},
    })


def scanner(request):
    market = request.GET.get("market", "crypto")
    # ═══ يُتحقَّق منه قبل أن يدخل نصّاً معروضاً ═══
    #
    # الفريم المطلوب يدخل رسالة التنويه، والرسالة تُعرض في الصفحة.
    # فنصٌّ عشوائي من شريط العنوان كان سيصل الـDOM. والحصر في
    # ‏``UI_TIMEFRAMES`` يقطع ذلك من المصدر — أوثق من الهروب عند
    # العرض، لأنّه لا يعتمد على أن يتذكّره كل مُستهلِك.
    requested_tf = request.GET.get("tf") or None
    if requested_tf and requested_tf not in UI_TIMEFRAMES:
        requested_tf = None
    timeframe = _default_scanner_timeframe(market, requested_tf)
    # Shell renders immediately — stat cards load via widget API
    pairs = (ScanRun.objects.filter(kind="scan")
             .values_list("market", "timeframe").distinct())
    populated = [{"market": m, "timeframe": t} for m, t in pairs]
    current_tf = timeframe
    has_run = _market_has_run(market, current_tf)

    return render(request, "dashboard/scanner.html", {
        "nav_page": "scanner",
        "show_market_chips": True,
        "market": market,
        "markets": MARKETS,
        "scope": _search_scope(request), "scopes": symbol_search.SCOPES,
        "populated": populated,
        "has_any": bool(populated),
        "has_run": has_run,
        "data_notice": _data_notice(market),
        "setup_hint": _setup_hint(market),
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": current_tf,
        "tf_label": TIMEFRAME_LABELS.get(current_tf, current_tf),
        "payload": {
            "market": market,
            "countdown": _countdown(current_tf).get("seconds"),
            "timeframe": current_tf,
        },
        "countdown": _countdown(current_tf),
        "alerts": SignalAlert.objects.filter(result__market=market)[:10],
    })


def symbol_detail(request, market: str, symbol: str):
    latest = (ScanResult.objects.filter(market=market, symbol=symbol)
              .order_by("-candle_time").first())

    # الرمز الذي وصل من البحث لم يمرّ بدورة مسح، فلا صف له في القاعدة.
    # نحلّله فوراً ونحفظه بدل رفض الصفحة — وهكذا يتراكم تاريخه أيضاً.
    if latest is None:
        try:
            analysis = _analyze_on_demand(symbol, market, persist=True)
            latest = (ScanResult.objects.filter(market=market, symbol=symbol)
                      .order_by("-candle_time").first())
        except Exception as exc:  # noqa: BLE001
            raise Http404(f"تعذّر تحليل {symbol}: {str(exc)[:200]}") from exc

    if latest is None:
        raise Http404(f"تعذّر حفظ نتيجة {symbol}")
    # الفريم المطلوب من العنوان يقود الصفحة كلها: الأزرار المضيئة والصف
    # المعروض والشارت. بدونه يضيء زر فريم بينما تُحمَّل بيانات فريم آخر.
    tf = request.GET.get("tf")
    if tf not in UI_TIMEFRAMES:
        tf = latest.timeframe
    on_tf = (ScanResult.objects.filter(market=market, symbol=symbol, timeframe=tf)
             .order_by("-candle_time").first())
    if on_tf is not None:
        latest = on_tf

    history = list(
        ScanResult.objects.filter(market=market, symbol=symbol,
                                  timeframe=latest.timeframe)
        .order_by("-candle_time")[:200]
    )[::-1]
    return render(request, "dashboard/symbol.html", {
        "market": market,
        "symbol": symbol,
        "latest": latest,
        "history": history,
        # القالب يقرأ من سياق العرض، لا من payload المخصّص لـ JavaScript
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]}
                       for t in UI_TIMEFRAMES],
        "timeframe": latest.timeframe,
        # للصفحة مبدّل فريم خاص بها داخل بطاقة الشارت يبدّل بلا إعادة تحميل،
        # فمبدّل الشريط العلوي تكرار له يربك أكثر مما يفيد
        "tf_in_page": True,
        # كل ما يحتاجه JavaScript يمرّ عبر json_script — لا استيفاء مباشر
        "payload": {
            "market": market,
            "symbol": symbol,
            "close": latest.close,
            "tvSymbol": _tv_symbol(symbol),
            "tvInterval": _tv_interval(latest.timeframe),
            "historyUrl": f"/api/history/{market}/{symbol}/",
            "chartApi": f"/api/chart/{market}/{symbol}/",
            "outlookApi": f"/api/outlook/{market}/{symbol}/",
            "timeframe": latest.timeframe,
            "chartUrl": latest.chart_url,
            "countdown": _countdown(latest.timeframe).get("seconds"),
            "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]}
                           for t in UI_TIMEFRAMES],
        },
    })


# ------------------------------------------------------------------ JSON

def api_results(request):
    """يستهلكها JS للتحديث بلا إعادة تحميل."""
    market = request.GET.get("market", "crypto")
    # ═══ يُتحقَّق منه قبل أن يدخل نصّاً معروضاً ═══
    #
    # الفريم المطلوب يدخل رسالة التنويه، والرسالة تُعرض في الصفحة.
    # فنصٌّ عشوائي من شريط العنوان كان سيصل الـDOM. والحصر في
    # ‏``UI_TIMEFRAMES`` يقطع ذلك من المصدر — أوثق من الهروب عند
    # العرض، لأنّه لا يعتمد على أن يتذكّره كل مُستهلِك.
    requested_tf = request.GET.get("tf") or None
    if requested_tf and requested_tf not in UI_TIMEFRAMES:
        requested_tf = None
    timeframe = _default_scanner_timeframe(market, requested_tf)
    notice = _timeframe_notice(market, requested_tf, timeframe)
    run = _latest_run(market, timeframe)
    if run is None:
        # ═══ الفراغ يُعلَّل ═══
        #
        # جدولٌ فارغ بلا كلمة يُقرأ «النظام معطوب». والسبب هنا
        # معروف: لا جولة مسحٍ لهذا السوق على هذا الفريم.
        return JsonResponse({
            "run": None, "results": [],
            "countdown": _countdown(timeframe),
            "timeframe": timeframe,
            "requested_timeframe": requested_tf or timeframe,
            "notice": notice or {
                "requested": requested_tf or timeframe,
                "served": timeframe, "substituted": False,
                "why": f"لا جولة مسحٍ لـ {market} على {timeframe} بعد.",
            },
        })

    rows = [
        {
            "symbol": r.symbol, "close": r.close, "score": round(r.score, 1),
            "decision": r.decision, "confluence": r.confluence, "reasons": r.reasons,
            "htf": r.htf, "htf_text": r.htf_text, "ready": r.ready,
            "blocker": r.blocker, "rsi": r.rsi, "rvol": r.rvol,
            "atr_pct": r.atr_pct, "chart_url": r.chart_url,
            "action": r.action, "headline": r.headline, "entry": r.entry,
            "stop": r.stop, "target1": r.target1, "rr": r.rr,
            "trigger": r.trigger, "grade": r.grade,
            "compliance": r.compliance, "compliance_reason": r.compliance_reason,
            "chart_pattern": r.chart_pattern,
            "candle_patterns": r.candle_patterns, "elliott": r.elliott,
            "confidence": r.confidence,
            "liquidity": r.liquidity,
            "liquidity_label": liquidity.label(r.liquidity),
            "quote_volume": r.quote_volume,
            "volume_text": liquidity.human(r.quote_volume),
            "thin": liquidity.is_thin(r.liquidity),
            "url": f"/symbol/{market}/{r.symbol}/",
        }
        # ═══ المحظور لا يُعرض ولو كان مخزّناً ═══
        #
        # الحرس عند المسح يمنع القادم، وهذه الصفوف مُسحت قبل
        # الحظر. وبقاؤها ظاهرةً يجعل الحظر يبدو معطّلاً.
        for r in blocklist.drop_blocked(list(run.results.all()),
                                        market=market)
    ]
    return JsonResponse({
        "run": {
            "id": run.id,
            "started_at": run.started_at.isoformat(),
            "timeframe": run.timeframe,
            "scanned": run.symbols_scanned,
            "failed": run.symbols_failed,
            "ready": run.ready_count,
            "duration": run.duration_seconds,
            # مصدر الرموز يصل الواجهة: مسحٌ على عشرة أسهم بينما الإعداد
            # يَعِد بسبعمئة يجب أن يُرى، لا أن يُستنتج من قلّة الصفوف
            "universe_source": run.universe_source or "",
            "universe_note": run.universe_note or "",
            "universe_degraded": run.universe_source in
            ("fallback", "auto_thin", "cached"),
            # ═══ عمر الدورة يُعرَض ═══
            #
            # اللوحة كانت تعرض آخر دورة بلا ذكر متى جرت. وكان
            # ``AUTO_SCAN_MARKETS=crypto`` يعني أن السوق الأمريكي لا
            # يُمسَح أصلاً — فظلّت اللوحة تعرض دورةً عمرها أسابيع
            # وكأنّها نتيجة اليوم: عشرة أسهم، بلا خطأ ولا صفر نتائج،
            # فتبدو سليمة تماماً.
            #
            # لا يكفي أن نعرض الرقم: يجب أن نقول متى صار.
            **_run_age(run),
        },
        "results": rows,
        "countdown": _countdown(run.timeframe),
        "timeframe": run.timeframe,
        "requested_timeframe": requested_tf or run.timeframe,
        # المعروض قد لا يكون المطلوب — ويُقال ذلك بدل أن يُخمَّن
        "notice": notice,
    })


def api_history(request, market: str, symbol: str):
    """تاريخ الدرجة لرسمه بـ Chart.js."""
    qs = ScanResult.objects.filter(market=market, symbol=symbol)
    tf = request.GET.get("tf")
    if tf:
        qs = qs.filter(timeframe=tf)
    qs = qs.order_by("-candle_time")[:200]
    rows = list(qs)[::-1]
    return JsonResponse({
        "symbol": symbol,
        "labels": [r.candle_time.strftime("%m-%d %H:%M") for r in rows],
        "score": [round(r.score, 1) for r in rows],
        "close": [r.close for r in rows],
        "confluence": [r.confluence for r in rows],
        "ready": [r.ready for r in rows],
    })


SCOPE_COOKIE = "search_scope"


def _search_scope(request) -> str:
    """النطاق المطلوب: من العنوان، وإلا آخر اختيار محفوظ، وإلا الكل."""
    return symbol_search.normalize_scope(
        request.GET.get("m"),
        fallback=symbol_search.normalize_scope(request.COOKIES.get(SCOPE_COOKIE)),
    )


def search(request):
    """بحث بالاسم أو الرمز، ثم تحليل فوري للنتيجة المختارة."""
    query = (request.GET.get("q") or "").strip()
    picked = (request.GET.get("symbol") or "").strip()
    market = (request.GET.get("market") or "").strip()
    timeframe = (request.GET.get("tf") or "").strip() or None
    scope = _search_scope(request)

    results, analysis, error = [], None, ""
    elapsed = None

    if picked and market:
        try:
            analysis = _analyze_on_demand(picked, market, persist=True,
                                          timeframe=timeframe)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:300]
    elif query:
        found = symbol_search.run(query, scope, get_adapter)
        results, elapsed = found["results"], found["elapsed"]
        # فشل مصدر لا يعني «لا نتائج» — نعرضه فقط حين لا نتيجة أصلاً
        if found["failures"] and not results:
            error = " · ".join(found["failures"])

    response = render(request, "dashboard/search.html", {
        "nav_page": "search",
        "markets": MARKETS, "market": market or "crypto",
        "query": query, "results": results,
        "analysis": analysis, "error": error,
        "scope": scope, "scopes": symbol_search.SCOPES, "elapsed": elapsed,
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": timeframe or (analysis["timeframe"] if analysis else "4h"),
        "payload": {"countdown": None},
        "tvdata": {"symbol": analysis["tv_symbol"], "interval": analysis["tv_interval"]}
        if analysis else {},
    })
    # الاختيار يبقى للزيارة القادمة — هذا معنى «تحديد مسبق»
    response.set_cookie(SCOPE_COOKIE, scope, max_age=60 * 60 * 24 * 365,
                        samesite="Lax")
    return response


def _analyze_on_demand(symbol: str, market: str, persist: bool = False,
                       timeframe: str | None = None) -> dict:
    """يجلب البيانات ويحلّلها فوراً — بلا انتظار دورة المسح."""
    from django.conf import settings

    from scanner import storage
    from scanner.config import load_market
    from scanner.scoring import score_with_recommendation

    cfg_path = settings.SCANNER_CONFIG_DIR / f"{market}.yaml"
    if not cfg_path.exists():
        raise ValueError(f"لا توجد إعدادات لسوق {market}")

    cfg = load_market(cfg_path)
    timeframe = timeframe or cfg.timeframes[0]
    if timeframe not in UI_TIMEFRAMES:
        raise ValueError(f"فريم غير مدعوم: {timeframe}")
    adapter = get_adapter(cfg.adapter)

    cached = storage.load(cfg.name, symbol, timeframe)
    fresh = adapter.fetch(symbol, timeframe, cfg.candles)
    df = storage.merge(cached, fresh)
    storage.save(cfg.name, symbol, timeframe, df)

    if len(df) < 60:
        raise ValueError(f"بيانات غير كافية ({len(df)} شمعة)")

    result = score_with_recommendation(df, symbol, timeframe, cfg)

    if persist:
        _persist_result(cfg, timeframe, result, adapter.name)

    return {
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "close": result.close, "score": round(result.score, 1),
        "decision": result.decision, "htf": result.htf,
        "htf_text": result.context.get("htf_text", ""),
        "confluence": result.confluence, "ready": result.ready,
        "blocker": result.blocker, "candles": len(df),
        "rsi": result.context.get("rsi"), "rvol": result.context.get("rvol"),
        "atr_pct": result.context.get("atr_pct"),
        "reco": result.recommendation,
        "tv_symbol": _tv_symbol(symbol),
        "tv_interval": _tv_interval(timeframe),
    }


def _gated_scan(market: str, timeframe: str | None) -> None:
    """بوّابة الحداثة ثمّ المسح — كلاهما في الخيط الخلفي.

    ترتيبهما محفوظ كما كان: لا يبدأ المسح على بيانات متأخّرة. والفرق
    أن الانتظار صار في خيط لا في طلب، فلا يحجب الواجهة.
    """
    from .concurrency import track

    with track(f"مسح {market} {timeframe or ''}".strip(), kind="scan"):
        try:
            from scanner.market_sync import get_service

            with track(f"بوّابة الحداثة {market}", kind="freshness"):
                gate = get_service().scan_freshness_gate(
                    market, timeframe or "4h", auto_refresh=True,
                )
            if not gate.get("ok"):
                scheduler.note_blocked(
                    market, gate.get("reason", "بيانات السوق متأخرة"),
                    code=gate.get("code", "MARKET_DATA_STALE"))
                return
        except Exception:  # noqa: BLE001
            # تعذّر الفحص لا يمنع المسح: البيانات قد تكون سليمة والعطب
            # في الفاحص. والمسح نفسه يتحقّق من قِدَم الشموع.
            pass
        scheduler.run_scan(market, timeframe, force=False, cached=True)


@require_POST
def api_scan_now(request):
    """تشغيل مسح فوري في الخلفية — يستهلك بيانات مزامَنة (لا مزامنة تاريخية)."""
    market = request.POST.get("market", "crypto")
    timeframe = request.POST.get("timeframe") or None
    if market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "سوق غير معروف"}, status=400)
    if timeframe and timeframe not in UI_TIMEFRAMES:
        return JsonResponse({"ok": False, "reason": "فريم غير مدعوم"}, status=400)
    if scheduler.is_running():
        return JsonResponse({"ok": False, "reason": "دورة جارية بالفعل"})

    # بوّابة الحداثة تُفحَص **داخل الخيط** لا هنا.
    #
    # ═══ لماذا نُقلت ═══
    #
    # ``scan_freshness_gate(auto_refresh=True)`` يحلّ قائمة الرموز —
    # وقد ينادي الشبكة لاكتشافها — ثمّ يقرأ ملفّاً لكل رمز من مئات.
    # وتنفيذه داخل الطلب يعني خيط خادم مشغولاً دقائق، والمتصفّح يحدّ
    # اتصالاته بستّة، فتتجمّد الواجهة كلّها بسبب ضغطة زرّ واحدة.
    #
    # والنتيجة تصل عبر ``/api/scan/status/`` كما تصل بقيّة أخبار المسح،
    # فلا يضيع التحقّق — يتغيّر موضعه فقط.

    threading.Thread(
        target=_gated_scan,
        args=(market, timeframe),
        name=f"manual-scan-{market}",
        daemon=True,
    ).start()
    return JsonResponse({"ok": True, "market": market, "mode": "cached_scan"})


def api_scan_status(request):
    st = scheduler.status()
    return JsonResponse({
        "running": st["running"], "market": st["market"],
        "elapsed": round(time.time() - st["started_at"], 1)
        if st["running"] and st["started_at"] else None,
        "last_error": st["last_error"],
        "last_result": st["last_result"],
        "auto": st["thread_started"],
    })


def _persist_result(cfg, timeframe: str, result, adapter_name: str) -> None:
    """حفظ نتيجة تحليل مفرد كدورة مسح من رمز واحد."""
    from django.db import transaction

    from scanner.report import tradingview_link

    from .management.commands.scan import _as_utc, _num, _reco_fields

    row = result.to_row()
    with transaction.atomic():
        run = ScanRun.objects.create(
            market=cfg.name, timeframe=timeframe, kind="adhoc",
            duration_seconds=0.0, symbols_scanned=1, symbols_failed=0,
            ready_count=1 if result.ready else 0,
        )
        ScanResult.objects.update_or_create(
            symbol=result.symbol, market=cfg.name, timeframe=timeframe,
            candle_time=_as_utc(result.timestamp),
            defaults=dict(
                run=run, close=result.close, score=result.score,
                decision=result.decision, confluence=len(result.confluence),
                reasons=" · ".join(result.confluence)[:255], htf=result.htf,
                ready=result.ready, blocker=result.blocker[:64],
                rsi=_num(row.get("rsi")), rvol=_num(row.get("rvol")),
                atr_pct=_num(row.get("atr_pct")),
                chart_url=tradingview_link(adapter_name, result.symbol, timeframe),
                **_reco_fields(result.recommendation),
            ),
        )


def api_chart(request, market: str, symbol: str):
    """شموع + كل طبقات التحليل كإحداثيات جاهزة للرسم."""
    from django.conf import settings

    from scanner import storage
    from scanner.analysis.overlay import build as build_overlay
    from scanner.config import load_market
    from scanner.scoring import score_with_recommendation

    cfg_path = settings.SCANNER_CONFIG_DIR / f"{market}.yaml"
    if not cfg_path.exists():
        return JsonResponse({"error": "سوق غير معروف"}, status=404)

    cfg = load_market(cfg_path)
    timeframe = request.GET.get("tf") or cfg.timeframes[0]
    if timeframe not in UI_TIMEFRAMES:
        return JsonResponse({"error": f"فريم غير مدعوم: {timeframe}"}, status=400)

    df = storage.load(cfg.name, symbol, timeframe)
    # الفريم الذي لم يُمسح بعد لا بيانات له — bootstrap أولي مرة واحدة فقط.
    # المسار العادي يقرأ من المخزن المزامَن في الخلفية (MD-01).
    if df is None or len(df) < 60:
        try:
            from scanner.market_sync import get_service
            get_service().sync_pair(cfg.name, symbol, timeframe)
            df = storage.load(cfg.name, symbol, timeframe)
        except Exception as exc:  # noqa: BLE001
            return JsonResponse(
                {"error": f"تعذّر جلب {symbol} على فريم {timeframe}: {str(exc)[:160]}"},
                status=502)
    elif storage.bars_needed(df, timeframe, cfg.candles, margin=1) > 3:
        # تأخير بسيط: تحديث تزايدي فقط، لا إعادة التاريخ
        try:
            from scanner.market_sync import get_service
            get_service().sync_pair(cfg.name, symbol, timeframe)
            df = storage.load(cfg.name, symbol, timeframe) or df
        except Exception:  # noqa: BLE001
            pass
    if df is None or len(df) < 60:
        return JsonResponse({"error": "بيانات غير كافية لهذا الفريم"}, status=404)

    try:
        result = score_with_recommendation(df, symbol, timeframe, cfg)
        payload = build_overlay(df, cfg, reco=result.recommendation)

        # ═══ لوحتا الزخم ═══
        #
        # النافذة تُؤخذ من أوّل شمعة في المخرَج لا من ``max_bars``:
        # ‏overlay يوسّعها أحياناً لتشمل بداية الموجة، فلو خُمِّنت
        # لانزلقت اللوحتان عن الشارت بعشرات الشمعات.
        #
        # وفشلهما لا يُسقط الصفحة: الشارت والتوصية أهمّ منهما،
        # وخطأٌ في مؤشّرٍ عرضيّ يجب ألّا يخفي التحليل كلّه.
        try:
            from scanner.analysis.oscillators import build as build_osc

            _first = (payload.get("candles") or [{}])[0].get("time")
            payload["oscillators"] = build_osc(df, since_ts=_first)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر حساب لوحتي الزخم لـ %s: %s",
                        symbol, str(exc)[:160])
            payload["oscillators"] = {"ok": False,
                                      "reason": "تعذّر الحساب"}

        # ═══ خطّ Supertrend على فريم الشاشة ═══
        #
        # على الفريم المعروض لا على اليوميّ دائماً: المؤشّر على
        # الشارت يجب أن يوافق ما تحته. ومقاطعُه ملوّنة بالاتجاه،
        # في طبقةٍ مستقلّة تُطفأ بنقرة.
        #
        # وفشلُه لا يُسقط الصفحة — كبقيّة الطبقات.
        try:
            from scanner.analysis.supertrend_layer import build as build_st
            from scanner.strategies.pes import load_params as _pes_params

            _stcfg = (_pes_params().get("supertrend") or {})
            _first = (payload.get("candles") or [{}])[0].get("time")
            st_layer = build_st(
                df, since_ts=_first,
                length=int(_stcfg.get("length", 10)),
                mult=float(_stcfg.get("multiplier", 3.0)))
            payload["supertrend"] = {k: v for k, v in st_layer.items()
                                     if k != "lines"}
            for ln in st_layer.get("lines") or []:
                payload.setdefault("lines", []).append(ln)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر رسم Supertrend لـ %s: %s",
                        symbol, str(exc)[:160])
            payload["supertrend"] = {"ok": False, "reason": "تعذّر الحساب"}

        # ═══ امتداد فيبوناتشي المبني على الاتجاه ═══
        #
        # يُرسم كما يُرسم في TradingView: خطٌّ يصل النقاط الثلاث،
        # ومستوياتٌ أفقية معنونة بنسبتها — كي يقارن المستخدم بشارته
        # ويحكم على اختيار النقاط بنفسه.
        #
        # وفي طبقةٍ مستقلّة (‎fib_ext‎) تُطفأ بنقرة: ثمانية خطوط
        # إضافية على شارتٍ فيه فيبوناتشي وقناة ونماذج تصير ضجيجاً.
        try:
            from scanner.indicators import fib_extension as fx
            from scanner.strategies.pes import load_params

            fib = fx.measure(df, load_params())
            payload["fib_extension"] = fib
            if fib.get("ok"):
                pts = [("p1_at", "p1"), ("p2_at", "p2"), ("p3_at", "p3")]
                payload.setdefault("lines", []).append({
                    "layer": "fib_ext", "color": "#c792ea",
                    "width": 1, "style": "dashed",
                    "points": [{"time": int(fib[t].timestamp()),
                                "value": float(fib[v])}
                               for t, v in pts],
                })
                for x in fib["levels"]:
                    # ‏0.618 و1.0 و1.618 هي المراتب التي يُتعامل
                    # معها فعلاً؛ والباقي يُرسم أبهت كي لا يزاحمها
                    key = x["ratio"] in (0.618, 1.0, 1.618)
                    payload.setdefault("levels", []).append({
                        "layer": "fib_ext", "price": x["price"],
                        "color": "#c792ea" if key else "rgba(199,146,234,.4)",
                        "style": "dotted",
                        "title": f"امتداد {x['ratio']}",
                    })
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر رسم امتداد فيب لـ %s: %s",
                        symbol, str(exc)[:160])
            payload["fib_extension"] = {"ok": False,
                                        "why": "تعذّر الحساب"}

        # الاستجابة تحمل كل ما تعرضه الصفحة، لا الشارت وحده — تبديل الفريم
        # يجب أن يحدّث الترويسة والتوصية والجداول معاً وإلا خلط فريمين
        payload.update({
            "recommendation": result.recommendation,
            "symbol": symbol,
            "timeframe": timeframe,
            "score": round(result.score, 1),
            "decision": result.decision,
            "close": result.close,
            "htf": result.htf,
            "htf_text": result.context.get("htf_text", ""),
            "confluence": result.confluence,
            "ready": result.ready,
            "blocker": result.blocker,
            "rsi": result.context.get("rsi"),
            "rvol": result.context.get("rvol"),
            "atr_pct": result.context.get("atr_pct"),
            "candles_count": len(df),
            "countdown": _countdown(timeframe).get("seconds"),
            "history_url": f"/api/history/{market}/{symbol}/?tf={timeframe}",
            "freshness": __import__(
                "scanner.market_sync.freshness", fromlist=["assess_freshness"]
            ).assess_freshness(cfg.name, symbol, timeframe, df=df),
        })
        return JsonResponse(payload)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)[:300]}, status=500)


def api_outlook(request, market: str, symbol: str):
    """توقّع الأسبوع + السياق العام."""
    from django.conf import settings

    from scanner import storage
    from scanner.analysis.context import build as build_context
    from scanner.analysis.outlook import build as build_outlook
    from scanner.config import load_market
    from scanner.indicators.pine import atr

    cfg_path = settings.SCANNER_CONFIG_DIR / f"{market}.yaml"
    if not cfg_path.exists():
        return JsonResponse({"error": "سوق غير معروف"}, status=404)

    cfg = load_market(cfg_path)
    timeframe = request.GET.get("tf") or cfg.timeframes[0]
    days = int(request.GET.get("days") or cfg.outlook_days)

    df = storage.load(cfg.name, symbol, timeframe)
    if df is None or len(df) < 60:
        return JsonResponse({"error": "لا بيانات كافية"}, status=404)

    try:
        run = _latest_run(market)
        breadth = None
        if run:
            total = run.symbols_scanned
            ready = ScanResult.objects.filter(run=run, ready=True).count()
            if total:
                breadth = (ready, total)

        latest = (ScanResult.objects.filter(market=market, symbol=symbol)
                  .order_by("-candle_time").first())
        regime = None
        if latest:
            regime = latest.htf == 1 if latest.htf != 0 else None

        ctx = build_context(
            market, regime_bull=regime, breadth=breadth,
            df=df, atr_series=atr(df, cfg.params.atr_len),
            with_news=request.GET.get("news", "1") == "1",
            feeds=cfg.news_feeds or None,
        )
        outlook = build_outlook(df, cfg, timeframe, days=days,
                                market_context=ctx.as_dict())
        return JsonResponse({
            "symbol": symbol, "timeframe": timeframe,
            "outlook": outlook.as_dict(), "context": ctx.as_dict(),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": str(exc)[:300]}, status=500)


def watches(request):
    """الفرص المراقَبة: المسلّحة والمتحققة حديثاً."""
    from django.db.utils import OperationalError, ProgrammingError

    from . import monitor

    setup_error = ""
    armed, recent = [], []
    f = _watch_filters(request)
    try:
        # المرشّح يسري على القائمتين: «تحققت مؤخراً» جزءٌ من هذه
        # الشاشة، وترشيحُ نصفها يجعل الصفحة تناقض نفسها.
        armed = list(_apply_watch_filters(
            Watch.objects.filter(status="armed"), f))
        recent = list(_apply_watch_filters(
            Watch.objects.filter(status="triggered"), f)[:15])
    except (OperationalError, ProgrammingError):
        setup_error = "جدول المراقبة غير موجود — شغّل: python web/manage.py migrate"

    return render(request, "dashboard/watches.html", {
        "nav_page": "watches",
        "markets": MARKETS,
        "market_options": market_options(),
        "filters": f,
        "armed": armed, "recent": recent, "setup_error": setup_error,
        "monitor": monitor.status(),
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
    })


def _watch_filters(request) -> dict:
    """مرشّحات المراقبة — الرمز والفريم والتاريخ.

    ونفس دوالّ الصفقات تُستعمل هنا: «من 27 إلى 20» يُصحَّح في
    الشاشتين، و«btc» تجد ‏BTCUSDT في الشاشتين. مرشّحٌ يعني شيئاً
    هنا وشيئاً هناك أسوأ من غيابه.
    """
    tf = request.GET.get("tf") or ""
    market = request.GET.get("market") or ""
    start, end = _date_range(request)
    return {
        "symbol": _clean_symbol(request.GET.get("symbol")),
        "timeframe": tf if tf in UI_TIMEFRAMES else "",
        "market": market if market in MARKETS else "",
        "date_from": start.isoformat() if start else "",
        "date_to": end.isoformat() if end else "",
        "_start": start, "_end": end,
    }


def _apply_watch_filters(qs, f):
    if f["symbol"]:
        qs = qs.filter(symbol__icontains=f["symbol"])
    if f["timeframe"]:
        qs = qs.filter(timeframe=f["timeframe"])
    if f["market"]:
        qs = qs.filter(market=f["market"])
    # ═══ التاريخ على وقت الإنشاء ═══
    #
    # ‏``expires_at`` يجعل المرشّح يسأل «متى تنتهي» لا «متى
    # رُصدت»، و``triggered_at`` فارغ في كل مراقبة مسلّحة — فأيّ
    # مدىً عليه يفرّغ الجدول كلّه.
    return _apply_date(qs, "created_at", f["_start"], f["_end"])


def api_watches(request):
    from django.db.utils import OperationalError, ProgrammingError

    rows = []
    f = _watch_filters(request)
    try:
        armed = list(_apply_watch_filters(
            Watch.objects.filter(status="armed"), f))
    except (OperationalError, ProgrammingError):
        return JsonResponse({"watches": [], "monitor": _monitor_status(),
                             "setup_error": "شغّل: python web/manage.py migrate"})

    for w in armed:
        rows.append({
            "symbol": w.symbol, "market": w.market, "timeframe": w.timeframe,
            "side": w.side, "entry": w.entry, "stop": w.stop, "target1": w.target1,
            "rr": w.rr, "grade": w.grade, "reasons": w.reasons,
            "last_price": w.last_price, "distance_pct": w.distance_pct,
            "expires_at": w.expires_at.isoformat() if w.expires_at else None,
            "url": f"/symbol/{w.market}/{w.symbol}/",
        })
    # مراقبةٌ سُلّحت قبل الحظر تبقى في القاعدة — فتُحجب من العرض.
    # ولا تُحذف: الحظر قد يُرفع، والحذف لا رجعة فيه.
    rows = blocklist.drop_blocked(rows)
    rows.sort(key=lambda r: abs(r["distance_pct"]) if r["distance_pct"] is not None else 999)
    # ``total`` قبل الترشيح: بلا هذا العدد يُقرأ الجدول الفارغ
    # «لا مراقبات» بينما هناك أربعون وواحدةٌ لا تطابق المرشّح.
    try:
        total = Watch.objects.filter(status="armed").count()
    except (OperationalError, ProgrammingError):
        total = len(rows)
    return JsonResponse({"watches": rows, "monitor": _monitor_status(),
                         "total": total, "shown": len(rows),
                         "filtered": bool(f["symbol"] or f["timeframe"]
                                          or f["market"] or f["date_from"]
                                          or f["date_to"])})


def _monitor_status() -> dict:
    from . import monitor

    st = monitor.status()
    return {
        "running": st["running"], "checked": st["checked"],
        "triggered_total": st["triggered_total"],
        "last_error": st["last_error"],
        "seconds_ago": round(time.time() - st["last_check"]) if st["last_check"] else None,
    }


@require_POST
def api_telegram_test(request):
    """إرسال رسالة اختبار مع تشخيص السبب عند الفشل."""
    import os

    token = os.getenv("TELEGRAM_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        return JsonResponse({"ok": False,
                             "reason": "TELEGRAM_TOKEN غير مضبوط في .env"})

    if ":" not in token or not token.split(":", 1)[0].isdigit():
        return JsonResponse({
            "ok": False,
            "reason": "صيغة التوكن خاطئة — يجب أن يبدأ برقم ثم نقطتين "
                      "(8123456789:AAG…). شغّل: python web/manage.py telegram_test",
        })

    if chat_id == token.split(":", 1)[0]:
        return JsonResponse({
            "ok": False,
            "reason": "TELEGRAM_CHAT_ID هو معرّف البوت نفسه — البوت لا يراسل نفسه. "
                      "شغّل: python web/manage.py telegram_test --chat-id",
        })
    if not chat_id:
        return JsonResponse({"ok": False,
                             "reason": "TELEGRAM_CHAT_ID غير مضبوط — شغّل: "
                                       "python web/manage.py telegram_test --chat-id"})

    from scanner.outputs import telegram

    text = "\n".join([
        "✅ *اختبار ماسح الأسواق*",
        "",
        "الاتصال يعمل — هكذا ستصلك تنبيهات الفرص.",
        "",
        f"الوقت: {timezone.now():%Y-%m-%d %H:%M} UTC",
    ])
    ok = telegram.send(text, token=token, chat_id=chat_id)
    return JsonResponse({
        "ok": bool(ok),
        "reason": "" if ok else "رفض تيليجرام الإرسال — تحقّق من المعرّف "
                                "وأنك أرسلت /start للبوت",
    })


@require_POST
def api_check_now(request):
    """فحص فوري بدل انتظار الدورة."""
    from . import monitor

    result = monitor.check_once()
    return JsonResponse({"ok": True, **result})


def api_quotes(request):
    """أسعار الأسواق التي لا بثّ لها (الأسهم) — تُسحب من الخادم.

    Yahoo لا توفّر WebSocket مجانياً، والأسعار مؤجّلة بطبيعتها.
    نصرّح بذلك في الرد بدل إيهام الواجهة بأنها لحظية.
    """
    market = request.GET.get("market", "us")
    if market in STREAMING_MARKETS:
        return JsonResponse({"market": market, "streaming": True, "quotes": {}})

    cached = _QUOTE_CACHE.get(market)
    if cached and (time.time() - cached[0]) < QUOTE_TTL:
        return JsonResponse({"market": market, "streaming": False,
                             "delayed": True, "cached": True, "quotes": cached[1]})

    run = _latest_run(market)
    if run is None:
        return JsonResponse({"market": market, "streaming": False, "quotes": {}})

    symbols = list(run.results.values_list("symbol", flat=True)[:60])
    quotes: dict = {}
    feed = ""

    # قفل لكل سوق: لتجميع الطلبات المتزامنة في نداء واحد.
    #
    # الذاكرة كانت تُكتب **بعد** انتهاء نداء الشبكة، فكل طلب يصل أثناء
    # النداء يجده فارغاً فيبدأ نداءً خاصاً به. ولوحتان مفتوحتان (أو
    # تبويبان) يستعلمان بفارق أجزاء من الثانية = نداءان كاملان إلى
    # Alpaca لنفس البيانات. والقفل يجعل الثاني ينتظر ثمّ يجد الجواب
    # جاهزاً بدل أن يكرّر العمل.
    lock = _QUOTE_LOCKS.setdefault(market, threading.Lock())
    with lock:
        # ربما ملأها من سبقنا إلى القفل
        cached = _QUOTE_CACHE.get(market)
        if cached and (time.time() - cached[0]) < QUOTE_TTL:
            return JsonResponse({"market": market, "streaming": False,
                                 "delayed": True, "cached": True,
                                 "coalesced": True, "quotes": cached[1]})
        try:
            from django.conf import settings

            from scanner.config import load_market

            cfg = load_market(settings.SCANNER_CONFIG_DIR / f"{market}.yaml")
            adapter = get_adapter(cfg.adapter)
            if hasattr(adapter, "quotes"):
                quotes = adapter.quotes(symbols)
            if hasattr(adapter, "snapshot_feed"):
                feed = str(adapter.snapshot_feed() or "")
        except Exception as exc:  # noqa: BLE001
            return JsonResponse({"market": market, "streaming": False,
                                 "error": str(exc)[:200], "quotes": {}})

        _QUOTE_CACHE[market] = (time.time(), quotes)
    # ‏«delayed» كانت مثبَّتة على True مهما كانت التغذية — وهذا يخفي
    # الفرق الذي يهمّ: أهي sip (السوق كاملاً) أم iex (بورصة واحدة).
    # الواجهة تحتاج الاسم لا وصفاً عامّاً.
    return JsonResponse({"market": market, "streaming": False,
                         "feed": feed, "partial": feed in ("iex",),
                         "delayed": True, "cached": False, "quotes": quotes})


def api_stats(request):
    """ملخص عبر الأسواق للوحة العلوية."""
    data = []
    for m in MARKETS:
        run = _latest_run(m)
        if run is None:
            data.append({"market": m, "run": None})
            continue
        data.append({
            "market": m, "timeframe": run.timeframe,
            "started_at": run.started_at.isoformat(),
            "scanned": run.symbols_scanned, "ready": run.ready_count,
        })
    return JsonResponse({"markets": data})


# ------------------------------------------------------------ مساعدات

def _tv_symbol(symbol: str) -> str:
    if symbol.endswith(".SR"):
        return f"TADAWUL:{symbol[:-3]}"
    if symbol.endswith("USDT"):
        return f"BINANCE:{symbol}"
    return symbol


def _tv_interval(timeframe: str) -> str:
    return {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60",
            "2h": "120", "4h": "240", "1d": "D", "1w": "W"}.get(timeframe, "240")


# ──────────────────────────────────────────── الأداء والصفقات

TRADE_STATUS_ORDER = ["open", "pending", "won", "lost", "expired", "cancelled"]

# مرشّحات حالة الصفقة. «محسومة» تجمع الرابحة والخاسرة لأنها وحدها
# ما يدخل الإحصاءات.
STATUS_FILTERS = {
    "all": (),
    "closed": ("won", "lost"),
    "won": ("won",),
    "lost": ("lost",),
    "open": ("open",),
    "pending": ("pending",),
    "expired": ("expired", "cancelled"),
}
STATUS_LABELS = {
    "all": "الكل", "closed": "محسومة", "won": "رابحة", "lost": "خاسرة",
    "open": "مفتوحة", "pending": "تنتظر", "expired": "لم تُفعَّل",
}


# ═══════════════ مرشّحا الرمز والتاريخ — مشتركان ═══════════════
#
# صفحتا الصفقات والمراقبة تحتاجانهما بالسلوك نفسه. ونسختان
# متطابقتان تتباعدان بعد أوّل تعديل: يُصلَح ترتيب التاريخ في
# إحداهما ويُنسى في الأخرى، فيصير المرشّح يعني شيئين.

def _clean_symbol(raw) -> str:
    """رمزٌ للبحث الجزئي — ‏«btc» تجد ‏BTCUSDT.

    يُقصّ إلى 32 محرفاً: خانة الرمز في القاعدة بهذا الطول، وما
    زاد لا يطابق شيئاً أبداً فيُعطي نتيجةً فارغة بلا سبب ظاهر.
    """
    return (str(raw or "").strip().upper())[:32]


def _one_date(raw):
    """‏«YYYY-MM-DD» → تاريخاً، وما سواه → ‏None.

    الخانة ``<input type=date>`` لا تُرسل غير هذه الصيغة أو
    الفراغ. والقيمة المشوّهة تأتي من عنوانٍ حُرِّر يدوياً، فتُهمَل
    كما تُهمَل قيم المرشّحات الأخرى غير المعروفة.
    """
    from datetime import date

    txt = str(raw or "").strip()
    if not txt:
        return None
    try:
        y, m, d = txt.split("-")
        return date(int(y), int(m), int(d))
    except (ValueError, TypeError):
        return None


def _date_range(request, *, key_from="from", key_to="to"):
    """مدى تاريخي من العنوان — والمقلوب يُصحَّح لا يُفرَّغ.

    ═══ لماذا يُبدَّل الطرفان ═══

    «من 2026-08-27 إلى 2026-08-20» يعطي صفر نتيجة. والصفر يُقرأ
    «لا صفقات في هذه الفترة» وهو خطأ في الإدخال لا في البيانات —
    فيبحث المستخدم عن عطبٍ ليس موجوداً. والتبديل يفعل ما قصده
    قطعاً.
    """
    a = _one_date(request.GET.get(key_from))
    b = _one_date(request.GET.get(key_to))
    if a and b and a > b:
        a, b = b, a
    return a, b


def _apply_date(qs, field: str, start, end):
    """يقصر الاستعلام على مدى تاريخي — بالتوقيت المحلّي.

    ``__date`` في Django مع ``USE_TZ`` يحوّل العمود إلى المنطقة
    النشطة (‏Asia/Riyadh) قبل المقارنة. فيوم «27 أغسطس» عند
    المستخدم هو يومه لا يوم UTC — وهما يختلفان ثلاث ساعات، أي
    أنّ صفقات المساء كانت ستقع في اليوم التالي.
    """
    if start:
        qs = qs.filter(**{f"{field}__date__gte": start})
    if end:
        qs = qs.filter(**{f"{field}__date__lte": end})
    return qs


def _trade_filters(request):
    """قراءة المرشّحات من العنوان — مع تجاهل القيم غير المعروفة بصمت."""
    source = request.GET.get("source") or "auto"
    if source not in ("auto", "manual", "breakout", "all"):
        source = "auto"
    market = request.GET.get("market") or ""
    timeframe = request.GET.get("tf") or ""
    status = request.GET.get("status") or "all"
    start, end = _date_range(request)
    return {
        "source": source,
        "market": market if market in MARKETS else "",
        "timeframe": timeframe if timeframe in UI_TIMEFRAMES else "",
        "status": status if status in STATUS_FILTERS else "all",
        "status_label": STATUS_LABELS.get(
            status if status in STATUS_FILTERS else "all", "الكل"),
        "symbol": _clean_symbol(request.GET.get("symbol")),
        # النصّ يعود للخانة كما فُهم لا كما كُتب: مدىً مقلوب
        # يُعاد مرتّباً، فيرى المستخدم ما طُبِّق فعلاً.
        "date_from": start.isoformat() if start else "",
        "date_to": end.isoformat() if end else "",
        "_start": start, "_end": end,
    }


def _query_suffix(f) -> str:
    """سلسلة الاستعلام التي تُبقي مرشّحات الصفحة في نداء التحديث."""
    from django.utils.http import urlencode

    parts = {"source": f["source"]}
    if f["market"]:
        parts["market"] = f["market"]
    if f["timeframe"]:
        parts["tf"] = f["timeframe"]
    if f["status"] != "all":
        parts["status"] = f["status"]
    if f.get("symbol"):
        parts["symbol"] = f["symbol"]
    if f.get("date_from"):
        parts["from"] = f["date_from"]
    if f.get("date_to"):
        parts["to"] = f["date_to"]
    return "?" + urlencode(parts)


def _trade_queryset(f):
    """نطاق **الإحصاءات** — بلا مرشّح الحالة عمداً.

    إدخال الحالة هنا يجعل «رابحة» تعطي نسبة نجاح 100% وتوقّعاً موجباً
    دائماً — رقم صحيح حسابياً وبلا معنى. الحالة تُرشّح الجدول وحده،
    والبطاقات تبقى على العيّنة الكاملة.
    """
    qs = Trade.objects.all()
    if f["source"] != "all":
        qs = qs.filter(source=f["source"])
    if f["market"]:
        qs = qs.filter(market=f["market"])
    if f["timeframe"]:
        qs = qs.filter(timeframe=f["timeframe"])
    if f.get("symbol"):
        # ‏icontains لا ‏exact: من يكتب «btc» يريد ‏BTCUSDT، ولو
        # طُلب التطابق التامّ لوجب عليه حفظ اللاحقة لكل سوق.
        qs = qs.filter(symbol__icontains=f["symbol"])
    # ═══ التاريخ على وقت الإشارة ═══
    #
    # ثلاثة أوقات في الصفقة: الإشارة والفتح والحسم. و«الحسم»
    # يُخفي كل صفقة مفتوحة (‏closed_at فارغ)، فيبدو أنّ الأسبوع
    # بلا نشاط وفيه عشر صفقات قائمة. و«الإشارة» موجود دائماً.
    qs = _apply_date(qs, "signal_at", f.get("_start"), f.get("_end"))
    return qs


def _apply_status(qs, status: str):
    """مرشّح الحالة — للجدول لا للإحصاءات."""
    wanted = STATUS_FILTERS.get(status) or ()
    return qs.filter(status__in=wanted) if wanted else qs


def _status_counts(qs) -> dict:
    """عدد الصفقات لكل حالة — يظهر على الرقائق فيُعرف الفارغ قبل الضغط."""
    from django.db.models import Count

    raw = dict(qs.values_list("status").annotate(n=Count("id")))
    out = {}
    for key, states in STATUS_FILTERS.items():
        out[key] = (sum(raw.values()) if not states
                    else sum(raw.get(s, 0) for s in states))
    return out


def _settled_stats(qs) -> dict:
    """نسبة الفوز ومتوسّط R — بفاصل ثقة لا برقمٍ عارٍ.

    ═══ لماذا الفاصل ═══

    شاشة التصميم تعرض «نسبة الفوز ‎68.4٪‎» رقماً مفرداً. ورقمٌ
    مفرد على عشرين صفقة يُقرأ كما يُقرأ على ألفين، وهو ليس كذلك:
    عشرون صفقة بمعدّل ‎60٪‎ فاصلها ‎[36–81]‎ — أي أنّها قد تكون
    أسوأ من العملة المعدنية.

    وفاصل ويلسون يصلح للعيّنات الصغيرة، بخلاف التقريب الطبيعي
    الذي يعطي حدوداً خارج ‎[0,1]‎ عند الأطراف.

    ومتوسّط R وحده لا يكفي: توزيعه ملتوٍ — خسائرُ محدودة عند ‎-1‎
    وأرباحٌ ممتدّة — فالوسيط يُذكر معه.
    """
    import math
    from statistics import median, pstdev

    rows = list(qs.filter(status__in=("won", "lost"))
                .values_list("status", "r_multiple"))
    n = len(rows)
    if not n:
        return {"settled": 0}
    wins = sum(1 for st, _ in rows if st == "won")
    rs = [float(r) for _, r in rows if r is not None]

    p = wins / n
    z = 1.959963985
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    out = {
        "settled": n,
        "wins": wins,
        "win_rate": round(100 * p, 1),
        "win_low": round(100 * max(0.0, centre - half)),
        "win_high": round(100 * min(1.0, centre + half)),
        "avg_r": round(sum(rs) / len(rs), 2) if rs else None,
        "median_r": round(median(rs), 2) if rs else None,
    }
    if not rs:
        return out

    # ═══ الوحدة R لا النسبة المئوية ═══
    #
    # شاشة التصميم تعرض «العائد ‎+24.8٪‎» و«التراجع ‎-12.3٪‎».
    # والنسبة المئوية تحتاج رأس مالٍ ومقدار مخاطرةٍ لكل صفقة، وليس
    # في السجلّ حجمُ مركزٍ واحد — الصفقات تُسجَّل بالدخول والوقف
    # والهدف، لا بالمبلغ.
    #
    # فالرقم بـ R: «‎+97.7R‎» يعني أنّك ربحت 97.7 ضعف ما تخاطر به
    # في الصفقة الواحدة. وهو صادق وقابل للتحويل متى عُرف المبلغ.
    # وعرضُه نسبةً مئوية يتطلّب اختراع رأس مال — ورقمٌ مخترَع في
    # خانة العائد أخطر من غيابه.
    equity, peak, mdd = 0.0, 0.0, 0.0
    for x in rs:
        equity += x
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    gain = sum(x for x in rs if x > 0)
    loss = -sum(x for x in rs if x < 0)
    sd = pstdev(rs) if len(rs) > 1 else 0.0
    out.update({
        "total_r": round(equity, 1),
        "max_dd_r": round(mdd, 1),
        # عامل الربح: كل ريال خسارة مقابل كم من الربح
        "profit_factor": round(gain / loss, 2) if loss else None,
        # شارب لكل صفقة لا سنويّاً: التسنين يحتاج وتيرة تداولٍ
        # ثابتة، وهي غير متحقّقة هنا.
        "sharpe_per_trade": round((sum(rs) / len(rs)) / sd, 2) if sd else None,
    })
    return out


def _research_bundle(request):
    """بيانات مشتركة بين صفحة البحث الكمّي وواجهتها."""
    from django.db.utils import OperationalError, ProgrammingError
    from scanner.research import build_dashboard

    f = _trade_filters(request)
    setup_error = ""
    counts: dict = {}
    dashboard = {}
    rows: list = []
    try:
        qs = _trade_queryset(f)
        rows = trade_svc.rows_for_stats(qs)
        counts = _status_counts(qs)
        page_obj = _paginate(_apply_status(qs, f["status"])
                             .order_by("-signal_at"), request)
        trades = list(page_obj)
    except (OperationalError, ProgrammingError):
        trades, page_obj = [], None
        setup_error = "جدول الصفقات غير موجود — شغّل: python web/manage.py migrate"
    else:
        try:
            dashboard = build_dashboard(
                rows, market=f["market"] or "crypto",
                timeframe=f["timeframe"] or "4h")
        except Exception as exc:  # noqa: BLE001
            setup_error = f"تعذّر بناء لوحة البحث: {str(exc)[:120]}"

    stats = _settled_stats(qs) if page_obj is not None else {"settled": 0}
    overall = tracking.summarize(rows)
    splits = [
        ("التصنيف", tracking.split(rows, "grade", min_n=3)),
        ("الفريم", tracking.split(rows, "timeframe", min_n=3)),
        ("السوق", tracking.split(rows, "market", min_n=3)),
        ("سبب الدخول", tracking.split_multi(rows, "factors", min_n=3)),
    ]
    return {
        "stats": stats,
        "f": f,
        "rows": rows,
        "dashboard": dashboard,
        "counts": counts,
        "setup_error": setup_error,
        "trades": trades,
        "page_obj": page_obj,
        "overall": overall,
        "splits": [{"title": t, "rows": r} for t, r in splits],
    }


def research(request):
    """مختبر البحث الكمّي — shell فوري، الأقسام تُحمَّل بشكل مستقل."""
    f = _trade_filters(request)
    return render(request, "dashboard/research.html", {
        "nav_page": "research",
        "show_market_chips": False,
        "markets": MARKETS,
        "market": f["market"] or "crypto",
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": f["timeframe"],
        "tf_in_page": True,
        "filters": f,
        "tz_name": _timezone_name(),
        "statuses": [{"key": k, "label": STATUS_LABELS[k], "count": 0}
                     for k in ("all", "closed", "won", "lost", "open",
                               "pending", "expired")],
        "payload": {
            "query": _query_suffix(f),
        },
    })


def trades(request):
    """الصفقات — جداول تشغيلية مع تبويبات."""
    f = _trade_filters(request)
    return render(request, "dashboard/trades.html", {
        "nav_page": "trades",
        "market_options": market_options(),
        "show_market_chips": False,
        "markets": MARKETS,
        "market": f["market"] or "crypto",
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": f["timeframe"] or "4h",
        "filters": f,
        "payload": {"query": _query_suffix(f)},
    })


def analytics(request):
    """التحليلات — أين يأتي الأداء ولماذا."""
    f = _trade_filters(request)
    return render(request, "dashboard/analytics.html", {
        "nav_page": "analytics",
        "show_market_chips": False,
        "markets": MARKETS,
        "market": f["market"] or "crypto",
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": f["timeframe"] or "4h",
        "filters": f,
        "payload": {"query": _query_suffix(f)},
    })


def optimization(request):
    """تحسين الاستراتيجية — لوحة المتصدرين وسجل التحسين."""
    return render(request, "dashboard/optimization.html", {
        "nav_page": "optimization",
        "show_market_chips": False,
        "markets": MARKETS,
        "market": "crypto",
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": "4h",
        "payload": {"countdown": None},
    })


def ai(request):
    """مركز الذكاء الاصطناعي — لماذا يوصي النظام بما يوصي به."""
    f = _trade_filters(request)
    return render(request, "dashboard/ai.html", {
        "nav_page": "ai",
        "show_market_chips": False,
        "markets": MARKETS,
        "market": f["market"] or "crypto",
        "timeframes": [{"key": t, "label": TIMEFRAME_LABELS[t]} for t in UI_TIMEFRAMES],
        "timeframe": f["timeframe"] or "4h",
        "filters": f,
        "payload": {"query": _query_suffix(f)},
    })


def api_research(request):
    """JSON للوحة البحث الكمّي."""
    bundle = _research_bundle(request)
    if bundle["setup_error"]:
        return JsonResponse({"error": bundle["setup_error"]}, status=500)
    f = bundle["f"]
    qs = _trade_queryset(f)
    recent = [
        {"id": t.id, "symbol": t.symbol, "timeframe": t.timeframe,
         "status": t.status, "label": t.get_status_display(),
         "r": t.r_multiple, "unrealized": t.unrealized_r,
         "grade": t.grade, "note": t.resolution_note,
         "opened": _local_text(t.opened_at),
         "opened_full": _local_text(t.opened_at, "Y-m-d H:i"),
         "closed": _local_text(t.closed_at),
         "closed_full": _local_text(t.closed_at, "Y-m-d H:i"),
         "held": _held_text(t)}
        for t in _apply_status(qs, f["status"]).order_by("-signal_at")[:400]
    ]
    return JsonResponse({
        "overall": bundle["overall"],
        "dashboard": bundle["dashboard"],
        "trades": recent,
        "counts": bundle["counts"],
        "settlement": _settlement_status(),
    })


def api_research_export(request):
    """تصدير بيانات البحث الكمّي."""
    import csv
    import json
    from io import StringIO

    bundle = _research_bundle(request)
    fmt = (request.GET.get("format") or "json").lower()
    if fmt == "csv":
        buf = StringIO()
        writer = csv.writer(buf)
        writer.writerow(["section", "key", "value"])
        dash = bundle["dashboard"]
        for key, val in (dash.get("health") or {}).items():
            writer.writerow(["health", key, val])
        for row in dash.get("experiments") or []:
            writer.writerow(["experiment", row.get("experiment_id"),
                             row.get("expectancy")])
        for row in dash.get("contributions") or []:
            writer.writerow(["factor", row.get("label"), row.get("marginal_delta")])
        resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="research_export.csv"'
        return resp
    return JsonResponse(bundle["dashboard"], json_dumps_params={"ensure_ascii": False})


def performance(request):
    """إعادة توجيه إلى لوحة البحث الكمّي مع الحفاظ على المرشّحات."""
    qs = request.META.get("QUERY_STRING") or ""
    target = "/research/" + ("?" + qs if qs else "")
    return redirect(target)


@require_POST
def api_track(request):
    """فتح صفقة يدوية من صفحة الرمز."""
    symbol = (request.POST.get("symbol") or "").strip()
    market = (request.POST.get("market") or "").strip()
    timeframe = (request.POST.get("timeframe") or "").strip()
    if not symbol or market not in MARKETS:
        return JsonResponse({"ok": False, "reason": "رمز أو سوق غير صالح"}, status=400)
    if timeframe not in UI_TIMEFRAMES:
        return JsonResponse({"ok": False, "reason": "فريم غير مدعوم"}, status=400)

    try:
        analysis = _analyze_on_demand(symbol, market, persist=True,
                                      timeframe=timeframe)
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "reason": str(exc)[:200]})

    reco = analysis.get("reco") or {}
    if reco.get("action") not in ("now", "pending"):
        return JsonResponse({"ok": False,
                             "reason": "لا توصية قابلة للتتبّع على هذا الفريم"})

    row = (ScanResult.objects.filter(market=market, symbol=symbol,
                                     timeframe=timeframe)
           .order_by("-candle_time").first())
    if row is None:
        return JsonResponse({"ok": False, "reason": "تعذّر حفظ نتيجة التحليل"})

    try:
        trade = trade_svc.open_manual(row, reco, timeframe,
                                      note=(request.POST.get("note") or "")[:200])
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "reason": str(exc)[:200]})

    if trade is None:
        return JsonResponse({"ok": False,
                             "reason": "متابَعة بالفعل على شمعة هذه الإشارة"})
    return JsonResponse({"ok": True, "id": trade.id,
                         "entry": trade.entry, "stop": trade.stop,
                         "target": trade.target1, "grade": trade.grade})


@require_POST
def api_trade_cancel(request, trade_id: int):
    """إلغاء متابعة — للصفقات التي لم تُحسم بعد فقط.

    المحسومة لا تُلغى: حذف الخسائر من السجل يجعل الإحصاءات كذبة مريحة.
    """
    trade = Trade.objects.filter(id=trade_id).first()
    if trade is None:
        return JsonResponse({"ok": False, "reason": "غير موجودة"}, status=404)
    if trade.is_closed:
        return JsonResponse({"ok": False,
                             "reason": "الصفقة محسومة — لا تُحذف من السجل"})
    trade.status = "cancelled"
    trade.resolution_note = "أُلغيت يدوياً"
    trade.save(update_fields=["status", "resolution_note"])
    return JsonResponse({"ok": True})


def api_performance(request):
    """الأرقام وحالة الحسم — لتحديث الصفحة بلا إعادة تحميل."""
    f = _trade_filters(request)
    try:
        qs = _trade_queryset(f)
        rows = trade_svc.rows_for_stats(qs)
        recent = [
            {"id": t.id, "symbol": t.symbol, "timeframe": t.timeframe,
             "status": t.status, "label": t.get_status_display(),
             "r": t.r_multiple, "unrealized": t.unrealized_r,
             "grade": t.grade, "note": t.resolution_note,
             "entry": t.entry, "stop": t.stop, "target1": t.target1,
             "entry_price": t.entry_price, "exit_price": t.exit_price,
             "last_price": t.last_price,
             "opened": _local_text(t.opened_at),
             "opened_full": _local_text(t.opened_at, "Y-m-d H:i"),
             "closed": _local_text(t.closed_at),
             "closed_full": _local_text(t.closed_at, "Y-m-d H:i"),
             "held": _held_text(t)}
            for t in _apply_status(qs, f["status"]).order_by("-signal_at")[:400]
        ]
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"error": f"تعذّر قراءة الصفقات: {str(exc)[:120]}"})

    return JsonResponse({
        "overall": tracking.summarize(rows),
        "trades": recent,
        "counts": _status_counts(qs),
        "settlement": _settlement_status(),
    })


def _local_text(value, fmt: str = "m-d H:i") -> str | None:
    """وقت منسَّق بالتوقيت المحلي — جاهزاً للعرض بلا تحويل في المتصفّح.

    كان يُرسَل ``isoformat()`` بـ UTC ويقصّه JavaScript نصّياً، فيكتب
    فوق ما رسمه الخادم بالتوقيت المحلي. النتيجة أن «وقت الرصد» يظهر
    محلياً بينما «الدخول» و«الخروج» يعودان إلى UTC بعد أول تحديث —
    فيبدو الرصد بعد الدخول، وهو مستحيل.

    التنسيق في مكان واحد كما في الأرقام: الخادم يُنسّق، والمتصفّح يعرض.
    """
    if not value:
        return None
    from django.utils import formats, timezone as tz

    try:
        return formats.date_format(tz.localtime(value), fmt)
    except (ValueError, TypeError):
        return None


def _timezone_name() -> str:
    """المنطقة الزمنية المعروضة — تُذكر صراحةً فلا يُخمّنها القارئ."""
    from django.conf import settings as dj

    return getattr(dj, "TIME_ZONE", "UTC")


def _held_text(trade) -> str:
    """مدة الاحتفاظ بصيغة العرض — نفس منطق مرشّح القالب."""
    from .templatetags.fmt import span

    return span(trade.opened_at, trade.closed_at)


def _settlement_status() -> dict:
    """حالة عامل الحسم بصيغة صالحة للعرض مباشرة."""
    from . import settlement

    st = settlement.status()
    ago = None
    if st.get("last_run"):
        ago = int(time.time() - st["last_run"])
    return {
        "running": st["running"], "started": st["thread_started"],
        "seconds_ago": ago, "checked": st["checked"],
        "settled": st["settled"], "settled_total": st["settled_total"],
        "groups": st["groups"], "error": st["last_error"],
    }


@require_POST
def api_repair_times(request):
    """يعيد اشتقاق أوقات الصفقات المحسومة من الشموع.

    الحسم لا يكتب فوق وقت موجود، فالصفوف التي حُسمت قبل إصلاح الأوقات
    تبقى بوقت معالجة — وبعضها بخروج قبل الدخول.
    """
    from . import settlement

    try:
        result = settlement.repair_times()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "reason": str(exc)[:200]})
    if result.get("error"):
        return JsonResponse({"ok": False, "reason": result["error"]})
    return JsonResponse({
        "ok": True, **result,
        "reason": (f"فُحصت {result['checked']} · صُحّحت {result['fixed']}"
                   + (f" · منها {result['inverted']} مقلوبة"
                      if result["inverted"] else "")
                   + (f" · {result['skipped']} بلا شموع"
                      if result["skipped"] else "")),
    })


@require_POST
def api_settle_now(request):
    """حسم فوري بطلب من المستخدم — لا ينتظر الدورة."""
    from . import settlement

    if settlement.status()["running"]:
        return JsonResponse({"ok": False, "reason": "دورة حسم جارية بالفعل"})
    try:
        result = settlement.settle_once()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "reason": str(exc)[:200]})
    if result.get("error"):
        return JsonResponse({"ok": False, "reason": result["error"]})
    return JsonResponse({
        "ok": True, **result,
        "reason": (f"فُحصت {result['checked']} صفقة · "
                   f"حُسمت {result['settled']}"
                   + (f" · انتهت {result['expired']}" if result["expired"] else "")),
    })


# ──────────────────────────────────────────── الإعدادات

def settings_page(request):
    """عرض الإعدادات وحفظها — تُبنى الحقول من المخطط لا من القالب."""
    notes: list[str] = []
    saved = False

    if request.method == "POST":
        if request.POST.get("action") == "reset":
            appsettings.reset()
            notes.append("أُعيدت كل الإعدادات إلى الافتراضي.")
            saved = True
        else:
            _, notes = appsettings.save(request.POST.dict())
            saved = True

    current = appsettings.values(force=True)
    groups = []
    for g in settings_schema.GROUPS:
        rows = []
        for f in g.fields:
            rows.append({
                "key": f.key, "label": f.label, "kind": f.kind,
                "help": f.help, "unit": f.unit, "step": f.step,
                "min": f.minimum, "max": f.maximum, "choices": f.choices,
                "value": current.get(f.key, f.default),
                "default": f.default,
                "changed": current.get(f.key, f.default) != f.default,
            })
        groups.append({"key": g.key, "title": g.title, "note": g.note,
                       "fields": rows})

    return render(request, "dashboard/settings.html", {
        "nav_page": "settings",
        "show_market_chips": False,
        "markets": MARKETS, "market": "crypto",
        "groups": groups, "notes": notes, "saved": saved,
        "storage_format": _storage_format(),
        "liquidity_gap": _liquidity_gap(),
        "ai_advisor_status": _ai_advisor_status(),
        "local_ai_status": _local_ai_status(),
        "payload": {"countdown": None},
    })


def _ai_advisor_status() -> dict:
    """AI Advisor status for settings page — no secrets."""
    try:
        from scanner.ai_advisor.provider_config import config_to_public_dict, load_config
        from scanner.ai_advisor.provider_factory import create_claude_provider
        from scanner.ai_advisor.runtime_state import AdvisorRuntimeState

        cfg = load_config()
        provider = create_claude_provider(cfg)
        health = provider.health()
        runtime = AdvisorRuntimeState().load()
        runtime_status = runtime.get("status", "disconnected")
        provider_connected = (
            health.get("healthy", False)
            or runtime_status in ("connected", "running")
        )
        return {
            **config_to_public_dict(cfg),
            "provider_status": provider_connected,
            "runtime_status": runtime_status,
            "latency_ms": runtime.get("latency_ms") or health.get("latency_ms"),
            "last_success": (
                runtime.get("last_test_at")
                or runtime.get("last_review_at")
                or health.get("last_success")
            ),
            "average_response_time_ms": health.get("average_response_time_ms"),
            "error_rate": health.get("error_rate", 0),
            "provider_mode": health.get("mode", "unknown"),
        }
    except Exception:  # noqa: BLE001
        return {"available": False}


def _local_ai_status() -> dict:
    """Local AI status for settings — no secrets."""
    try:
        from scanner.ai_local.config import load_local_config
        from scanner.ai_local.health import check_ollama_health
        from scanner.ai_local.history import LocalAIHistory
        from scanner.ai_local.metrics import compute_metrics
        from scanner.ai_local.runtime import runtime_status

        cfg = load_local_config()
        health = check_ollama_health(cfg)
        metrics = compute_metrics()
        last = LocalAIHistory().list_recent(1)
        return {
            "enabled": cfg.local_enabled and cfg.ollama_enabled,
            "status": runtime_status(),
            "execution_mode": cfg.execution_mode,
            "default_model": cfg.local_default_model,
            "ollama_reachable": health.get("ollama_reachable", False),
            "model_available": health.get("model_available", False),
            "total_reviews": metrics.get("total_reviews", 0),
            "last_review": last[0] if last else None,
            "base_url": cfg.ollama_base_url,
        }
    except Exception:  # noqa: BLE001
        return {"enabled": False, "status": "NOT READY"}


@require_POST
def api_ai_advisor_test_connection(request):
    """Test Claude provider connection — metadata only in response."""
    try:
        from scanner.ai_advisor.provider_factory import create_claude_provider

        provider = create_claude_provider()
        result = provider.test_connection()
        if result.get("connected"):
            from datetime import datetime, timezone
            from scanner.ai_advisor.runtime_state import AdvisorRuntimeState
            AdvisorRuntimeState().set_status(
                "connected",
                model=result.get("model"),
                latency_ms=result.get("latency_ms"),
                last_test_at=datetime.now(timezone.utc).isoformat(),
            )
        return JsonResponse({
            "ok": result.get("connected", False),
            "connected": result.get("connected", False),
            "latency_ms": result.get("latency_ms"),
            "model": result.get("model"),
            "provider_version": result.get("provider_version"),
            "error": result.get("error", ""),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({
            "ok": False,
            "connected": False,
            "error": str(exc)[:200],
        })


@require_POST
def api_optimization_run(request):
    """Run optimization from UI — uses closed trades."""
    try:
        from scanner.optimization import OptimizationService
        from scanner.tracking import LOST, WON

        from . import trades as trade_svc
        from .models import Trade

        qs = Trade.objects.filter(status__in=[WON, LOST]).order_by("-closed_at")[:500]
        rows = trade_svc.rows_for_stats(qs)
        if len(rows) < 10:
            return JsonResponse({
                "ok": False,
                "error": "insufficient_trades",
                "message": f"تحتاج 10 صفقات محسومة على الأقل — المتوفر: {len(rows)}",
                "trade_count": len(rows),
            })

        svc = OptimizationService()
        space = svc.build_space(min_score_range=(60, 85, 5), require_htf=True)
        report = svc.optimize(
            rows, space, method="grid",
            title="Optimization Lab Run",
        )
        return JsonResponse({
            "ok": True,
            "experiment_id": report.get("experiment_id"),
            "status": report.get("status"),
            "trade_count": len(rows),
            "total_evaluated": (report.get("leaderboard") or {}).get("total_evaluated"),
            "best_expectancy": (
                (report.get("report") or {}).get("best_metrics", {}).get("expectancy")
            ),
        })
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "error": str(exc)[:200]})


def _storage_format() -> str:
    try:
        from scanner import storage

        return storage.storage_format()
    except Exception:  # noqa: BLE001
        return "csv"


def _liquidity_gap() -> dict:
    """كم نتيجة بلا حجم تداول؟ الرقم هو ما يفسّر تعطّل فلتر السيولة."""
    try:
        total = ScanResult.objects.count()
        missing = ScanResult.objects.filter(quote_volume__isnull=True).count()
    except Exception:  # noqa: BLE001
        return {"total": 0, "missing": 0}
    return {"total": total, "missing": missing}


@require_POST
def api_backfill_liquidity(request):
    """يحسب حجم التداول للنتائج المحفوظة من الشموع المخزّنة.

    وجوده لأن إضافة عمود السيولة لا تُصلح صفوفاً حُفظت قبلها، فيبدو
    الفلتر معطّلاً حتى يمرّ مسح كامل. الشموع محفوظة أصلاً على القرص،
    فالحساب منها لا يكلّف طلب شبكة واحداً.
    """
    from scanner import liquidity as liq
    from scanner import storage

    tiers = appsettings.liquidity_tiers()
    updated = skipped = 0
    cache: dict[tuple, float | None] = {}

    rows = list(ScanResult.objects.filter(quote_volume__isnull=True)[:5000])
    for row in rows:
        key = (row.market, row.symbol, row.timeframe)
        if key not in cache:
            try:
                df = storage.load(row.market, row.symbol, row.timeframe)
                cache[key] = liq.from_candles(df, row.timeframe)
            except Exception:  # noqa: BLE001
                cache[key] = None
        qv = cache[key]
        if qv is None:
            skipped += 1
            continue
        row.quote_volume = qv
        row.liquidity = liq.tier(qv, tiers)
        row.save(update_fields=["quote_volume", "liquidity"])
        updated += 1

    return JsonResponse({
        "ok": True, "updated": updated, "skipped": skipped,
        "remaining": max(0, len(rows) - updated - skipped),
        "reason": (f"حُسبت السيولة لـ {updated} نتيجة"
                   + (f" · {skipped} بلا شموع محفوظة" if skipped else "")),
    })
