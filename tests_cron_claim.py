# -*- coding: utf-8 -*-
"""حجزُ المهامّ على طريقة ``ir.cron`` — والتقديم قبل العمل لا بعده.

═══ العطب الذي عولج ═══

كان الترتيب: تُشغَّل المهمّة ← يُكتب ``next_run``. وفشلُ تلك
الكتابة — قفلُ قاعدةٍ أو انهيار — يترك المهمّة **مستحقّةً وعملُها
قد تمّ**. فتُعاد.

ومسحٌ يستغرق اثنتي عشرة دقيقة يُعاد كاملاً، فيطيل احتكار القاعدة،
فتفشل الكتابة ثانيةً: حلقةٌ تُغذّي نفسها. وظهرت بـ«القاعدة مقفلة»
على أربع مهامّ دفعةً واحدة.

═══ وترتيب أودو ═══

``ir.cron`` يقدّم ``nextcall`` داخل معاملة الحجز، **قبل** تشغيل
الإجراء. فالانهيار بعدها يعني تفويت دورة — لا إعادتها أبداً.
وتفويتُ دورةٍ أهون بكثير من دورةٍ تتكرّر بلا نهاية.

═══ والحجز بقفل صفّ ═══

``FOR UPDATE SKIP LOCKED``: عمليةٌ تحجز والأخرى تتخطّى فوراً.
وهو ما يمنع التشغيل المزدوج **عبر الحاويات** — بخلاف الذاكرة
داخل العملية، فحاوية الويب وحاوية المجدول ذاكرتان منفصلتان.

═══ والفخّ بعد الإصلاح ═══

تقديمٌ مزدوج: في الحجز وفي التسجيل معاً. فمهمّة الساعة تصير كل
ساعتين — تعمل نصف ما ينبغي، بلا خطأ ولا أثرٍ في السجلّ.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from tests_helpers import Checks, body_of, code_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

CRON = ROOT / "web" / "dashboard" / "cron.py"
code = code_of(CRON)


# ═══════════ ١) الحجز موجود ويُستعمل ═══════════
c("١ ‎claim_due‎ معرَّفة", "def claim_due" in code)
run_due = body_of(CRON, "run_due")
c("  و‎run_due‎ يحجز لا يقرأ",
  "claim_due()" in run_due and "due_jobs()" not in run_due, run_due[:120])
# ``due_jobs`` تبقى للعرض والتشخيص — حذفُها يكسر الشاشة
c("  و‎due_jobs‎ باقية للعرض", "def due_jobs" in code)


# ═══════════ ٢) التقديم قبل التشغيل ═══════════
claim = body_of(CRON, "claim_due")
c("٢ الحجز يقدّم الموعد", "next_run = advance(" in claim, claim[:200])
c("  ويسجّل وقت التشغيل", "last_run_at" in claim)
c("  ويحفظ الحقلين وحدهما",
  'update_fields=["next_run", "last_run_at"]' in claim, claim[:400])
# ═══ والمعاملة قصيرة ═══
#
# أودو يُبقي القفل طوال التنفيذ. وهنا لا: مسحٌ باثنتي عشرة دقيقة
# يُبقي معاملةً مفتوحة تلك المدّة — وهي وصفة الاحتكار نفسه.
c("  والتنفيذ خارج المعاملة",
  "transaction.atomic" in claim and "run_job" not in claim)


# ═══════════ ٣) قفل الصفّ حين يُدعَم ═══════════
c("٣ يستعمل ‎skip_locked‎", "skip_locked=True" in claim)
# ═══ و‏SQLite لا يدعمه ═══
#
# واشتراطُه يجعل الجدولة تنهار محلّياً بـ``NotSupportedError``.
c("  ويسأل عن الدعم أوّلاً",
  "has_select_for_update_skip_locked" in claim)
c("  ولا يشترطه", "if skip_locked" in claim)
# وفشلُ الحجز لا يُشغّل شيئاً: المستحقّ يبقى مستحقّاً
c("  وفشل الحجز يعيد فراغاً", "return []" in claim)
c("  ولا يرمي", "except Exception" in claim)


# ═══════════ ٤) لا تقديم مزدوج ═══════════
fin = body_of(CRON, "_finish")
c("٤ التسجيل لا يقدّم الموعد",
  'fields["next_run"] = advance(' not in fin, "ما زال يقدّم")
# ═══ إلّا التخطّي ═══
#
# هناك لم يجرِ عمل، فالتعجيل مقصود: مهمّة تُتخطّى تُعاد بعد
# دقائق لا بعد فترتها كاملة.
c("  والتخطّي وحده يُعيد الضبط",
  'fields["next_run"] = _retry_at(job)' in fin)


# ═══════════ ٥) اللحاق: مرّةً لا ستّين ═══════════
#
# مهمّةٌ كل دقيقة توقّفت ساعةً: أودو يقفز ``nextcall`` بفتراتٍ
# كاملة حتى يتجاوز الآن، فتعمل **مرّة**. والبديل ستّون تشغيلاً
# متتابعاً يخنق الخادم لحظة عودته.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("_cron_probe", CRON)
_mod = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_mod)
    _loaded = True
except Exception as exc:  # noqa: BLE001
    _loaded = False
    c("٥ تحميل الوحدة", False, f"{type(exc).__name__}: {str(exc)[:70]}")

if _loaded:
    NOW = datetime(2026, 9, 22, 12, 0, tzinfo=tz.utc)

    def job(minutes: int, last: datetime):
        return SimpleNamespace(interval_seconds=minutes * 60, next_run=last)

    # فات ستّون دورة
    nxt = _mod.advance(job(1, NOW - timedelta(hours=1)), now=NOW)
    c("٥ اللحاق يتجاوز الآن", nxt > NOW, str(nxt))
    c("  ولا يتجاوزه إلّا بفترة",
      (nxt - NOW) <= timedelta(minutes=1), str(nxt - NOW))
    # ═══ والإيقاع محفوظ ═══
    #
    # التقدّم من الموعد المقرَّر لا من لحظة الانتهاء: مهمّةُ ساعةٍ
    # تستغرق دقيقتين تصير كل ساعة ودقيقتين ثمّ كل ساعة وأربع.
    base = NOW - timedelta(minutes=30)
    n2 = _mod.advance(job(60, base), now=NOW)
    c("  والإيقاع لا ينجرف", n2 == base + timedelta(minutes=60), str(n2))
    # وموعدٌ في المستقبل لا يُمسّ
    fut = NOW + timedelta(minutes=5)
    c("  والمستقبل لا يُقدَّم",
      _mod.advance(job(15, fut), now=NOW) == fut)
    # وقفزةٌ واحدة على الأقلّ ولو حلّ الموعد للتوّ
    c("  وقفزةٌ واحدة على الأقلّ",
      _mod.advance(job(15, NOW), now=NOW) > NOW)


# ═══════════ ٦) الذاكرة المحلّية صارت ثانوية ═══════════
#
# تبقى حزاماً داخل العملية الواحدة — ويُذكر حدُّها صراحةً كي لا
# يُظنّ أنّها تحرس ما لا تحرسه.
c("٦ الذاكرة المحلّية باقية", "_ran_at" in code)
_raw = CRON.read_text(encoding="utf-8")
c("  وحدُّها مكتوب", "لا تعبر الحاويات" in _raw)
c("  و‎claim_due‎ مذكورٌ سببه", "أودو" in _raw)


sys.exit(c.report())
