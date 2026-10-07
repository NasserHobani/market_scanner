# -*- coding: utf-8 -*-
"""مسارا الجدولة — ولماذا تأخّر كلُّ شيء.

═══ العطب المقيس ═══

``run_due`` كان يشغّل كل مستحقٍّ **بالتسلسل في عمليةٍ واحدة**،
وحلقة ‎docker-scheduler.sh‎ تنتظر الدفعة كلّها قبل أن تنام. فطولُ
الدورة = مجموع مُدد كل المهامّ المستحقّة.

والترتيب بالأولوية: watch(5) ← sync(10) ← settlement(15) ←
scan(20) ← topdown(24) ← pes(25) ← squeeze(30) ← paper(35).

فـ``settlement`` فترتها **ثلاث دقائق** ولا تستطيع أن تعمل أكثر
من مرّةٍ في الدورة. ودورةٌ فيها مسحُ الكريبتو (اثنتا عشرة دقيقة
مقيسة) ومزامنةٌ بنحو ١٩٠٠ طلب تبلغ أربعين دقيقة — فصارت مهمّةُ
الثلاث دقائق كل أربعين. متأخّرةً ثلاثة عشر ضعفاً.

ولا شيء يقول ذلك: كل مهمّة «نجحت»، وحالتُها خضراء.

═══ والفخّ في الإصلاح ═══

``claim_due`` **يقدّم الموعد لحظة الحجز**. فحجزُ ستٍّ ثمّ التوقّف
عند الثالثة لنفاد الميزانية يعني أنّ الثلاث الباقيات تقدّمت
مواعيدها ولم تعمل — تخطٍّ صامت، وهو أسوأ من التأخّر لأنّه لا
يظهر في شيء.

فالحجز واحدةً واحدة، والميزانية تُفحَص **قبل** كل حجز.

═══ وفخٌّ ثانٍ في bash ═══

``docker stop`` يرسل SIGTERM إلى العملية الأولى وحدها. وحلقة
المسار الثقيل في الخلفية بنسختها الخاصّة من ``running`` — فلا
تراها تتغيّر، وتبقى تعمل بعد أمر التوقّف.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from tests_helpers import Checks, body_of, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

CRON = ROOT / "web" / "dashboard" / "cron.py"
code = code_of(CRON)


# ═══════════ ١) التصنيف ═══════════
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("_lane_probe", CRON)
_mod = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
    _ok = True
except Exception as exc:  # noqa: BLE001
    _ok = False
    c("١ تحميل الوحدة", False, f"{type(exc).__name__}: {str(exc)[:70]}")

if _ok:
    c("١ الثقيل ثقيل", _mod.lane_of("scan") == "heavy")
    c("  والمزامنة ثقيلة", _mod.lane_of("market_sync") == "heavy")
    c("  والانضغاط ثقيل", _mod.lane_of("squeeze") == "heavy")
    c("  والحسم خفيف", _mod.lane_of("settlement") == "light")
    c("  والمراقبة خفيفة", _mod.lane_of("watch_monitor") == "light")
    c("  والمحفظة خفيفة", _mod.lane_of("paper") == "light")
    # ═══ والمجهول خفيف ═══
    #
    # مُعالِجٌ جديد يُضاف بلا تصنيف يجب أن يعمل في موعده، لا أن
    # يُدفن خلف المسح. وإن ثقُل ظهر في الأداة بمدّته فيُنقل.
    c("  والمجهول خفيف", _mod.lane_of("لا_يوجد") == "light")


# ═══════════ ٢) الميزانية قبل الحجز ═══════════
#
# وهذا هو الفرق بين «تأخّرت» و«لم تعمل ولا أحد يدري».
rd = body_of(CRON, "run_due")
c("٢ الميزانية تُفحَص قبل الحجز",
  rd.index("budget") < rd.index("claim_due")
  if ("budget" in rd and "claim_due" in rd) else False, rd[:200])
c("  والحجز واحدةً واحدة", "claim_due(limit=1" in rd, rd[:300])
c("  والمسار يُمرَّر", "lane=lane" in rd)
c("  والتوقّف يُسجَّل", "نفدت ميزانية" in source_of(CRON))

# ═══ ٢ب) ولا مجاعة ═══
#
# ═══ العطب الذي أحدثه الحجز واحدةً واحدة ═══
#
# إعادةُ الاستعلام في كل مرّة تعني أنّ ``claim_due`` يرتّب
# بالأولوية من جديد. و``market_sync`` أولويّتها ١٠ وفترتها عشر
# دقائق وتستغرق أطول منها — فما إن تنتهي حتى تكون **مستحقّةً من
# جديد**، فتفوز بالحجز التالي. و``scan`` أولويّتها ٢٠ فلا يأتيها
# دورٌ أبداً.
#
# ولم يظهر خطأً في شيء: المسح توقّف، فتوقّف إنشاء المراقبات،
# و``watch_monitor`` يُنهي المنتهية كل دقيقة — فجفّت شاشة
# المراقبة في أيّام، وكلّ مهمّة تقول «نجحت».
c("٢ب لكلٍّ دورٌ واحد في الدورة", "served.add(job.code)" in rd, rd[:400])
c("  والمستثنى يُمرَّر", "exclude_codes=served" in rd)
_cl = body_of(CRON, "claim_due")
c("  والحجز يستثني", "exclude_codes" in _cl and "code__in" in _cl)
c("  والسبب موثَّق", "المجاعة" in source_of(CRON))


# ═══════════ ٣) التصفية في القاعدة ═══════════
cl = body_of(CRON, "claim_due")
c("٣ المسار يصفّي الاستعلام", "handler__in" in cl, cl[:300])
c("  والخفيف يستثني الثقيل", "exclude(handler__in" in cl)
# ‏``limit`` يُقصّ بعد الجلب: تصفيةٌ في بايثون كانت ستُنقص الدفعة
c("  والتصفية قبل القصّ",
  cl.index("handler__in") < cl.index("[:limit]")
  if ("handler__in" in cl and "[:limit]" in cl) else False)
# وبلا مسار يبقى السلوك كما كان
c("  وبلا مسار لا تصفية", 'lane in ("light", "heavy")' in cl)
# والتقديم قبل التشغيل باقٍ — لا يُنقض بهذا الإصلاح
c("  والتقديم قبل التشغيل باقٍ", "next_run = advance(" in cl)
c("  و‎skip_locked‎ باقٍ", "skip_locked=True" in cl)


# ═══════════ ٤) الأمر يقبل المسار ═══════════
cmd = code_of(ROOT / "web" / "dashboard" / "management" / "commands"
              / "run_jobs.py")
c("٤ ‎--lane‎ موجود", '"--lane"' in cmd)
c("  و‎--budget‎ كذلك", '"--budget"' in cmd)
# والافتراض «الكل»: من ينادي الأمر مجرّداً يبقى سلوكه كما كان
c("  والافتراض الكلّ", 'default="all"' in cmd)
c("  و«الكل» تعني بلا تصفية", 'None if lane == "all" else lane' in cmd)


# ═══════════ ٥) حلقتان لا واحدة ═══════════
sh = source_of(ROOT / "docker-scheduler.sh")
c("٥ حلقةٌ للثقيل", "heavy_loop()" in sh)
c("  تعمل في الخلفية", "heavy_loop &" in sh)
c("  والخفيف كل فترة", "--lane light" in sh)
c("  والثقيل بميزانية", "--lane heavy --budget" in sh)
# ═══ والإشارة تُمرَّر ═══
#
# ‏SIGTERM يبلغ العملية الأولى وحدها. والابن بنسخته الخاصّة من
# ``running`` — فلا يتوقّف أبداً.
c("  والإشارة تبلغ الابن", 'kill -TERM "$HEAVY_PID"' in sh)
c("  وللابن علَمُه", "h_running" in sh)
# ودورةٌ فارغة لا تصير حلقةً محمومة
c("  والفارغة تنتظر أدنى", "h_elapsed" in sh and "sleep $(( 30" in sh)
# والنبضة باقية: فحص الصحّة يقرؤها
c("  ونبضة الحياة باقية", "/tmp/scheduler-heartbeat" in sh)


# ═══════════ ٥ب) المعلّقة تُستعاد ═══════════
#
# ``run_job`` يكتب «يعمل» قبل العمل والنتيجة بعده. وما بينهما قد
# لا يكتمل: إعادة نشرٍ، أو قتلٌ لنفاد الذاكرة، أو قراءةٌ شبكية بلا
# مهلة. فيبقى الصفّ «يعمل» إلى الأبد.
#
# وظهرت ``scan:us`` تقول «تعمل الآن» وآخر تشغيلٍ لها **قبل ثلاث
# عشرة ساعة** — فلا يُعرَف ما يعمل حقّاً ممّا مات.
c("٥ب دالّة الاستعادة", "def reclaim_stale" in code)
c("  وتُنادى في كل دورة", "reclaim_stale()" in rd, rd[:300])
_rc = body_of(CRON, "reclaim_stale")
# ═══ والعمر لا المعرّف ═══
#
# معرّفات العمليات تتكرّر، وهي في حاوياتٍ مختلفة أصلاً.
c("  والحكم بالعمر", "last_run_at" in _rc and "total_seconds()" in _rc)
c("  ومضاعف الفترة", "STALE_INTERVAL_FACTOR" in code)
# ═══ وتُسمّى بما هي ═══
#
# ليست «فشلت»: لم يُبلَّغ عن فشل. هي عملٌ بدأ ولم يُعرَف مصيره.
c("  وحالةٌ باسمها", '"stale"' in _rc, "تُسمّى فشلاً")
c("  ولا ترمي", "except Exception" in _rc)
c("  والسبب موثَّق", "ثلاث عشرة ساعة" in source_of(CRON))

js_jobs = (ROOT / "web" / "dashboard" / "static" / "dashboard"
           / "jobs-page.js").read_text(encoding="utf-8")
c("  والشاشة تسمّيها", 'stale: "معلّقة"' in js_jobs)
# وبين الموت والدورة التالية نافذةٌ تُعلَّم فيها بصرياً فوراً
c("  وتُعلَّم قبل الاستعادة", "function looksStuck" in js_jobs)

# ═══ ومهلةٌ صارمة ═══
#
# الميزانية تمنع **بدء** مهمّةٍ جديدة ولا توقف واحدةً علقت.
c("  ومهلةٌ على الدورة الثقيلة", "HEAVY_TIMEOUT" in sh and "timeout " in sh)
c("  وعلى الخفيفة", "LIGHT_TIMEOUT" in sh)
c("  والقطع يُسجَّل", "قُطعت دورة ثقيلة" in sh)
# و‎timeout‎ أطول من الميزانية: الأولى تنظيم والثانية إنقاذ
c("  والمهلة فوق الميزانية", "2400" in sh and "1500" in sh)


# ═══════════ ٦) أداةُ قياسٍ لا تخمين ═══════════
#
# «متأخّرة» وحدها لا تقول أيّ مهمّة تأكل الدورة.
doc = ROOT / "tools_doctor_cron.py"
c("٦ أداة التشخيص موجودة", doc.exists())
if doc.exists():
    dt = source_of(doc)
    c("  تقيس التأخّر بالموعد", "next_run" in dt)
    c("  وتحسب الحِمل", "المدّة ÷ الفترة" in dt or "share" in dt)
    # مهمّةٌ مدّتها أطول من فترتها لا تلحق أبداً
    c("  وتكشف المستحيلة", "أطول من فترتها" in dt)
    c("  وتفصل المسارين", "lane_of" in dt)
    c("  وتكشف المعلّقة", "مهامّ معلّقة" in dt)


sys.exit(c.report())
