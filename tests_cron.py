# -*- coding: utf-8 -*-
"""محرّك الجدولة — الحساب الذي يخطئ بصمت.

═══ ما استُبدل ═══

أربع حلقات مستقلّة، كلٌّ خيطٌ بفترته في متغيّر بيئة وحالته في
الذاكرة::

    scheduler          مسح تلقائي        AUTO_SCAN_MARKETS
    market_sync_worker مزامنة الشموع     MARKET_SYNC_MARKETS
    monitor            مراقبة الفرص      WATCH_INTERVAL_SECONDS
    settlement         حسم الصفقات       SETTLEMENT_INTERVAL_SECONDS

فلا سجلّ يبقى بعد إعادة التشغيل، ولا تغيير لفترةٍ بلا تحرير ملفّ.

═══ وما يحرسه هذا الملف ═══

عطب الجدولة صامت: لا يفشل شيء ظاهر، بل يعمل الشيء في الوقت الخطأ
— أو خمسمئة مرّة دفعة واحدة. وثلاثة أخطاء كلاسيكية:

    ١) التراكم — خادمٌ أُغلق يومين ومهمّةٌ كل خمس دقائق: ٥٧٦
       تشغيلة تعويضاً لا يفيد منها إلّا الأخيرة.
    ٢) الانجراف — الحساب من لحظة الانتهاء يجعل «كل ساعة» تصير
       كل ساعة ودقيقتين، ثمّ كل ساعة وأربع.
    ٣) الفترة الصفرية — دورةٌ بلا نهاية.
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── تحميل ``advance`` بلا Django ──
src = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
tree = ast.parse(src)
adv_node = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "advance")
# ``timezone.now()`` لا يُستدعى ما دام ``now`` مُمرَّراً
ns: dict = {"timedelta": timedelta}
exec(compile(ast.Module(body=[adv_node], type_ignores=[]), "cron", "exec"), ns)
advance = ns["advance"]


class Job:
    """أقلّ ما تحتاجه ``advance`` — لا قاعدة بيانات."""

    def __init__(self, next_run, seconds):
        self.next_run = next_run
        self.interval_seconds = seconds


NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=tz.utc)


# ── ١) الموعد في المستقبل لا يُمسّ ──
future = NOW + timedelta(minutes=3)
check("١ المستقبل يبقى", advance(Job(future, 300), now=NOW) == future)


# ═══ ٢) التراكم ═══
#
# الخادم أُغلق يومين ومهمّةٌ كل خمس دقائق. الموعد المحفوظ قبل
# يومين، والآن الآن.
two_days = NOW - timedelta(days=2)
nxt = advance(Job(two_days, 300), now=NOW)
check("٢ الفائت لا يتراكم", nxt > NOW, str(nxt))
# قفزةٌ واحدة بعد الآن لا أكثر: الموعد الجديد خلال فترةٍ واحدة
check("  والموعد خلال فترة واحدة",
      nxt - NOW <= timedelta(seconds=300), str(nxt - NOW))
# ولو أُضيفت الفترة مرّة واحدة لبقي في الماضي — وهو العطب
check("  ولو أُضيفت مرّة لبقي ماضياً",
      two_days + timedelta(seconds=300) < NOW)
# كم تشغيلة كان سيُنتجها الحلّ الساذج؟
naive = int((NOW - two_days).total_seconds() // 300)
check("  والساذج كان سيُشغّل مئات", naive > 500, str(naive))


# ═══ ٣) الانجراف ═══
#
# الحساب من الموعد المقرَّر لا من لحظة الانتهاء: مهمّةٌ كل ساعة
# تستغرق دقيقتين يجب أن تبقى على رأس الساعة.
sched = datetime(2026, 8, 28, 12, 0, 0, tzinfo=tz.utc)
finished = sched + timedelta(minutes=2)          # انتهت 12:02
nxt = advance(Job(sched, 3600), now=finished)
check("٣ لا انجراف", nxt == sched + timedelta(hours=1), str(nxt))
check("  والإيقاع على رأس الساعة", nxt.minute == 0 and nxt.second == 0)
# ثلاث دورات متتالية تبقى منضبطة
t = sched
for _ in range(3):
    t = advance(Job(t, 3600), now=t + timedelta(minutes=2))
check("  وبعد ثلاث دورات كذلك",
      t == sched + timedelta(hours=3), str(t))


# ── ٤) الموعد الغائب ──
check("٤ بلا موعد يُجدول من الآن",
      advance(Job(None, 600), now=NOW) == NOW + timedelta(seconds=600))
# والمستحقّ الآن بالضبط يتقدّم — لا يبقى مستحقّاً إلى الأبد
check("  والمستحقّ الآن يتقدّم", advance(Job(NOW, 600), now=NOW) > NOW)


# ═══ ٥) الفترة الصفرية ═══
#
# ``interval_seconds`` في النموذج يفرض حدّاً أدنى. وبلا الحدّ تدور
# ``advance`` بلا نهاية بحثاً عن موعدٍ بعد الآن — تعليقٌ تامّ للخيط
# لا استثناء يُرى في سجلّ.
models = (ROOT / "web" / "dashboard" / "models.py").read_text(encoding="utf-8")
check("٥ الفترة لها حدّ أدنى", "max(30," in models, "لا حدّ")
# ولو مرّت فترةٌ صفرية إلى advance لتعلّقت — فتُفحص أنّها لا تُبنى
mtree = ast.parse(models)
cls = next(n for n in ast.walk(mtree)
           if isinstance(n, ast.ClassDef) and n.name == "ScheduledJob")
prop = next(n for n in cls.body
            if isinstance(n, ast.FunctionDef) and n.name == "interval_seconds")
# ‏@property يُجرَّد: المطلوب الحساب لا واصف السمة
prop.decorator_list = []
ns2: dict = {}
exec(compile(ast.Module(body=[prop], type_ignores=[]), "m", "exec"), ns2)
calc = ns2["interval_seconds"]


class Cfg:
    def __init__(self, n, t):
        self.interval_number, self.interval_type = n, t


# توقّعتُ أوّلاً أن يعطي الصفر ثلاثين ثانية، والصواب ستّون:
# ``interval_number or 1`` يحرس قبل ``max(30, …)``. فحارسان لا
# واحد — والمهمّ أنّ الناتج لا يكون صفراً أبداً مهما كان المدخل.
for n in (0, -5, None):
    val = calc(Cfg(n, "minutes"))
    check(f"  و«{n}» لا يعطي صفراً", val >= 30, str(val))
check("  ودقيقة = 60", calc(Cfg(1, "minutes")) == 60)
check("  وساعة = 3600", calc(Cfg(1, "hours")) == 3600)
check("  ويوم = 86400", calc(Cfg(1, "days")) == 86400)
check("  والوحدة المجهولة تُعامَل دقائق", calc(Cfg(2, "زخرف")) == 120)


# ── ٦) المعالجات تنادي المنطق القائم لا تعيد كتابته ──
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
for fn in ("scheduler.run_scan", "market_sync_worker.run_once",
           "monitor.check_once", "settlement.settle_once"):
    check(f"٦ ينادي {fn}", fn in code)
check("  والمعالجات أربعة", code.count("HANDLERS = {") == 1
      and all(k in code for k in ('"scan"', '"market_sync"',
                                  '"watch_monitor"', '"settlement"')))

# ═══ الفشل يظهر فشلاً ═══
#
# ``check_once`` يعيد ``{"error": "migrate"}`` مع ``checked: 0``.
# وبلا فحص المفتاح تُقرأ «فُحص 0» نجاحاً بلا عمل — والجدول أخضر
# والمراقبة معطّلة منذ أسبوع.
check("  والخطأ يُرفع لا يُبتلع",
      code.count("raise RuntimeError") >= 4, "معالج يبتلع خطأه؟")


# ═══ ٦ب) الازدحام ليس فشلاً ═══
#
# قِيس على الشاشة بعد أوّل تشغيل حقيقي::
#
#     scan:crypto   فشلت   «دورة أخرى جارية»   1 (1)
#     scan:us       فشلت   «دورة أخرى جارية»   2 (2)
#     scan:saudi    تُخطّيت  «دورة سابقة ما زالت تعمل»  15
#
# والسبب أنّ ``scheduler`` قفلٌ **واحد لكل الأسواق**، فثلاث مهامّ
# مسحٍ تستحقّ معاً فتفوز واحدة وتُردّ اثنتان. وهذا سلوكٌ صحيح —
# لكنّه عُرض «فشلاً» أحمر ورفع عدّاد الفشل، فيبحث المستخدم عن خللٍ
# ليس موجوداً.
check("٦ب الازدحام له استثناء خاصّ", "class JobBusy" in code)
# ═══ القياس داخل ``run_job`` وحدها ═══
#
# النسخة الأولى قاست على الملفّ كلّه بـ ``code.index`` — أي أوّل
# ``except Exception`` أينما وقع. فلمّا أُضيف معالجٌ آخر قبلها في
# الملفّ صار الاختبار يقارن دالّتين مختلفتين ويرسب، والترتيب داخل
# ``run_job`` سليم. فالنطاق يُحدَّد بالدالّة لا بالملفّ.
_fn = next(n for n in ast.walk(ast.parse(code))
           if isinstance(n, ast.FunctionDef) and n.name == "run_job")
run_job_src = ast.get_source_segment(code, _fn) or ""
check("  ويُلتقط قبل Exception",
      run_job_src.index("except JobBusy")
      < run_job_src.index("except Exception as exc"))
busy_block = run_job_src.split("except JobBusy")[1].split("except Exception")[0]
check("  ويُسجَّل تخطّياً لا فشلاً", '"skipped"' in busy_block, busy_block[:80])
check("  ولا يُسجَّل فشلاً", '"fail"' not in busy_block)
# والمصدر يُعلن الازدحام بمفتاح لا بنصٍّ عربي يُترجَم يوماً
sched = (ROOT / "web" / "dashboard" / "scheduler.py").read_text(encoding="utf-8")
sync = (ROOT / "web" / "dashboard"
        / "market_sync_worker.py").read_text(encoding="utf-8")
check("  والمصدر يعلّمه بمفتاح", '"busy": True' in sched and '"busy": True' in sync)
check("  والمعالج يقرأ المفتاح", 'out.get("busy")' in code)


# ═══ ٦ج) التخطّي يؤجّل ولا يدور ═══
#
# النسخة الأولى لم تقدّم الموعد عند التخطّي «كي تستحقّ في النبضة
# التالية». والأثر المقيس: ``market_sync`` بلغت ١٥ تشغيلة بينما
# جاراتها ٢–٤ — أربع محاولات في الدقيقة طوال الدورة الطويلة،
# سجلٌّ ممتلئ وعدّاد منتفخ بلا عملٍ جرى.
check("٦ج التخطّي يؤجّل", "_retry_at(job)" in code)
check("  ولا يبقى مستحقّاً",
      'if status_ != "skipped":\n        fields["next_run"]' not in code)
check("  والمهلة أطول من النبضة",
      "RETRY_AFTER_SKIP" in code)
retry = ns.get("RETRY_AFTER_SKIP")
tick = None
for line in src.splitlines():
    if line.startswith("RETRY_AFTER_SKIP ="):
        retry = int(line.split("=")[1].strip())
    if line.startswith("TICK_SECONDS ="):
        tick = int(line.split("=")[1].strip())
check("  فعلاً", retry and tick and retry > tick, f"{retry} مقابل {tick}")
# ولا يُعدّ تشغيلاً: العدّاد لما جرى فعلاً
check("  ولا يرفع عدّاد التشغيل", 'fields.pop("run_count", None)' in code)
check("  ولا عدّاد الفشل",
      'if status_ == "fail":' in code and "fail_count" in code)
# ونوبة الازدحام سطرٌ واحد في السجلّ لا عشرة
check("  ونوبة التخطّي سطرٌ واحد", "skip_repeat" in code)


# ═══ ٦د) البذر يوزّع المتزاحمات ═══
#
# بذرُها كلّها على ``now`` هو ما جعل ``scan:us`` و``scan:saudi``
# لا تعملان أبداً: تستحقّان مع ``scan:crypto`` وتخسران القفل.
check("٦د البذر يوزّع المسح", "timedelta(minutes=offset)" in code)
check("  والمسح وحده يُزاح",
      'if spec["handler"] == "scan"' in code)
cmd_src = (ROOT / "web" / "dashboard" / "management" / "commands"
           / "run_jobs.py").read_text(encoding="utf-8")
# ومن بذر قبل الإصلاح يحتاج تصحيحاً بلا حذف
check("  وللمبذور سلفاً أداة", "--stagger" in cmd_src)


# ── ٧) الاستثناء لا يقتل الموزِّع ──
check("٧ run_job يلتقط كل استثناء",
      "except Exception" in code and "def run_job" in code)
check("  والحلقة كذلك",
      code.count("except Exception") >= 3)
# ═══ توقّعٌ انقلب ═══
#
# كان هنا فحصٌ يفرض ألّا يُقدَّم الموعد عند التخطّي — وهو بالضبط
# ما أنتج الدوران (أربع محاولات في الدقيقة). فالفحص الآن معكوس:
# التخطّي **يجب** أن يؤجّل.
check("  والتخطّي يؤجّل لا يبقى", "_retry_at(job)" in code)


# ── ٨) السجلّ محدود ──
#
# ‏events.jsonl بلغ ٣٠٥ ميغابايت بلا حدّ.
check("٨ لسجلّ التشغيل سقف", "MAX_RUNS_PER_JOB" in code)
check("  ويُقصّ عند الكتابة", "_trim_runs(" in code)


# ── ٩) البذر لا يفرض ──
#
# من غيّر فترةً من الواجهة لا يجوز أن تُعاد في كل إقلاع.
check("٩ البذر get_or_create", "get_or_create" in code)
check("  ولا update_or_create", "update_or_create" not in code,
      "البذر يفرض على المحفوظ؟")
# ويقرأ متغيّرات البيئة القائمة — فأوّل إقلاع لا يغيّر سلوكاً
for env in ("AUTO_SCAN_MARKETS", "MARKET_SYNC_MARKETS",
            "WATCH_INTERVAL_SECONDS", "SETTLEMENT_INTERVAL_SECONDS"):
    check(f"  ويقرأ {env}", env in code)


# ── ١٠) الربط ──
apps = (ROOT / "web" / "dashboard" / "apps.py").read_text(encoding="utf-8")
acode = "\n".join(l for l in apps.splitlines() if not l.strip().startswith("#"))
check("١٠ الإقلاع يشغّل المحرّك", "cron.start()" in acode)
# ═══ off ليس توثيقاً بل سلوكاً ═══
#
# ``run_jobs`` يوثّق ``SCHEDULER_ENGINE=off``. ووثيقةٌ تصف ما لا
# يفعله البرنامج أسوأ من غياب الوثيقة.
check("  و off يوقف الجدولة", 'engine == "off"' in acode)
check("  و legacy يعيد القديم", 'engine == "legacy"' in acode)
check("  والأمر run_jobs يُستثنى من الإقلاع", '"run_jobs"' in acode)

cmd = (ROOT / "web" / "dashboard" / "management" / "commands"
       / "run_jobs.py").read_text(encoding="utf-8")
# خيطٌ طليق يُقتل مع العملية قبل أن يعمل
check("  والأمر ينتظر النتيجة", "block=True" in cmd)
check("  ويبذر إن كانت القاعدة فارغة", "ensure_defaults()" in cmd)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for n in ("api_jobs", "api_job_runs", "api_job_run_now", "api_job_toggle",
          "api_job_save", "api_jobs_seed"):
    check(f"  و{n} مسجَّل", n in urls)

views = (ROOT / "web" / "dashboard" / "job_views.py").read_text(encoding="utf-8")
vcode = "\n".join(l for l in views.splitlines() if not l.strip().startswith("#"))
check("  والفترة تُتحقّق قبل الحفظ", "number < 1" in vcode)
check("  والوحدة كذلك", "itype not in valid" in vcode)
# «شغّل الآن» لا يزيح الإيقاع
check("  و«شغّل الآن» في خيط", "threading.Thread" in vcode)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "jobs-page.js").read_text(encoding="utf-8")
check("  والشاشة تعرض حالة المحرّك", "thread_started" in js)
check("  وتعرض المتوقّف أحمر", "المحرّك متوقّف" in js)
check("  وتعرض السجلّ", "/runs/" in js)

html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "jobs.html").read_text(encoding="utf-8")
# التنبيه الذي لا يجوز إخفاؤه: المهامّ تموت مع الخادم
check("  والصفحة تنبّه أنّها تتبع الخادم",
      "ما دام الخادم يعمل" in html)
check("  وتدلّ على البديل", "run_jobs" in html)
check("  والوثيقة موجودة", (ROOT / "docs" / "SCHEDULER.md").exists())


# ═══ ٩) قفلُ القاعدة لا يقتل الموزّع ═══
#
# ‏SQLite يسمح بكاتبٍ واحد. ومسحٌ يستغرق دقائق يحجب كل كاتبٍ سواه
# طوال مدّته — فيسقط أيّ ``UPDATE`` يقع في تلك النافذة.
#
# ووقع هذا فعلاً: الخادم يعمل ومحرّكه يمسح، والمستخدم يشغّل
# ``run_jobs`` من الطرفية، فينهار الأمر بأثرٍ من ثلاثين سطراً.
# والسبب أنّ أوّل كتابة (``last_status="running"``) كانت **خارج**
# ``try`` — فوعدُ «لا يرمي أبداً» كان في الوثيقة لا في الكود.
check("٩ الكتابة تمرّ بحارس", "_db_write" in code)
check("  ويُعيد المحاولة", "DB_RETRIES" in code)
check("  ولا يرمي", "return False" in code.split("def _db_write")[1][:900])
check("  ويميّز القفل عن غيره", "def _is_locked" in code)

# ولا كتابة عارية داخل ``run_job``: كلّها إمّا داخل ``try`` أو
# عبر الحارس. والقياس على النصّ قبل ``try:`` تحديداً.
_pre = run_job_src.split("    try:")[0]
check("  ولا كتابة عارية قبل try",
      ".update(" not in _pre or "_db_write" in _pre, _pre[-90:])

# و``run_due`` حزامٌ ثانٍ: مهمّةٌ واحدة يجب ألّا تمنع الباقيات
_due = next(n for n in ast.walk(ast.parse(code))
            if isinstance(n, ast.FunctionDef) and n.name == "run_due")
due_src = ast.get_source_segment(code, _due) or ""
check("  و run_due يحرس كل مهمّة",
      "except Exception" in due_src and "run_job(job)" in due_src)

# والأمر الخارجي يقول السبب بلغةٍ لا بأثر استدعاء
rj = (ROOT / "web" / "dashboard" / "management" / "commands"
      / "run_jobs.py").read_text(encoding="utf-8")
check("  والأمر يشرح القفل", "قاعدة البيانات مقفلة" in rj)
check("  ويدلّ على SCHEDULER_ENGINE=off", "SCHEDULER_ENGINE=off" in rj)
check("  ولا يبتلع خطأً آخر", 'if "locked" not in str(exc).lower():' in rj
      and "raise\n" in rj)


# ═══ ١٠) عملٌ تمّ ولم يُسجَّل لا يُعاد ═══
#
# حين تُقفل القاعدة يفشل تقدّم ``next_run``، فتبقى المهمّة
# مستحقّةً وتُشغَّل من جديد — وعملُها قد تمّ. ومسحٌ استغرق اثنتي
# عشرة دقيقة يُعاد كاملاً، فيطيل احتكار القاعدة، فيفشل التسجيل
# ثانيةً: حلقةٌ تُغذّي نفسها. وهذا ما ظهر بـ «القاعدة مقفلة» على
# أربع مهامّ دفعةً واحدة.
check("١٠ ذاكرةٌ لما شُغّل في العملية", "_ran_at" in code)
check("  وتُفحَص قبل التشغيل", "_ran_recently(job)" in run_job_src)
check("  والوسم قبل العمل لا بعده",
      run_job_src.index("_mark_ran(job.code)")
      < run_job_src.index("fn = HANDLERS.get"))
# التشغيل اليدوي مستثنى: من ضغط الزرّ يريدها الآن
check("  واليدوي مستثنى", "not manual and _ran_recently" in run_job_src)
# والحدّ من فترة المهمّة نفسها لا رقمٌ مزروع
check("  والحدّ من فترة المهمّة", "job.interval_seconds" in code.split(
    "def _ran_recently")[1][:600])
check("  وبحدٍّ أدنى يمنع الحلقة", "max(30.0" in code)

_rr = next(n for n in ast.walk(ast.parse(code))
           if isinstance(n, ast.FunctionDef) and n.name == "_ran_recently")
_rr_src = ast.get_source_segment(code, _rr) or ""
check("  ولا يرمي إن تعذّرت القراءة", "except Exception" in _rr_src)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
