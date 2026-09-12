# -*- coding: utf-8 -*-
"""سجلّ رصد ‏PES: متى رُصد، وماذا جرى بعده.

═══ السؤال الذي يجيب عنه ═══

«هل هذه العملية فعّالة؟» — ولا يُجاب إلّا بتسجيل ما قيل **قبل**
أن يُعرَف الجواب، ثمّ قياس ما جرى.

والذاكرة البشرية لا تصلح لهذا: يُتذكَّر الرمز الذي انفجر بعد
الرصد، ويُنسى العشرون التي لم تتحرّك. فالسجلّ مكتوبٌ لا مُستذكَر.

═══ ولماذا يُحفظ المسار لا الحكم ═══

«انفجرت» كلمةٌ بلا معنى حتى تُحدَّد عتبتها. وعتبةٌ مخبوزة في الكود
تعني أنّ تغيير رأيك من ‎+8٪‎ إلى ‎+12٪‎ يُبطل كل ما جُمع.

فيُحفظ لكل رصد: أقصى ارتفاع ومتى بلغه، وأقصى تراجع، وهل عُبِرت
المقاومة، وهل تمدّد التقلّب. والعتبة مرشِّحٌ في الشاشة.

═══ ومنع النظر إلى المستقبل ═══

المتابعة تقرأ الشموع **بعد** ``candle_time`` حصراً. وشمعةُ الرصد
نفسها مستبعَدة: كانت جارية لحظة القرار.

وهذا ليس احتياطاً نظرياً — تسريبٌ بشمعةٍ واحدة يرفع أيّ نسبة
نجاح رفعاً يجعل النظام يبدو ممتازاً وهو لا يعمل.
"""
from __future__ import annotations

import logging
import time

log = logging.getLogger("dashboard.pes_history")

# ═══ مدى المتابعة ═══
#
# ‏PES مبنيّة على 4H، و١٤ يوماً ≈ ٨٤ شمعة — متّسعٌ لدورة تجميعٍ ثمّ
# تمدّد، وليس طويلاً فيُنسَب إلى الإشارة ما لا علاقة له بها.
HORIZON_DAYS = 14

# لا يُسجَّل ما لا إشارة له. و«انفجرت بالفعل» و«زخم متأخّر»
# **تُسجَّلان**: معرفة أنّ المرفوض كان يرتفع فعلاً تقول إنّ الرفض
# مخطئ — ولا يُعرف ذلك إلّا بتسجيله.
TRACKED_STATES = (
    "WATCH", "EARLY_MOMENTUM", "PRE_BREAKOUT", "STRONG_PRE_BREAKOUT",
    "BREAKOUT", "BREAKOUT_RETEST", "ENTRY_READY",
    "LATE_MOMENTUM", "ALREADY_EXPANDED",
)

# ═══ تمدّد التقلّب ═══
#
# الاستراتيجية تسمّي نفسها «ما قبل الانفجار»، والانفجار في أصله
# تمدّدُ تقلّب لا ارتفاع سعر. فيُقاس: هل خرج عرض بولنجر من
# انضغاطه؟
EXPANSION_RATIO = 2.0


def _parse_dt(value):
    """نصّ ‏ISO أو كائن وقت → وقتٌ واعٍ بمنطقته، أو ``None``.

    المسح يحفظ مخرَجه في ‏JSON، فالوقت يعود نصّاً. وتمريرُه كما هو
    إلى ``get_or_create`` يعمل على SQLite ويسقط على PostgreSQL —
    عطبٌ لا يظهر إلّا بعد الترحيل.
    """
    if value in (None, ""):
        return None
    try:
        import pandas as pd

        out = pd.Timestamp(value)
        if out.tzinfo is None:
            out = out.tz_localize("UTC")
        return out.to_pydatetime()
    except Exception:  # noqa: BLE001
        return None


def _tz_aware(ts):
    """يوحّد المنطقة الزمنية قبل أيّ مقارنة.

    ‏Django يخزّن بـ UTC، والشموع تحمل منطقتها. ومقارنة واعٍ بغير
    واعٍ ترمي ``TypeError`` في منتصف المتابعة — فتتوقّف الدورة عند
    أوّل رمزٍ ولا يُعرف السبب.
    """
    import pandas as pd

    out = pd.Timestamp(ts)
    return out.tz_localize("UTC") if out.tzinfo is None else out


# ═══════════════════ ١) التسجيل ═══════════════════

def record(rows: list[dict], market: str) -> int:
    """يسجّل الرصد الجديد من مخرَج المسح — ويعيد كم صفّاً أُضيف.

    ═══ التسجيل عند دخول الحالة لا في كل دورة ═══

    المسح يعمل كل ربع ساعة. ورمزٌ يبقى ‏PRE_BREAKOUT ثلاثة أيّام
    يُنتج ٢٨٨ صفّاً لو سُجّل كلّ مرّة — فتغرق أيّ إحصاءٍ في تكرار
    الحالة الواحدة، وتصير «نسبة النجاح» نسبةَ الرموز البطيئة.

    والمفتاح ``(رمز، سوق، حالة، شمعة)`` يمنع ذلك، ويمنعه القيد في
    القاعدة أيضاً — حزامان لأنّ ماسحين قد يعملان معاً.
    """
    from django.utils import timezone

    from .models import PesDetection

    now = timezone.now()

    # ═══ الموجود يُقرأ مرّة، ثمّ يُكتب الجديد دفعةً ═══
    #
    # كانت النسخة الأولى تنادي ``get_or_create`` لكل صفّ — أي
    # استعلامٌ ومعاملةُ كتابةٍ لكل رمز، ثلاث مرّاتٍ في كل دورة مسح.
    # وعلى ‏SQLite (كاتبٌ واحد) صار ذلك مئات الأقفال المتتابعة على
    # قاعدةٍ يكتب فيها المسح والحسم والمزامنة معاً.
    #
    # فالقراءة استعلامٌ واحد، والكتابة معاملةٌ واحدة.
    fresh: list = []
    seen: set = set()
    for r in rows or []:
        state = str(r.get("state") or "")
        if state not in TRACKED_STATES:
            continue

        ct = _parse_dt(r.get("candle_time"))
        if ct is None:
            # بلا شمعةٍ لا يُقاس المسار ولا يُمنع التكرار. والصفّ
            # بلا مرجعٍ زمني أسوأ من غيابه: يدخل الإحصاء ولا يُقاس.
            continue

        # ═══ سعرُ شمعة القرار لا السعر الحيّ ═══
        #
        # ``close`` هو إغلاق الشمعة **الجارية** لحظة المسح — وقد
        # تحرّك بالفعل عن الموضع الذي بُني عليه القرار. وقياس
        # الارتفاع منه يخصم من النتيجة حركةً سبقت الرصد، أو
        # يضيفها إليه.
        price = r.get("decision_close") or r.get("close")
        if not price:
            continue

        sym = str(r.get("symbol") or "")
        key = (sym, state, ct)
        if key in seen:          # الرمز نفسه مرّتين في مخرَجٍ واحد
            continue
        seen.add(key)

        mom = r.get("momentum") or {}
        fresh.append(PesDetection(
            symbol=sym, market=market, state=state, candle_time=ct,
            state_label=str(r.get("state_label") or "")[:40],
            detected_at=now,
            price=float(price),
            score=float(r.get("score") or 0),
            confidence=float(r.get("confidence") or 1),
            family_count=int(r.get("family_count") or 0),
            momentum_score=float(mom.get("score") or 0),
            momentum_label=str(mom.get("label") or "")[:80],
            resistance=r.get("resistance"),
            distance_pct=r.get("distance"),
            btc_label=str((r.get("btc") or {}).get("label") or "")[:16],
            reasons=str(r.get("why") or "")[:300],
        ))

    if not fresh:
        return 0

    # ═══ الموجود يُستبعَد قبل الكتابة ═══
    #
    # ‏``ignore_conflicts`` وحده كان يكفي، لكنّه لا يعيد عدد ما
    # أُضيف فعلاً — فيقول السجلّ «رُصد 300» في كل دورة وهي كلّها
    # مكرَّرة. والاستعلام هنا واحد، ويجعل الرقم صادقاً.
    times = {d.candle_time for d in fresh}
    have = set(PesDetection.objects
               .filter(market=market, candle_time__in=times)
               .values_list("symbol", "state", "candle_time"))
    new = [d for d in fresh
           if (d.symbol, d.state, d.candle_time) not in have]
    if not new:
        return 0

    try:
        from django.db import transaction

        with transaction.atomic():
            # ‏ignore_conflicts حزامٌ ثانٍ: ماسحان في اللحظة نفسها
            # قد يمرّان من الفحص أعلاه معاً، والقيد الفريد يحسمها
            # بلا استثناء.
            PesDetection.objects.bulk_create(new, ignore_conflicts=True)
    except Exception as exc:  # noqa: BLE001
        # التسجيل توثيقٌ لا شرط عمل: فشلُه لا يُسقط المسح
        log.warning("تعذّر تسجيل %d رصداً لـ %s: %s",
                    len(new), market, str(exc)[:120])
        return 0
    return len(new)


# ═══════════════════ ٢) المتابعة ═══════════════════

def _walk_forward(df, det) -> dict:
    """يقيس المسار من الشموع **بعد** لحظة الرصد وحدها.

    ولا يُستعمل ``iloc`` بفهرسٍ محسوب: القصّ بالزمن صريحٌ ويبقى
    صحيحاً ولو تغيّر عدد الشموع المخزَّنة أو ظهرت فجوة.
    """
    import numpy as np

    cut = _tz_aware(det.candle_time)
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    after = df[idx > cut]                 # ‏> لا ‎>=‎: شمعة الرصد جارية
    if after.empty:
        return {"bars": 0}

    horizon_end = cut + __import__("pandas").Timedelta(days=HORIZON_DAYS)
    aidx = after.index
    if aidx.tz is None:
        aidx = aidx.tz_localize("UTC")
    window = after[aidx <= horizon_end]
    if window.empty:
        return {"bars": 0}

    base = float(det.price)
    if base <= 0:
        return {"bars": 0}

    high = window["high"].astype(float)
    low = window["low"].astype(float)
    close = window["close"].astype(float)

    gains = (high - base) / base * 100.0
    top_i = int(np.argmax(gains.to_numpy()))
    max_gain = float(gains.iloc[top_i])
    top_at = window.index[top_i]

    # ═══ التراجع يُقاس قبل القمّة لا بعدها ═══
    #
    # ارتفاعٌ ‎+20٪‎ سبقه نزولٌ ‎-15٪‎ لا يُدرَك عملياً: الوقف يضربك
    # قبله. فالرقم المفيد هو أسوأ ما مرّ **قبل** بلوغ القمّة.
    before_top = low.iloc[:top_i + 1]
    dd = float(((before_top.min() - base) / base * 100.0)
               if len(before_top) else 0.0)

    broke, broke_at = False, None
    level = det.resistance
    if level:
        above = close[close > float(level)]
        if len(above):
            broke, broke_at = True, above.index[0]

    expanded = False
    try:
        from scanner.indicators.squeeze import bb_width

        # عرض القناة عند الرصد مقابل أوسع ما بلغه بعده
        pre = df[idx <= cut]
        if len(pre) >= 40:
            w0 = float(bb_width(pre).iloc[-1])
            w1 = float(bb_width(df[idx <= (aidx.max())]).iloc[-len(window):]
                       .max())
            expanded = bool(w0 > 0 and w1 / w0 >= EXPANSION_RATIO)
    except Exception:  # noqa: BLE001
        # مقياسٌ إضافي: تعذّره لا يُبطل المتابعة
        pass

    hours = (_tz_aware(top_at) - cut).total_seconds() / 3600.0
    return {
        "bars": len(window),
        "max_gain": round(max_gain, 2),
        "max_gain_at": top_at.to_pydatetime(),
        "hours_to_max": round(hours, 1),
        "drawdown": round(dd, 2),
        "broke": broke,
        "broke_at": broke_at.to_pydatetime() if broke_at is not None else None,
        "expanded": expanded,
        "last_bar": window.index[-1],
    }


# ═══ حدّان يمنعان هذه الدالّة من احتكار القاعدة ═══
#
# ‏SQLite يسمح بكاتبٍ واحد. وأوّل نسخةٍ من هذه الدالّة كانت تنادي
# ``det.save()`` لكل صفّ — أي **معاملة كتابةٍ مستقلّة** لكل رصد.
# فلمّا بلغ السجلّ ٦٥٩ صفّاً صار كل تشغيلٍ ٦٥٩ قفلاً متتابعاً على
# قاعدةٍ يكتب فيها المسحُ والحسمُ والمزامنة في الوقت نفسه.
#
# والنتيجة المقيسة: «القاعدة مقفلة» على أربع مهامّ دفعةً واحدة.
#
# فالكتابة صارت دفعاتٍ بـ ``bulk_update``: قفلٌ واحد لكل مئتي صفّ
# بدل مئتي قفل. والسقف يمنع الدالّة من التمدّد بلا حدّ كلّما كبر
# السجلّ — فما لا يُتابَع اليوم يُتابَع في الدورة التالية.
BATCH = 200
MAX_PER_RUN = 400

_TRACK_FIELDS = ["bars_seen", "max_gain_pct", "max_gain_at", "hours_to_max",
                 "max_drawdown_pct", "broke_resistance", "broke_at",
                 "volatility_expanded", "outcome", "settled_at", "note"]


def follow_up(limit: int = 0) -> dict:
    """يحدّث مسار كل رصدٍ قيد المتابعة، ويُغلق ما اكتمل مداه.

    الكتابة دفعاتٍ لا صفّاً صفّاً — انظر ``BATCH`` أعلاه.
    """
    from datetime import timedelta

    import pandas as pd
    from django.db import transaction
    from django.utils import timezone

    from scanner import storage

    from .models import PesDetection

    now = timezone.now()
    cap = limit or MAX_PER_RUN
    # ═══ الأقدم أوّلاً ═══
    #
    # ``order_by("id")`` يعني أنّ الرصد القديم يُتابَع قبل الجديد —
    # وهو الصواب: القديم أقرب إلى اكتمال مداه. ولو رُتّب عكسياً
    # لبقيت أقدم الصفوف بلا متابعةٍ أبداً كلّما امتلأ السجلّ.
    pending = list(PesDetection.objects.filter(outcome="watching")
                   .order_by("id")[:cap])

    cache: dict[tuple, object] = {}
    stats = {"updated": 0, "settled": 0, "no_data": 0,
             "seen": 0, "pending": 0}
    dirty: list = []

    def _flush():
        """يكتب ما تجمّع في معاملةٍ واحدة — ولا يرمي."""
        if not dirty:
            return
        from django.db import OperationalError

        for attempt in range(3):
            try:
                with transaction.atomic():
                    PesDetection.objects.bulk_update(dirty, _TRACK_FIELDS)
                dirty.clear()
                return
            except OperationalError as exc:
                if "locked" not in str(exc).lower() or attempt == 2:
                    # الفشل هنا لا يُسقط المهمّة: المتابعة توثيقٌ
                    # يُستدرَك في الدورة التالية، والرصد نفسه محفوظ.
                    log.warning("تعذّر حفظ %d مسار: %s",
                                len(dirty), str(exc)[:120])
                    dirty.clear()
                    return
                time.sleep(1.5 * (attempt + 1))

    for det in pending:
        stats["seen"] += 1
        key = (det.market, det.symbol)
        if key not in cache:
            try:
                cache[key] = storage.load(det.market, det.symbol, "4h")
            except Exception:  # noqa: BLE001
                cache[key] = None
        df = cache[key]

        done = now >= _tz_aware(det.candle_time).to_pydatetime() + timedelta(
            days=HORIZON_DAYS)

        if df is None or len(df) < 5:
            if done:
                det.outcome = "no_data"
                det.settled_at = now
                det.note = "لا شموع للمتابعة"
                dirty.append(det)
                stats["no_data"] += 1
                if len(dirty) >= BATCH:
                    _flush()
            continue

        try:
            path = _walk_forward(df, det)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّرت متابعة %s: %s", det.symbol, str(exc)[:120])
            continue

        if not path.get("bars"):
            if done:
                det.outcome = "no_data"
                det.settled_at = now
                det.note = "لا شموع بعد لحظة الرصد"
                dirty.append(det)
                stats["no_data"] += 1
                if len(dirty) >= BATCH:
                    _flush()
            continue

        det.bars_seen = path["bars"]
        det.max_gain_pct = path["max_gain"]
        det.max_gain_at = path["max_gain_at"]
        det.hours_to_max = path["hours_to_max"]
        det.max_drawdown_pct = path["drawdown"]
        det.broke_resistance = path["broke"]
        det.broke_at = path["broke_at"]
        det.volatility_expanded = path["expanded"]

        # ═══ لا يُغلق إلّا بشمعةٍ تتجاوز المدى ═══
        #
        # مرور الزمن وحده لا يكفي: قد تكون الشموع لم تُزامَن بعد،
        # فيُغلق الرصد على مسارٍ ناقص ويُحسب «لم ينفجر» وهو لم
        # يُقَس أصلاً.
        last = _tz_aware(path["last_bar"])
        reached = last >= _tz_aware(det.candle_time) + pd.Timedelta(
            days=HORIZON_DAYS)
        if done and reached:
            det.outcome = "settled"
            det.settled_at = now
            stats["settled"] += 1

        dirty.append(det)
        stats["updated"] += 1
        if len(dirty) >= BATCH:
            _flush()

    _flush()
    stats["pending"] = max(
        0, PesDetection.objects.filter(outcome="watching").count()
        - stats["seen"])
    return stats


# ═══════════════════ ٣) الإحصاء ═══════════════════

def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """فترة ثقة للنسبة — ‏Wilson لا ‏Wald.

    عند ٣ رصداتٍ ونسبة ١٠٠٪ تعطي ‏Wald فترةً عرضها صفر: «يقينٌ»
    من ثلاث ملاحظات. وأوّل ما يُجمع هنا سيكون عيّناتٍ صغيرة، فهذا
    ليس تفصيلاً بل شرطُ ألّا يُقرأ الضجيج نتيجة.
    """
    import math

    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - m), min(1.0, c + m))


def summarize(rows: list, threshold: float) -> dict:
    """يلخّص قائمة رصداتٍ عند عتبةٍ يختارها المستخدم.

    ``threshold`` نسبةُ الارتفاع التي تُسمّى «انفجاراً». وهي وسيطٌ
    لا ثابت: يحرّكها المستخدم فتتغيّر النسبة أمامه، ويرى بنفسه
    هل الإشارة تصمد عند حدٍّ أعلى.
    """
    # المكتمل وحده يدخل النسبة. والرصد الجاري ليس فشلاً — هو
    # **لم يُقَس بعد**، وعدُّه فشلاً يخفض كل نسبةٍ بمقدار ما هو
    # حديث، فتبدو الاستراتيجية تسوء كلّما مسحتَ أكثر.
    done = [r for r in rows if r.outcome == "settled"]
    hit = [r for r in done
           if r.max_gain_pct is not None and r.max_gain_pct >= threshold]
    n, w = len(done), len(hit)
    lo, hi = wilson(w, n)

    gains = sorted(r.max_gain_pct for r in done if r.max_gain_pct is not None)
    hours = sorted(r.hours_to_max for r in hit if r.hours_to_max is not None)
    dds = sorted(r.max_drawdown_pct for r in done
                 if r.max_drawdown_pct is not None)

    def med(xs):
        return round(xs[len(xs) // 2], 2) if xs else None

    return {
        "total": len(rows),
        "settled": n,
        "watching": sum(1 for r in rows if r.outcome == "watching"),
        "no_data": sum(1 for r in rows if r.outcome == "no_data"),
        "hits": w,
        "rate": round(w / n * 100, 1) if n else None,
        "ci_low": round(lo * 100, 1), "ci_high": round(hi * 100, 1),
        "median_gain": med(gains),
        "median_hours_to_hit": med(hours),
        "median_drawdown": med(dds),
        "broke_resistance": sum(1 for r in done if r.broke_resistance),
        "expanded": sum(1 for r in done if r.volatility_expanded),
        # عيّنةٌ دون هذا لا تُقرأ نتيجة — وتُعلَن كذلك في الشاشة
        "thin": n < 20,
    }


__all__ = ["record", "follow_up", "summarize", "wilson",
           "HORIZON_DAYS", "TRACKED_STATES"]
