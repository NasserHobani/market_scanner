# -*- coding: utf-8 -*-
"""فتح الصفقات المتتبَّعة وحسمها.

تقسيم المسؤوليات مقصود: كل الرياضيات في ``scanner.tracking`` (تُختبر بلا
Django ولا شبكة)، وهذا الملف يترجم بينها وبين قاعدة البيانات فقط.

قاعدة تحكم الملف كله: تتبّع الصفقات ميزة إضافية. أي فشل فيها — جدول
مفقود، هجرة غير مطبَّقة، بيانات ناقصة — يجب أن يُسجَّل ويُتخطّى، لا أن
يُسقط المسح. المسح هو الوظيفة، وهذه مرآته.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.db.utils import (DatabaseError, IntegrityError, OperationalError,
                             ProgrammingError)
from django.utils import timezone

from scanner.tracking import EXPIRED, LOST, OPEN, PENDING, WON, Plan, resolve

from .models import Trade

log = logging.getLogger(__name__)

# مهلة الدخول بالشموع لكل فريم — نفس منطق الفرص المراقَبة
ENTRY_DEADLINE_BARS = {"15m": 96, "1h": 48, "4h": 30, "1d": 10, "1w": 4}

# أقصى عمر لصفقة مفتوحة قبل أن تُغلق قسراً بسعر السوق. بدونه تبقى
# صفقة عالقة سنة كاملة خارج الإحصاءات فتُخفي خسارة حقيقية.
MAX_HOLD_BARS = {"15m": 200, "1h": 150, "4h": 100, "1d": 60, "1w": 26}

# ترجمة بنود حساب التوصية إلى مفاتيح ثابتة يمكن التجميع عليها بعد سنة.
# الأسباب نصّ حرّ تتغيّر صياغته، أمّا هذه فعقد لا يُكسر بلا هجرة بيانات.
FACTOR_KEYS = {
    "الفريم الأعلى": "htf",
    "نماذج الشموع": "candles",
    "النموذج السعري": "pattern",
    "موجات إليوت": "elliott",
    "عناصر الالتقاء": "confluence",
    "حركة السعر": "price_action",
    "الدرجة الموزونة": "score",
    "اصطياد سيولة سفلية": "sweep",
    # صوت النموذج التعلّمي. ربطه بمفتاح ليس تنظيماً بل شرط قياس: بلا
    # مفتاح يختفي من تحليل «سبب الدخول» تماماً، فيصير مدخلاً يؤثّر في
    # القرار ولا يظهر في أي جدول أداء — ولا سبيل لمعرفة هل ينفع أم يضرّ.
    # وهذا أسوأ ما يمكن أن يُضاف إلى نظام غرضه القياس.
    "تصويت النموذج": "ml_vote",
}
FACTOR_LABELS = {
    "htf": "الفريم الأعلى",
    "candles": "نماذج الشموع",
    "pattern": "النموذج السعري",
    "elliott": "موجات إليوت",
    "confluence": "عناصر الالتقاء",
    "price_action": "حركة السعر",
    "score": "الدرجة",
    "sweep": "اصطياد سيولة",
    "ml_vote": "تصويت النموذج",
    "breakout": "اختراق حجمي",
}


def _viability(plan, result_row) -> dict:
    """حكم الجدوى الاقتصادية — بلا إسقاط المسح عند أي تعذّر.

    فئة السيولة من صفّ المسح نفسه: هي ما نعرفه عن الرمز لحظة الإشارة،
    ولا تُقرأ من مكان آخر حتى لا يختلف الحكم عن الظرف الذي أنتجه.
    """
    from scanner import execution as ex

    try:
        risk_pct = plan.risk / plan.entry * 100 if plan.entry else 0.0
        tier = getattr(result_row, "liquidity", None) or "unknown"
        max_ratio = ex.MAX_COST_RATIO
        model = ex.DEFAULT
        try:
            from . import appsettings

            max_ratio = float(appsettings.get("max_cost_ratio",
                                              ex.MAX_COST_RATIO))
            model = appsettings.cost_model()
        except Exception:  # noqa: BLE001
            pass
        if max_ratio <= 0:            # صفر = البوّابة مطفأة
            return {"ok": True, "reason": "", "cost_r": 0.0}
        return ex.viability(risk_pct, tier, model, max_ratio=max_ratio)
    except Exception as exc:  # noqa: BLE001
        log.debug("تعذّر حساب الجدوى: %s", str(exc)[:80])
        return {"ok": True, "reason": "", "cost_r": 0.0}


def extract_factors(reco: dict | None) -> list[str]:
    """العوامل التي دفعت التوصية للأعلى فقط.

    البنود السالبة تُستبعد عمداً: السؤال «أي عامل يسبق الصفقات الرابحة؟»
    وعاملٌ طرح من الدرجة لم يدفع لدخولها.
    """
    if not reco:
        return []
    out: list[str] = []
    for item in reco.get("breakdown") or []:
        try:
            value = float(item.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        key = FACTOR_KEYS.get(str(item.get("label") or "").strip())
        if key and key not in out:
            out.append(key)
    return out


def _deadline(timeframe: str, bars_map: dict, default: int):
    from scanner.live import timeframe_seconds

    bars = bars_map.get(timeframe, default)
    return timedelta(seconds=timeframe_seconds(timeframe) * bars)


def open_from_reco(result_row, reco: dict | None, timeframe: str,
                   source: str = "auto") -> Trade | None:
    """يفتح صفقة متتبَّعة من توصية قابلة للتنفيذ.

    ``result_row`` صف ScanResult المحفوظ — منه نأخذ وقت الشمعة الذي يمنع
    ازدواج الصفقة عند إعادة المسح.
    """
    # ═══ الحرس الأخير ═══
    #
    # لا تُفتح صفقة على رمزٍ محظور مهما كان المسار: توصية مخزّنة،
    # مراقبة سُلّحت قبل الحظر، أو ضغطة يدوية. والمنع هنا لأنّه آخر
    # نقطة يمرّ بها كل من يفتح صفقة.
    try:
        from . import blocklist

        if blocklist.is_blocked(result_row.market, result_row.symbol):
            return None
    except Exception:  # noqa: BLE001
        pass

    if not reco:
        return None
    if reco.get("action") not in ("now", "pending"):
        return None

    targets = reco.get("targets") or []
    entry, stop = reco.get("entry"), reco.get("stop")
    target = targets[0] if targets else None
    if entry is None or stop is None or target is None:
        return None

    # ═══ لا صفقة بيع تُفتح ═══
    #
    # ``reco`` قاموسٌ يصل من المسح أو من الذكاء أو من الواجهة، وكان
    # اتّجاهه يُقرأ بلا سؤال. والمحرّك اليوم لا يُنتج بيعاً — لكنّ
    # «لا يُنتج اليوم» ليست ضماناً، والضمان يُكتب.
    from scanner import direction as _dir

    if not _dir.allowed(reco.get("side")):
        log.info("رُفضت صفقة بيع لـ %s — المنصّة شراءٌ فقط",
                 result_row.symbol)
        return None

    plan = Plan(side=_dir.LONG, entry=float(entry),
                stop=float(stop), target=float(target))
    if not plan.valid():
        log.debug("خطة غير صالحة لـ %s — لا صفقة", result_row.symbol)
        return None

    # بوّابة الجدوى: خطة لا تستطيع دفع كلفتها ليست خطة.
    #
    # قِيس على 96 صفقة أن الوقف دون 0.5% يعطي ‎+0.36R‎ إجمالياً و
    # ‎−3.75R‎ بعد التكلفة — خسارة مضمونة حسابياً قبل أن يتحرّك السعر.
    # وتسجيلها يفسد الإحصاءات مرّتين: يخفض التوقّع، ويشغل حدّ
    # الصفقات المتزامنة بخطط ميتة.
    verdict = _viability(plan, result_row)
    if not verdict["ok"]:
        log.debug("خطة غير اقتصادية لـ %s: %s", result_row.symbol,
                  verdict["reason"])
        return None

    now = timezone.now()
    # توصية «الآن» تُفتح فوراً بسعر الإغلاق؛ «لاحقاً» تنتظر بلوغ الدخول
    immediate = reco.get("action") == "now"

    # نقطة حفظ خاصة: هذه الدالة تُستدعى داخل transaction.atomic في أمر
    # المسح، والتقاط IntegrityError داخل معاملة بلا savepoint يترك
    # المعاملة كلها معطوبة فتفشل كل استعلامات المسح بعدها.
    fs_id = getattr(result_row, "feature_snapshot_id", "") or ""
    pit_id = getattr(result_row, "pit_snapshot_id", "") or ""
    reco_id = getattr(result_row, "recommendation_id", "") or ""
    try:
        with transaction.atomic():
            trade, created = Trade.objects.get_or_create(
                source=source, symbol=result_row.symbol, market=result_row.market,
                timeframe=timeframe, candle_time=result_row.candle_time,
                defaults=dict(
                    side=plan.side, entry=plan.entry, stop=plan.stop,
                    target1=plan.target, rr=reco.get("rr"),
                    grade=reco.get("grade") or "—",
                    score=getattr(result_row, "score", None),
                    confidence=float(reco.get("confidence") or 0),
                    action=reco.get("action") or "none",
                    reasons=" · ".join(reco.get("reasons") or [])[:255],
                    factors=extract_factors(reco),
                    feature_snapshot_id=fs_id,
                    pit_snapshot_id=pit_id,
                    recommendation_id=reco_id,
                    decision_timestamp=result_row.candle_time,
                    feature_version="3.0.0",
                    status=OPEN if immediate else PENDING,
                    signal_at=now, candle_time=result_row.candle_time,
                    expires_at=now + _deadline(timeframe, ENTRY_DEADLINE_BARS, 30),
                    # وقت السوق لا لحظة المسح: توصية «الآن» تدخل بإغلاق
                    # شمعة الإشارة، فوقت دخولها وقت تلك الشمعة. وضعُ
                    # timezone.now() هنا كان يخلط مصدرين — الدخول بوقت
                    # المعالجة والخروج بوقت الشمعة — فتخرج مدة سالبة
                    # وتظهر «—» في الجدول.
                    opened_at=result_row.candle_time if immediate else None,
                    entry_price=plan.entry if immediate else None,
                ),
            )
            # Backfill linkage only — never rewrite outcomes / plan fields
            if not created and trade:
                updates = []
                if not trade.feature_snapshot_id and fs_id:
                    trade.feature_snapshot_id = fs_id
                    updates.append("feature_snapshot_id")
                if not trade.pit_snapshot_id and pit_id:
                    trade.pit_snapshot_id = pit_id
                    updates.append("pit_snapshot_id")
                if not trade.recommendation_id and reco_id:
                    trade.recommendation_id = reco_id
                    updates.append("recommendation_id")
                if trade.decision_timestamp is None and result_row.candle_time:
                    trade.decision_timestamp = result_row.candle_time
                    updates.append("decision_timestamp")
                if not trade.feature_version:
                    trade.feature_version = "3.0.0"
                    updates.append("feature_version")
                if updates:
                    trade.save(update_fields=updates)
    except IntegrityError:
        return None       # سباق بين خيطين على الشمعة نفسها
    return trade if created else None


def open_manual(result_row, reco: dict, timeframe: str, note: str = "") -> Trade | None:
    """صفقة يدوية: المستخدم اختار متابعتها بنفسه."""
    # ═══ الحرس الأخير ═══
    #
    # لا تُفتح صفقة على رمزٍ محظور مهما كان المسار: توصية مخزّنة،
    # مراقبة سُلّحت قبل الحظر، أو ضغطة يدوية. والمنع هنا لأنّه آخر
    # نقطة يمرّ بها كل من يفتح صفقة.
    try:
        from . import blocklist

        if blocklist.is_blocked(result_row.market, result_row.symbol):
            return None
    except Exception:  # noqa: BLE001
        pass

    trade = open_from_reco(result_row, reco, timeframe, source="manual")
    if trade and note:
        trade.note = note[:200]
        trade.save(update_fields=["note"])
    return trade


def open_from_breakout(result_row, hit: dict, timeframe: str) -> Trade | None:
    """صفقة من تنبيه اختراق — مصدر منفصل حتى تُقاس وحدها.

    خلطها بالتوصيات كان سيفسد أرقام الاثنين: القياس الأوّلي لهذه
    الإشارة كان سالباً على 4h، فدمجها يخفي ضعفها ويشوّه قوّة غيرها.
    """
    if not hit:
        return None
    entry, stop, target = hit.get("entry"), hit.get("stop"), hit.get("target")
    if entry is None or stop is None or target is None:
        return None

    plan = Plan(side="buy", entry=float(entry), stop=float(stop),
                target=float(target))
    if not plan.valid():
        return None
    if not _viability(plan, result_row)["ok"]:
        return None

    now = timezone.now()
    try:
        with transaction.atomic():
            trade, created = Trade.objects.get_or_create(
                source="breakout", symbol=result_row.symbol,
                market=result_row.market, timeframe=timeframe,
                candle_time=result_row.candle_time,
                defaults=dict(
                    side="buy", entry=plan.entry, stop=plan.stop,
                    target1=plan.target, rr=hit.get("rr"),
                    grade="—", score=getattr(result_row, "score", None),
                    action="breakout",
                    reasons=" · ".join(hit.get("reasons") or [])[:255],
                    factors=["breakout"],
                    feature_snapshot_id=(getattr(result_row, "feature_snapshot_id", "") or ""),
                    pit_snapshot_id=(getattr(result_row, "pit_snapshot_id", "") or ""),
                    recommendation_id=(getattr(result_row, "recommendation_id", "") or ""),
                    decision_timestamp=result_row.candle_time,
                    feature_version="3.0.0",
                    # اختراق يُدخل فوراً بالإغلاق — لا انتظار ارتداد،
                    # ووقت الدخول وقت تلك الشمعة لا لحظة المسح
                    status=OPEN, signal_at=now,
                    candle_time=result_row.candle_time,
                    opened_at=result_row.candle_time, entry_price=plan.entry,
                ),
            )
    except IntegrityError:
        return None
    return trade if created else None


# ───────────────────────────────────────────── الحسم

def _bars_after(candles, candle_time) -> list[dict]:
    """الشموع التي تلي شمعة الإشارة — هي وحدها ما يحسم الصفقة.

    إدخال شمعة الإشارة نفسها يعني حسم الصفقة بحركة سبقت اتخاذ القرار،
    وهي إعادة الرسم بعينها في ثوب آخر.
    """
    out = []
    for c in candles or []:
        ts = c.get("time") or c.get("open_time")
        if ts is None:
            continue
        try:
            if ts <= candle_time:
                continue
        except TypeError:
            continue
        out.append(c)
    return out


def _bar_time(bars, index):
    """وقت الشمعة رقم ``index`` — أو None إن خرج عن المدى."""
    if index is None:
        return None
    try:
        value = bars[int(index)].get("time")
    except (IndexError, TypeError, ValueError, AttributeError):
        return None
    return value


def resolve_with_candles(trade: Trade, candles) -> bool:
    """يحسم صفقة واحدة من شموع. يعيد True إن تغيّرت حالتها."""
    bars = _bars_after(candles, trade.candle_time)
    if not bars:
        return False

    plan = Plan(side=trade.side, entry=trade.entry, stop=trade.stop,
                target=trade.target1)
    deadline = ENTRY_DEADLINE_BARS.get(trade.timeframe, 30)
    res = resolve(bars, plan,
                  already_entered=trade.status == OPEN,
                  entry_price=trade.entry_price,
                  max_bars=deadline)

    before = trade.status
    fields: list[str] = []

    def put(name, value):
        if getattr(trade, name) != value:
            setattr(trade, name, value)
            fields.append(name)

    put("status", res.status)
    put("bars_held", res.bars_held)
    put("resolution_note", res.note[:120])
    if res.entry_price is not None:
        put("entry_price", round(res.entry_price, 10))
    if res.r_multiple is not None:
        put("r_multiple", res.r_multiple)
    if res.excursion:
        put("best_r", res.excursion.get("best_r"))
        put("worst_r", res.excursion.get("worst_r"))

    # وقت السوق لا وقت المعالجة.
    #
    # كانت هذه الحقول تُكتب بـ timezone.now() أي لحظة تشغيل الحسم، فصفقة
    # نُفّذت قبل ثلاثة أيام وحُسمت الآن تُسجَّل كأنها فُتحت وأُغلقت في
    # اللحظة نفسها. النتيجة: «مدة الاحتفاظ» صفر دائماً، وترتيب الصفقات
    # زمنياً يعكس ترتيب المعالجة لا ترتيب السوق — وكلاهما يفسد أي تحليل
    # زمني لاحق. محرّك الحسم يعرف رقم شمعة الدخول والخروج، فنأخذ وقتها.
    entered_at = _bar_time(bars, res.entry_bar)
    exited_at = _bar_time(bars, res.exit_bar)
    now = timezone.now()

    if res.status in (WON, LOST):
        put("exit_price", round(res.exit_price, 10) if res.exit_price else None)
        if trade.closed_at is None:
            put("closed_at", exited_at or now)
        if trade.opened_at is None:
            put("opened_at", entered_at or now)
        # حارس أخير: خروج قبل دخول مستحيل. يحدث حين يختلط مصدر الوقت
        # (صفٌّ قديم فُتح بوقت معالجة ثم حُسم بوقت شمعة)، ونتيجته مدة
        # سالبة تظهر «—» بلا تفسير. نصحّحها لوقت الشمعة الصحيح.
        if (trade.opened_at and trade.closed_at
                and trade.opened_at > trade.closed_at):
            put("opened_at", entered_at or trade.closed_at)
    elif res.status == OPEN and trade.opened_at is None:
        put("opened_at", entered_at or now)

    # صفقة مفتوحة تجاوزت أقصى مدة: تُغلق بسعر السوق بدل أن تبقى معلّقة
    if res.status == OPEN:
        cap = MAX_HOLD_BARS.get(trade.timeframe, 100)
        if res.bars_held > cap:
            last = float(bars[-1]["close"])
            risk = abs((res.entry_price or trade.entry) - trade.stop)
            sign = 1 if trade.side == "buy" else -1
            r = ((last - (res.entry_price or trade.entry)) / risk * sign
                 if risk else 0.0)
            put("status", WON if r > 0 else LOST)
            put("exit_price", last)
            put("r_multiple", round(r, 3))
            put("closed_at", _bar_time(bars, len(bars) - 1) or now)
            put("resolution_note", f"أُغلقت بالسوق بعد {cap} شمعة بلا حسم")

    put("checked_at", timezone.now())
    if fields:
        trade.save(update_fields=list(dict.fromkeys(fields)))
    settled = trade.status != before
    if settled and trade.status in (WON, LOST):
        try:
            from scanner.ai_advisor.production_hooks import on_trade_settled
            on_trade_settled(trade)
        except Exception as exc:  # noqa: BLE001
            log.debug("advisor post-settle hook: %s", str(exc)[:120])
    return settled


def live_symbols(market: str, timeframe: str) -> set[str]:
    """رموز لها صفقة حيّة — لنحتفظ بشموعها وحدها أثناء المسح.

    الاحتفاظ بشموع كل الرموز يعني مئات الجداول في الذاكرة بلا داعٍ؛
    الصفقات الحيّة عادةً عشرات على الأكثر.
    """
    try:
        return set(Trade.objects.filter(
            market=market, timeframe=timeframe, status__in=[PENDING, OPEN]
        ).values_list("symbol", flat=True))
    except (OperationalError, ProgrammingError):
        return set()


def candles_from_frame(df) -> list[dict]:
    """DataFrame المسح ← شموع يفهمها المحرّك، بأقل نسخ ممكن."""
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    cols = ("open", "high", "low", "close")
    if not all(c in df.columns for c in cols):
        return []
    for ts, row in zip(df.index, df[list(cols)].to_numpy()):
        out.append({"time": ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts,
                    "open": float(row[0]), "high": float(row[1]),
                    "low": float(row[2]), "close": float(row[3])})
    return out


def resolve_market(market: str, timeframe: str, candles_by_symbol: dict) -> dict:
    """يحسم كل صفقات (سوق، فريم) من شموع المسح — بلا أي طلب شبكة إضافي."""
    try:
        live = list(Trade.objects.filter(market=market, timeframe=timeframe,
                                         status__in=[PENDING, OPEN]))
    except (OperationalError, ProgrammingError):
        log.warning("جدول الصفقات غير موجود — شغّل migrate")
        return {"checked": 0, "changed": 0, "error": "migrate"}

    changed = 0
    for trade in live:
        candles = candles_by_symbol.get(trade.symbol)
        if not candles:
            continue
        try:
            if resolve_with_candles(trade, candles):
                changed += 1
        except DatabaseError:
            raise
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر حسم صفقة %s: %s", trade.symbol, str(exc)[:120])
    return {"checked": len(live), "changed": changed}


def expire_stale() -> int:
    """الخطط التي انقضت مهلة دخولها ولم تُفعَّل."""
    try:
        return Trade.objects.filter(
            status=PENDING, expires_at__lte=timezone.now()
        ).update(status=EXPIRED, resolution_note="انقضت مهلة الدخول")
    except (OperationalError, ProgrammingError):
        return 0


# مضاعف فوق أقصى مدة احتفاظ مشروعة. الصفقة على 4h قد تبقى مئة شمعة
# بحكم MAX_HOLD_BARS، فثلاثة أضعافها تعني شهوراً — لا تبلغها إلا
# بيانات ميتة.
STALE_MULTIPLE = 3

# أقصى نسبة من الصفقات الحيّة يُسمح لدورة واحدة بإلغائها. فوقها يُرفض
# الإلغاء كله ويُسجَّل تحذير.
#
# هذا المكبح ليس احتياطاً نظرياً: أول صياغة لهذه الدالة استعملت عتبة
# ثابتة (عشر شموع) فألغت 91 صفقة سليمة في دورة واحدة على قاعدة حيّة،
# بينها خمس رابحة بلغت هدفها. أسقطت الاختبارات العتبة بعد ذلك، لكن
# الضرر كان قد وقع — لأن لا شيء كان يسأل: «إلغاء نصف السجلّ دفعةً،
# أهذا معقول؟»
#
# الدرس أعمّ من هذه الدالة: أي تغيير حالة جماعي يقوده ثابت رقمي يجب
# أن يكون له سقف. الخطأ في الثابت لا يظهر في المراجعة ولا في نوع
# البيانات — يظهر في **الحجم**.
MAX_CANCEL_RATIO = 0.25
MIN_CANCEL_FLOOR = 20        # دونه لا معنى للنسبة (سجلّ صغير)


def cancel_stale_candles(multiple: int = STALE_MULTIPLE) -> int:
    """يلغي الصفقات المبنية على شمعة ميتة — رموز توقّف تداولها.

    كيف نشأت: ملف الشموع يبقى على القرص بعد شطب الرمز من المنصّة،
    والجلب التراكمي يطلب الناقص فلا يعود بشيء، فيقرأ المحلّل شمعة من
    2022 على أنها الأحدث ويصدر توصية بسعرها. وُجد سبعة وخمسون صفّاً
    كهذا من 2022 إلى 2025.

    ولماذا لا يكفي ``expire_stale``: مهلته تُحسب من **لحظة الفتح** لا
    من وقت الشمعة، فصفقة فُتحت اليوم على شمعة 2022 تبدو طازجة ليومين.
    والتمييز مهم في السجلّ: هذه بيانات معطوبة، وتلك سعر لم يبلغ الدخول.

    وأمّا العتبة فكانت عشر شموع في أول كتابة، وأسقطتها اختبارات الحسم
    فوراً — وكانت محقّة. الصفقة **المفتوحة** تشيخ بطبيعتها: صفقة 4h
    تبقى مئة شمعة بحكم ``MAX_HOLD_BARS``، وعشر شموع كانت تلغيها وهي
    سليمة تماماً. الخطأ أن المقياس خلط بين قِدم الصفقة وقِدم البيانات،
    وهما شيئان مختلفان.

    فالعتبة الآن مشتقّة من أقصى مدة مشروعة لكل فريم مضروبة في
    ``multiple``: ما تجاوزها لا يمكن أن يكون صفقة حيّة، لأن ``MAX_HOLD``
    كان سيغلقها قبل ذلك بكثير. والفلترة الحقيقية في أمر المسح قبل
    التحليل أصلاً؛ هذه لتنظيف ما سبقها.
    """
    from scanner.live import timeframe_seconds

    now = timezone.now()
    cancelled = 0
    try:
        live = list(Trade.objects.filter(status__in=[PENDING, OPEN]))
    except (OperationalError, ProgrammingError):
        return 0

    # المرور الأول يختار بلا كتابة — الحكم على الحجم قبل تنفيذه
    doomed: list[tuple] = []
    for trade in live:
        if not trade.candle_time:
            continue
        try:
            seconds = timeframe_seconds(trade.timeframe)
        except Exception:  # noqa: BLE001
            continue
        if not seconds:
            continue
        limit = MAX_HOLD_BARS.get(trade.timeframe, 100) * max(1, multiple)
        behind = (now - trade.candle_time).total_seconds() / seconds
        if behind > limit:
            doomed.append((trade, behind))

    if (len(live) >= MIN_CANCEL_FLOOR
            and len(doomed) > len(live) * MAX_CANCEL_RATIO):
        log.error(
            "رُفض إلغاء %s من %s صفقة حيّة (%.0f%%) — تجاوز سقف %.0f%%. "
            "نسبة كهذه تعني عتبة خاطئة لا سوقاً ميتاً؛ راجع "
            "STALE_MULTIPLE قبل تعطيل المكبح.",
            len(doomed), len(live), len(doomed) / len(live) * 100,
            MAX_CANCEL_RATIO * 100)
        return 0

    for trade, behind in doomed:
        trade.status = EXPIRED
        trade.resolution_note = (
            f"بيانات قديمة — شمعة الإشارة متأخرة {behind:.0f} شمعة "
            f"(الرمز متوقّف التداول غالباً)")
        try:
            trade.save(update_fields=["status", "resolution_note"])
            cancelled += 1
        except DatabaseError:
            continue
    return cancelled


def touch_prices(prices: dict) -> int:
    """تحديث آخر سعر للصفقات الحيّة — للعرض فقط لا للحسم.

    الحسم من الشموع حصراً: عيّنة كل خمس دقائق تُفوّت الفتيل الذي يلمس
    الوقف ثم يرتدّ، فتُسجَّل خسارة حقيقية ربحاً.
    """
    try:
        live = list(Trade.objects.filter(status__in=[PENDING, OPEN]))
    except (OperationalError, ProgrammingError):
        return 0
    now = timezone.now()
    hit = 0
    for trade in live:
        price = prices.get((trade.market, trade.symbol))
        if price is None:
            continue
        trade.last_price = price
        trade.checked_at = now
        trade.save(update_fields=["last_price", "checked_at"])
        hit += 1
    return hit


# ───────────────────────────────────────────── التقارير

def rows_for_stats(queryset) -> list[dict]:
    """تحويل صفوف قاعدة البيانات إلى ما يفهمه ``scanner.tracking``."""
    return [{
        "status": t.status, "r_multiple": t.r_multiple,
        "grade": t.grade, "timeframe": t.timeframe, "market": t.market,
        "factors": [FACTOR_LABELS.get(f, f) for f in (t.factors or [])],
        "symbol": t.symbol,
        "closed_at": getattr(t, "closed_at", None),
        "signal_at": getattr(t, "signal_at", None),
    } for t in queryset]
