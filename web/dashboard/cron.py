# -*- coding: utf-8 -*-
"""محرّك الجدولة — على غرار ``ir.cron`` في أودو.

═══ ما استُبدل ═══

كانت أربع حلقات مستقلّة، كلٌّ خيطٌ بحالته في الذاكرة وفترته في
متغيّر بيئة::

    scheduler          مسح تلقائي        AUTO_SCAN_MARKETS
    market_sync_worker مزامنة الشموع     MARKET_SYNC_MARKETS
    monitor            مراقبة الفرص      WATCH_INTERVAL_SECONDS
    settlement         حسم الصفقات       SETTLEMENT_INTERVAL_SECONDS

فمعرفة «متى مُسح السعودي آخر مرّة» تحتاج قراءة سجلّات، وتغيير فترة
يحتاج تحرير ملفّ وإعادة تشغيل، وكل شيء يُمحى عند إعادة التشغيل.

والمنطق نفسه لم يُمسّ: هذه الوحدة **تنادي** ``run_scan`` و
``run_once`` و``check_once`` و``settle_once`` كما هي. المتغيّر هو
من يقرّر متى — وأين يُسجَّل ما جرى.

═══ ولماذا خيطٌ لكل مهمّة لا طابور واحد ═══

أودو يشغّل المهامّ بالتتابع. وهنا لا يصلح: المزامنة قد تستغرق
دقائق، والمراقبة يجب أن تعمل كل خمس دقائق لتلتقط بلوغ سعر الدخول.
فطابورٌ واحد يجعل مزامنةً بطيئة تؤخّر تنبيهاً — وهو تراجعٌ عن
السلوك القائم اليوم (أربعة خيوط مستقلّة).

فالحلقة هنا **موزِّعة** لا منفِّذة: تلتقط المستحقّ وتطلقه في خيطه،
وقفلٌ لكل مهمّة يمنع تداخل دورتين من **نفسها**.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import timedelta

log = logging.getLogger("dashboard.cron")

# نبضة الموزِّع — كل كم ثانية يُسأل عن المستحقّ.
# خمس عشرة ثانية: دقّةٌ كافية لأقصر فترة معقولة (دقيقة)، وحملٌ
# مهمَل على القاعدة (استعلامٌ واحد مفهرَس).
TICK_SECONDS = 15

# سقف سجلّ التشغيل لكل مهمّة — ‏events.jsonl بلغ ٣٠٥ ميغابايت بلا
# حدّ، فصارت قراءة سطرٍ منه تكلّف ثوانٍ. الحدّ يُفرض عند الكتابة.
MAX_RUNS_PER_JOB = 200

# ═══ مهلة إعادة المحاولة بعد التخطّي ═══
#
# قِيس على الشاشة: ``market_sync`` بلغت ١٥ «تشغيلة» بينما جاراتها
# ٢–٤. السبب أنّ التخطّي لم يكن يقدّم الموعد — فالمهمّة تبقى
# مستحقّة، وتُجرَّب في **كل نبضة** (أربع مرّات في الدقيقة) طوال
# الدورة الطويلة. فيمتلئ السجلّ وتنتفخ العدّادات بلا عملٍ جرى.
#
# فالتخطّي يؤجّل — أقصر من الفترة كي لا تضيع دورة، وأطول من
# النبضة كي لا يدور.
RETRY_AFTER_SKIP = 90

_state = {"thread_started": False, "last_tick": None, "ticks": 0}


class JobBusy(RuntimeError):
    """المورد مشغولٌ بدورةٍ سابقة — ازدحامٌ لا فشل.

    ثلاث مهامّ مسحٍ (crypto · us · saudi) تتشارك قفلاً واحداً في
    ``scheduler``. فاستحقاقُها معاً يجعل اثنتين تُردّان — وهذا
    سلوكٌ صحيح لا عطب. وعرضُه «فشلت» بالأحمر يجعل المستخدم يبحث
    عن خللٍ ليس موجوداً، ويرفع عدّاد الفشل بلا فشل.
    """


_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


# ═══════════ ذاكرةٌ لما جرى فعلاً في هذه العملية ═══════════
#
# ‏``next_run`` في القاعدة هو المرجع. لكنّ تقدّمه **كتابة**، وحين
# تُقفل القاعدة تفشل — فيبقى الموعد قديماً، والمهمّة مستحقّة،
# فتُشغَّل من جديد.
#
# والكارثة أنّ عملها تمّ بالفعل: مسحٌ استغرق اثنتي عشرة دقيقة
# ينتهي، ثمّ يعجز عن تسجيل نتيجته، فيُعاد كاملاً. وإعادتُه تطيل
# احتكار القاعدة، فيفشل التسجيل مرّةً أخرى — حلقةٌ تُغذّي نفسها،
# وهي ما ظهر بـ «القاعدة مقفلة» على أربع مهامّ دفعةً واحدة.
#
# فهذه ذاكرةٌ في العملية: من شغّل مهمّةً يعرف أنّه شغّلها، سواءٌ
# استطاع كتابة ذلك أم لا. ولا تحلّ محلّ القاعدة — تحرس الفجوة
# بينها وبين الواقع حين تعجز الكتابة.
_ran_at: dict[str, float] = {}
_ran_guard = threading.Lock()


def _mark_ran(code: str) -> None:
    with _ran_guard:
        _ran_at[code] = time.time()


def _ran_recently(job) -> bool:
    """هل شُغّلت هذه المهمّة في هذه العملية قبل أن يحلّ موعدها؟"""
    with _ran_guard:
        last = _ran_at.get(job.code)
    if last is None:
        return False
    # فترة المهمّة نفسها هي الحدّ: مهمّةٌ كل ١٥ دقيقة لا تُعاد قبل
    # مضيّها. وتُقرأ من الإعداد لا تُخمَّن.
    #
    # و‎0.9‎ هامشٌ مقصود: التقدّم يُحسب من الموعد المقرَّر لا من
    # لحظة الانتهاء، فقد يحلّ الموعد التالي قبل مضيّ الفترة كاملةً
    # على ساعة الحائط. والحدّ الأدنى ثلاثون ثانية يمنع الحلقة
    # مهما قصُرت الفترة.
    try:
        step = float(job.interval_seconds)
    except Exception:  # noqa: BLE001
        step = 60.0
    return (time.time() - last) < max(30.0, step * 0.9)


# ═══════════════ قفل القاعدة ليس فشلاً في المهمّة ═══════════════
#
# ‏SQLite يسمح بكاتبٍ واحد. ومسحٌ يستغرق دقائق يحجب كل كاتبٍ آخر
# طوال مدّته، فيسقط أيّ ‎UPDATE‎ يقع في تلك النافذة بـ
# ``database is locked``.
#
# ووقع هذا فعلاً: الخادم يعمل ومحرّكه يمسح، والمستخدم يشغّل
# ``run_jobs`` من الطرفية، فينهار الأمر كلّه بأثرٍ من ثلاثين سطراً.
#
# والأسوأ أنّ ``run_job`` **يعد بألّا يرمي أبداً** — لأنّ استثناءً
# يهرب منه يقتل الموزّع فتتوقّف كل المهامّ بسبب واحدة. لكنّ
# الكتابة الأولى (‎last_status="running"‎) كانت خارج ``try``،
# فكان الوعد مكتوباً في الوثيقة ومنقوضاً في الكود.
#
# فكل كتابةٍ هنا تمرّ من هذا: تُعاد المحاولة قليلاً، ثمّ يُسجَّل
# العجز ويُمضى. وتقدّمُ الموعد وحده يفوت — فتُعاد المهمّة في
# النبضة التالية، وهو أهون من موت الموزّع.

DB_RETRIES = 3
DB_RETRY_WAIT = 1.5


def _is_locked(exc: Exception) -> bool:
    text = str(exc).lower()
    return "locked" in text or "busy" in text


def _db_write(fn, what: str) -> bool:
    """ينفّذ كتابةً ولا يرمي — يعيد نجاحها."""
    from django.db import OperationalError

    for attempt in range(1, DB_RETRIES + 1):
        try:
            fn()
            return True
        except OperationalError as exc:
            if not _is_locked(exc):
                log.warning("تعذّرت كتابة %s: %s", what, str(exc)[:160])
                return False
            if attempt == DB_RETRIES:
                log.warning(
                    "القاعدة مقفلة عند %s بعد %d محاولات — كاتبٌ آخر "
                    "يعمل (مسحٌ طويل غالباً). تُترك للنبضة التالية.",
                    what, DB_RETRIES)
                return False
            time.sleep(DB_RETRY_WAIT * attempt)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّرت كتابة %s: %s", what, str(exc)[:160])
            return False
    return False


def _lock_for(code: str) -> threading.Lock:
    with _locks_guard:
        if code not in _locks:
            _locks[code] = threading.Lock()
        return _locks[code]


def status() -> dict:
    return dict(_state)


# ═══════════════════════ المعالجات ═══════════════════════
#
# كلٌّ يعيد نصّاً قصيراً يُعرض في السجلّ. والاستيراد داخل الدالّة:
# تحميل هذه الوحدة يجب ألّا يجرّ ماسح السوق كلّه معه.

def _h_scan(payload: dict) -> str:
    """يمسح سوقاً على فريمٍ واحد أو أكثر.

    ═══ ``timeframes`` كانت قائمةً لا يُقرأ منها إلّا أوّلها ═══

    ‏``scan.py`` يأخذ ``cfg.timeframes[0]`` وحده. فمن كتب في
    ‎config/us.yaml‎ قائمةً من فريمين ظنّ أنّ الاثنين يُمسحان،
    والثاني لم يُمسّ قطّ — والشاشة تعرض فراغاً بلا سبب.

    وهذا ما وقع: السوق الأمريكي مُهيّأ على ‎1d‎ وحده، فبقي فريم
    ‎4h‎ بلا **ولا جولة مسحٍ واحدة** منذ إنشاء النظام، بينما
    شموعه تُزامَن كل عشر دقائق وتُخزَّن كاملة.

    فالقائمة تُقرأ كلّها الآن. وحمولة المهمّة تعلوها: مهمّةٌ
    بفريمٍ صريح تمسحه وحده — وهو ما يسمح بفصل الفريم الثقيل في
    مهمّةٍ ذات فترةٍ أطول بدل إثقال دورةٍ واحدة.
    """
    from django.conf import settings

    from scanner.config import load_market

    from . import scheduler

    market = str(payload.get("market") or "crypto")
    tf = payload.get("timeframe") or None

    if tf:
        frames = [tf]
    else:
        try:
            cfg = load_market(settings.SCANNER_CONFIG_DIR / f"{market}.yaml")
            frames = list(cfg.timeframes or []) or [None]
        except Exception:  # noqa: BLE001
            frames = [None]

    done, failed = [], []
    for one in frames:
        out = scheduler.run_scan(market, one)
        if out.get("busy"):
            # الازدحام يوقف البقيّة: القفل واحد، ومحاولةُ الباقي
            # تُنتج التقرير نفسه مرّاتٍ بلا عمل
            raise JobBusy(out.get("reason") or "المسح مشغول")
        if out.get("ok"):
            done.append(one or "افتراضي")
        else:
            failed.append(f"{one}: {out.get('reason', 'فشل')[:60]}")

    if not done:
        raise RuntimeError(" · ".join(failed) or "فشل المسح")
    msg = f"{market} · " + " و".join(done)
    return msg + (f" · فشل {len(failed)}" if failed else "")


def _h_market_sync(payload: dict) -> str:
    from . import market_sync_worker

    markets = payload.get("markets") or None
    out = market_sync_worker.run_once(markets) or {}
    # ‏run_once يعيد ``{ok, markets, successful, failed, elapsed_sec}``
    # أو ``{ok: False, reason}`` عند التعذّر. والرسالة تُبنى من هذه
    # المفاتيح لا من مفتاح «summary» غير موجود.
    if out.get("busy"):
        raise JobBusy(out.get("reason") or "المزامنة مشغولة")
    if not out.get("ok"):
        raise RuntimeError(out.get("reason") or "تعذّرت المزامنة")
    return (f"نجح {out.get('successful', 0)}"
            f" · فشل {out.get('failed', 0)}"
            f" · {out.get('elapsed_sec', 0)}ث")


def _h_watch_monitor(payload: dict) -> str:
    from . import monitor

    out = monitor.check_once() or {}
    # ``error: "migrate"`` تعني أنّ الجدول غير موجود — وهذا فشلٌ
    # يجب أن يظهر أحمر لا «فُحص 0» الذي يُقرأ نجاحاً بلا عمل.
    if out.get("error"):
        raise RuntimeError(str(out["error"]))
    return (f"فُحص {out.get('checked', 0)}"
            f" · تحقّق {out.get('triggered', 0)}")


def _h_settlement(payload: dict) -> str:
    from . import settlement

    out = settlement.settle_once(int(payload.get("max_symbols") or 200)) or {}
    if out.get("error"):
        raise RuntimeError(str(out["error"]))
    msg = f"فُحص {out.get('checked', 0)} · حُسم {out.get('settled', 0)}"
    if out.get("expired"):
        msg += f" · انتهت {out['expired']}"
    return msg


def _h_train(payload: dict) -> str:
    """يدرّب نموذج التنبؤ ويقيسه — ولا يرقّي إلّا إن اجتاز.

    هذه هي «يدرّب نفسه»: دورةٌ مجدولة تبني البيانات وتتعلّم منها
    وتقيس نفسها على صفقاتٍ حقيقية لم ترها. والترقية شرطُها التفوّق
    لا مرور الوقت.
    """
    from . import predictor

    data = predictor.build_datasets()
    sim, real = data["simulated"], data["real"]
    if sim["eligible_count"] < int(payload.get("min_rows") or 100):
        raise JobBusy(f"صفوف المحاكاة {sim['eligible_count']} دون الحدّ")
    out = predictor.train_and_gate(sim, real,
                                   promote=bool(payload.get("promote", True)))
    g = out["gate"]
    tail = "رُقّي" if out.get("promoted") else (
        "اجتاز بلا ترقية" if g["passed"] else g["reason"])
    return (f"محاكاة {sim['eligible_count']} · حقيقي {g['real_n']}"
            f" · محرّك {out['engine']} · {tail}")


def _h_squeeze(payload: dict) -> str:
    """يعيد قياس الانضغاط لكل سوق وفريم مطلوب.

    القياس يمرّ على مئات ملفّات الشموع، فلا يُشغَّل في طلبٍ من
    المتصفّح. ودورةٌ كل ساعتين تكفي: رتبة الانضغاط تُحسب على ١٢٠
    شمعة فلا تتغيّر بين شمعةٍ وأخرى تغيّراً يُذكر.
    """
    from scanner import squeeze_scan

    from .views import MARKETS

    markets = payload.get("markets") or list(MARKETS)
    tfs = payload.get("timeframes") or ["1h", "4h", "1d"]
    done, failed = 0, 0
    for m in markets:
        for t in tfs:
            try:
                squeeze_scan.save(squeeze_scan.build(m, t))
                done += 1
            except Exception:  # noqa: BLE001
                failed += 1
    if not done:
        raise RuntimeError("لم يكتمل أيّ قياس")
    return f"قِيس {done}" + (f" · فشل {failed}" if failed else "")


def _h_pes(payload: dict) -> str:
    """يمسح استراتيجية ما قبل الانفجار على الأسواق المطلوبة."""
    from scanner.strategies import pes_scan

    from .views import MARKETS

    from . import pes_history

    markets = payload.get("markets") or list(MARKETS)
    done, states, logged = 0, {}, 0
    for m in markets:
        try:
            out = pes_scan.scan(m)
            pes_scan.save(out)
            done += 1
            for k2, v in (out.get("by_state") or {}).items():
                if k2 != "NONE":
                    states[k2] = states.get(k2, 0) + v
            # ═══ السجلّ يُكتب هنا لا بعدُ ═══
            #
            # ملفّ المسح يُكتب فوقه في الدورة التالية، فما لم
            # يُسجَّل الآن يضيع بلا أثر. وفشلُ التسجيل لا يُسقط
            # المسح: النتائج معروضة، والسجلّ توثيقٌ يُستدرَك.
            try:
                logged += pes_history.record(out.get("rows") or [], m)
            except Exception:  # noqa: BLE001
                log.warning("تعذّر تسجيل رصد PES لـ %s", m)
        except Exception:  # noqa: BLE001
            log.warning("تعذّر مسح PES %s", m)

    # المتابعة مع المسح: الاثنان على البيانات نفسها، وفصلُهما
    # مهمّتين يضاعف قراءة ملفّات الشموع بلا فائدة.
    try:
        fu = pes_history.follow_up()
        if fu.get("settled"):
            states["اكتمل"] = fu["settled"]
    except Exception:  # noqa: BLE001
        log.warning("تعذّرت متابعة سجلّ PES")

    if logged:
        states["رُصد"] = logged
    if not done:
        raise RuntimeError("لم يكتمل أيّ مسح")
    tail = " · ".join(f"{k2} {v}" for k2, v in sorted(states.items()))
    return f"{done} سوق" + (f" · {tail}" if tail else " · لا إشارة")


def _h_paper(payload: dict) -> str:
    """دورة المحفظة الورقية: تقييمٌ ثمّ فتح."""
    from . import paper_engine

    out = paper_engine.tick()
    s = out["summary"]
    return (f"قُيّم {out['marked']} · أُغلق {len(out['closed'])}"
            f" · فُتح {len(out['opened'])}"
            f" · الرصيد {s['equity']} ({s['pnl_pct']:+}٪)")


HANDLERS = {
    "scan": _h_scan,
    "paper": _h_paper,
    "pes": _h_pes,
    "squeeze": _h_squeeze,
    "train_predictor": _h_train,
    "market_sync": _h_market_sync,
    "watch_monitor": _h_watch_monitor,
    "settlement": _h_settlement,
}

# أسماء عربية للمعالجات — تُعرض حين تُضاف مهمّة جديدة
HANDLER_LABELS = {
    "scan": "مسح السوق",
    "squeeze": "قياس الانضغاط",
    "paper": "دورة المحفظة الورقية",
    "pes": "مسح ما قبل الانفجار",
    "train_predictor": "تدريب نموذج التنبؤ",
    "market_sync": "مزامنة الشموع",
    "watch_monitor": "مراقبة الفرص",
    "settlement": "حسم الصفقات",
}


# ═══════════════════════ تقدّم الموعد ═══════════════════════

def advance(job, *, now=None):
    """الموعد القادم — بلا تراكم وبلا انجراف.

    ═══ المسألة ═══

    الخادم أُغلق يومين ومهمّةٌ فترتها خمس دقائق. فلو أُضيفت الفترة
    مرّةً واحدة لبقي الموعد في الماضي، فتُشغَّل في كل نبضة إلى أن
    تلحق — نحو **٥٧٦ تشغيلة** تعويضاً عن يومين لا يفيد منها إلّا
    الأخيرة.

    ولو حُسب من **لحظة الانتهاء** لانجرف الموعد: مهمّةٌ كل ساعة
    تستغرق دقيقتين تصير كل ساعة ودقيقتين، ثمّ كل ساعة وأربع.

    فالتقدّم من الموعد **المقرَّر** بقفزات الفترة حتى يتجاوز الآن:
    الإيقاع محفوظ، والفائت يُنفَّذ مرّة واحدة.
    """
    if now is None:
        # الاستيراد عند الحاجة وحدها: الحساب هنا نقيّ، ومُناديه
        # الذي يمرّر ``now`` لا يحتاج Django — فيُختبَر بلا إطار.
        from django.utils import timezone

        now = timezone.now()
    step = timedelta(seconds=job.interval_seconds)
    nxt = job.next_run or now
    if nxt > now:
        return nxt
    # قفزةٌ واحدة على الأقل، ثمّ ما يلزم للحاق
    missed = int((now - nxt).total_seconds() // step.total_seconds()) + 1
    return nxt + step * missed


def _retry_at(job):
    """موعد إعادة المحاولة بعد تخطٍّ — لا الفترة كاملة ولا صفر."""
    from datetime import timedelta

    from django.utils import timezone

    wait = min(RETRY_AFTER_SKIP, max(30, job.interval_seconds))
    return timezone.now() + timedelta(seconds=wait)


# ═══════════════════════ التنفيذ ═══════════════════════

def run_job(job, *, manual: bool = False) -> dict:
    """يشغّل مهمّة واحدة ويسجّل نتيجتها — ولا يرمي أبداً.

    استثناءٌ يهرب من هنا يقتل خيط الموزِّع، فتتوقّف **كل** المهامّ
    بسبب واحدة. وقد وقع هذا الشكل من العطب في المشروع من قبل.
    """
    from django.utils import timezone

    from .models import JobRun, ScheduledJob

    # ═══ حارس التكرار: عملٌ تمّ ولم يُسجَّل ═══
    #
    # حين تُقفل القاعدة يفشل تقدّم ``next_run``، فتبقى المهمّة
    # مستحقّةً وتُشغَّل من جديد — وعملُها قد تمّ. ومسحٌ استغرق اثنتي
    # عشرة دقيقة يُعاد كاملاً، فيطيل احتكار القاعدة، فيفشل التسجيل
    # ثانيةً: حلقةٌ تُغذّي نفسها.
    #
    # والتشغيل اليدوي مستثنى: من ضغط الزرّ يريدها الآن.
    if not manual and _ran_recently(job):
        log.info("تُخطّي %s: شُغّلت في هذه العملية قبل قليل "
                 "ولم يتقدّم موعدها (القاعدة مقفلة غالباً)", job.code)
        return {"ok": False, "status": "skipped",
                "message": "شُغّلت للتوّ — لم يتقدّم موعدها بعد"}

    lock = _lock_for(job.code)
    if not lock.acquire(blocking=False):
        # دورةٌ سابقة ما زالت تعمل. والتخطّي يُسجَّل لا يُبتلع:
        # مهمّة تُتخطّى دائماً تعني أنّ فترتها أقصر من مدّتها.
        _finish(job, "skipped", "دورة سابقة ما زالت تعمل", 0,
                manual=manual, started=timezone.now())
        return {"ok": False, "status": "skipped"}

    started = timezone.now()
    t0 = time.perf_counter()
    # يُوسَم **قبل** العمل لا بعده: العمل قد يطول، والوسم بعده
    # يترك نافذةً تُشغَّل فيها المهمّة مرّتين.
    _mark_ran(job.code)
    # ═══ هذه الكتابة كانت خارج ``try`` ═══
    #
    # وقفلُ القاعدة عندها كان يهرب من الدالّة فيقتل الموزّع —
    # نقضاً للوعد المكتوب أعلاه. وهي تجميلية أصلاً: تصبغ الصفّ
    # «يعمل» في الشاشة. ففشلها لا يمنع تشغيل المهمّة.
    _db_write(
        lambda: ScheduledJob.objects.filter(pk=job.pk).update(
            last_status="running", last_run_at=started),
        f"بدء {job.code}")
    try:
        fn = HANDLERS.get(job.handler)
        if fn is None:
            raise RuntimeError(f"معالج غير معروف: {job.handler}")
        msg = fn(dict(job.payload or {})) or "اكتملت"
        status_ = "ok"
    except JobBusy as exc:
        # ازدحامٌ لا فشل: لا يُصبغ أحمر ولا يرفع عدّاد الفشل
        msg, status_ = str(exc)[:280], "skipped"
    except Exception as exc:  # noqa: BLE001
        log.exception("فشلت المهمّة %s", job.code)
        msg, status_ = str(exc)[:280], "fail"
    finally:
        lock.release()

    ms = int((time.perf_counter() - t0) * 1000)
    _finish(job, status_, msg, ms, manual=manual, started=started)
    return {"ok": status_ == "ok", "status": status_, "message": msg,
            "duration_ms": ms}


def _finish(job, status_: str, message: str, ms: int, *, manual: bool,
            started) -> None:
    """يحفظ النتيجة على المهمّة وفي السجلّ، ويقدّم الموعد.

    ولا يرمي: يُنادى من ``finally`` بعد أن عملت المهمّة فعلاً،
    فرميُه هنا يُضيّع عملاً تمّ ويقتل الموزّع معه.
    """
    from django.db.models import F

    from .models import JobRun, ScheduledJob

    fields = {
        "last_status": status_,
        "last_message": (message or "")[:300],
        "last_duration_ms": ms,
        "last_run_at": started,
        "run_count": F("run_count") + 1,
    }
    if status_ == "fail":
        fields["fail_count"] = F("fail_count") + 1

    if status_ == "skipped":
        # ═══ التأجيل لا البقاء مستحقّاً ═══
        #
        # النسخة الأولى تركت الموعد كما هو «كي تستحقّ في النبضة
        # التالية». والأثر المقيس: أربع محاولات في الدقيقة طوال
        # الدورة الطويلة، وسجلٌّ ممتلئ وعدّادٌ منتفخ بلا عمل.
        #
        # ولا يُعدّ تشغيلاً: ``run_count`` عدد ما جرى فعلاً.
        fields.pop("run_count", None)
        fields["next_run"] = _retry_at(job)
    else:
        fields["next_run"] = advance(job)
    # فشلُ هذه يعني أنّ ``next_run`` لم يتقدّم، فتُعاد المهمّة في
    # النبضة التالية. تكرارٌ محتمل — وهو أهون من موت الموزّع.
    if not _db_write(
            lambda: ScheduledJob.objects.filter(pk=job.pk).update(**fields),
            f"نتيجة {job.code}"):
        return

    try:
        # ═══ نوبة الازدحام سطرٌ واحد لا عشرة ═══
        #
        # مزامنةٌ تستغرق عشر دقائق تُنتج تخطّياً كل تسعين ثانية —
        # سبعة أسطر متطابقة تدفن ما قبلها. فيُكتب أوّل تخطٍّ في
        # النوبة، ويُهمَل ما تلاه حتى تتغيّر الحالة.
        skip_repeat = (status_ == "skipped"
                       and JobRun.objects.filter(job_id=job.pk)
                       .order_by("-started_at")
                       .values_list("status", flat=True).first() == "skipped")
        if not skip_repeat:
            JobRun.objects.create(job_id=job.pk, started_at=started,
                                  duration_ms=ms, status=status_,
                                  message=(message or "")[:300],
                                  manual=manual)
            _trim_runs(job.pk)
    except Exception:  # noqa: BLE001
        # السجلّ توثيقٌ لا شرط عمل: فشل كتابته لا يُسقط المهمّة.
        log.warning("تعذّر حفظ سجلّ التشغيل لـ %s", job.code)


def _trim_runs(job_id: int) -> None:
    from .models import JobRun

    ids = list(JobRun.objects.filter(job_id=job_id)
               .order_by("-started_at")
               .values_list("id", flat=True)[MAX_RUNS_PER_JOB:])
    if ids:
        JobRun.objects.filter(id__in=ids).delete()


def due_jobs():
    from django.utils import timezone

    from .models import ScheduledJob

    return list(ScheduledJob.objects.filter(
        active=True, next_run__lte=timezone.now()).order_by("priority", "id"))


def run_due(*, block: bool = False) -> list[dict]:
    """يشغّل كل مستحقّ.

    ``block=True`` للتشغيل الخارجي (أمر ``run_jobs``): ينتظر
    الانتهاء ثمّ يخرج، وإلّا مات الخيط مع العملية قبل أن يعمل.
    """
    out = []
    for job in due_jobs():
        if block:
            # حزامُ أمانٍ ثانٍ: ``run_job`` يَعِد بألّا يرمي، وهذا
            # يضمن الوعد ولو نُقض. فمهمّةٌ واحدة يجب ألّا تمنع
            # التسع الباقيات من العمل.
            try:
                out.append({"code": job.code, **run_job(job)})
            except Exception as exc:  # noqa: BLE001
                log.exception("هرب استثناء من run_job لـ %s", job.code)
                out.append({"code": job.code, "ok": False,
                            "status": "fail", "message": str(exc)[:200]})
        else:
            threading.Thread(target=run_job, args=(job,),
                             name=f"cron-{job.code}", daemon=True).start()
            out.append({"code": job.code, "status": "started"})
    return out


# ═══════════════════════ الحلقة ═══════════════════════

def _loop(initial_delay: float = 6.0) -> None:
    from django.utils import timezone

    time.sleep(initial_delay)          # مهلة حتى يستقرّ الخادم
    try:
        ensure_defaults()
    except Exception:  # noqa: BLE001
        log.exception("تعذّر بذر المهامّ الافتراضية")

    while True:
        try:
            _state["ticks"] += 1
            _state["last_tick"] = timezone.now().isoformat()
            run_due()
        except Exception:  # noqa: BLE001
            log.exception("خطأ في نبضة الجدولة")
        time.sleep(TICK_SECONDS)


def start() -> bool:
    """يشغّل الموزِّع مرّة واحدة."""
    if _state["thread_started"]:
        return False
    _state["thread_started"] = True
    threading.Thread(target=_loop, name="cron", daemon=True).start()
    log.info("محرّك الجدولة يعمل — نبضة كل %ss", TICK_SECONDS)
    return True


# ═══════════════════════ البذر ═══════════════════════

def default_jobs() -> list[dict]:
    """المهامّ الافتراضية — من متغيّرات البيئة القائمة.

    البذر يقرأ ما كان يقرأه ``apps.py`` بالضبط، فأوّل تشغيل بعد
    الترقية لا يغيّر شيئاً: من كان يمسح الكريبتو كل شمعة يبقى
    كذلك. والتغيير يصير من الواجهة بعدها.
    """
    import os

    markets = [m.strip() for m in
               os.environ.get("AUTO_SCAN_MARKETS", "crypto").split(",")
               if m.strip()] or ["crypto"]
    sync = [m.strip() for m in
            os.environ.get("MARKET_SYNC_MARKETS", ",".join(markets)).split(",")
            if m.strip()] or markets

    jobs: list[dict] = []
    for m in markets:
        jobs.append({
            "code": f"scan:{m}", "handler": "scan",
            "name": f"مسح السوق — {m}",
            "interval_number": 15, "interval_type": "minutes",
            "payload": {"market": m}, "priority": 20,
            "active": os.environ.get("AUTO_SCAN", "1") == "1",
        })
    jobs.append({
        "code": "market_sync", "handler": "market_sync",
        "name": "مزامنة الشموع",
        "interval_number": 10, "interval_type": "minutes",
        "payload": {"markets": sync}, "priority": 10,
        "active": os.environ.get("MARKET_DATA_SYNC", "1") == "1",
    })
    jobs.append({
        "code": "watch_monitor", "handler": "watch_monitor",
        "name": "مراقبة الفرص",
        "interval_number": max(1, int(os.environ.get(
            "WATCH_INTERVAL_SECONDS", "300")) // 60),
        "interval_type": "minutes", "payload": {}, "priority": 5,
        "active": os.environ.get("WATCH_MONITOR", "1") == "1",
    })
    jobs.append({
        # يوميّاً لا بالساعة: البيانات تنمو ببضع صفقات في اليوم،
        # وتدريبٌ كل ساعة يحرق المعالج على مجموعةٍ لم تتغيّر.
        "code": "train_predictor", "handler": "train_predictor",
        "name": "تدريب نموذج التنبؤ",
        "interval_number": 1, "interval_type": "days",
        "payload": {"min_rows": 100, "promote": True}, "priority": 40,
        "active": os.environ.get("PREDICTOR_TRAINING", "1") == "1",
    })
    jobs.append({
        # كل ربع ساعة: أسرع من المسح كي تُغلق الوقوف بسرعة،
        # وأبطأ من أن تُغرق المزوّد بطلبات الأسعار.
        "code": "paper", "handler": "paper",
        "name": "دورة المحفظة الورقية",
        "interval_number": 15, "interval_type": "minutes",
        "payload": {}, "priority": 35,
        "active": os.environ.get("PAPER_TRADING", "1") == "1",
    })
    jobs.append({
        "code": "pes", "handler": "pes",
        "name": "مسح ما قبل الانفجار",
        "interval_number": 1, "interval_type": "hours",
        "payload": {}, "priority": 25,
        "active": os.environ.get("PES_SCAN", "1") == "1",
    })
    jobs.append({
        "code": "squeeze", "handler": "squeeze",
        "name": "قياس الانضغاط",
        "interval_number": 2, "interval_type": "hours",
        "payload": {"timeframes": ["1h", "4h", "1d"]}, "priority": 30,
        "active": os.environ.get("SQUEEZE_SCAN", "1") == "1",
    })
    jobs.append({
        "code": "settlement", "handler": "settlement",
        "name": "حسم الصفقات",
        "interval_number": max(1, int(os.environ.get(
            "SETTLEMENT_INTERVAL_SECONDS", "180")) // 60),
        "interval_type": "minutes", "payload": {}, "priority": 15,
        "active": os.environ.get("TRADE_SETTLEMENT", "1") == "1",
    })
    return jobs


def ensure_defaults() -> int:
    """ينشئ ما لم يوجد — ولا يلمس ما وُجد.

    الإنشاء بالمفتاح: من غيّر فترةً من الواجهة لا يُعاد ضبطها في
    كل إقلاع. وهذا الفرق بين البذر والفرض.
    """
    from django.utils import timezone

    from .models import ScheduledJob

    # ═══ التوزيع على الدقائق ═══
    #
    # بذرُها كلّها على ``now`` يجعل الستّ تستحقّ في النبضة نفسها.
    # وثلاث مهامّ مسحٍ تتشارك قفلاً واحداً في ``scheduler``، فتفوز
    # واحدة وتُردّ اثنتان — وهو ما ظهر في الشاشة: ``scan:us`` و
    # ``scan:saudi`` لا تعملان أبداً بينما ``scan:crypto`` تعمل.
    #
    # فيُفصل بين المتزاحمات بدقيقة: تأخيرٌ لا يُلاحَظ، ويكفي لأن
    # تنتهي السابقة قبل أن تستحقّ التالية.
    made = 0
    now = timezone.now()
    offset = 0
    for spec in default_jobs():
        start_at = now + timedelta(minutes=offset)
        _, created = ScheduledJob.objects.get_or_create(
            code=spec["code"],
            defaults={**spec, "next_run": start_at},
        )
        if created:
            made += 1
            # المسح وحده يتزاحم؛ الباقي بأقفال مستقلّة
            if spec["handler"] == "scan":
                offset += 1
    if made:
        log.info("بُذرت %s مهمّة مجدولة", made)
    return made


__all__ = ["start", "status", "run_job", "run_due", "due_jobs", "advance",
           "JobBusy", "RETRY_AFTER_SKIP",
           "ensure_defaults", "default_jobs", "HANDLERS", "HANDLER_LABELS",
           "TICK_SECONDS", "MAX_RUNS_PER_JOB"]
