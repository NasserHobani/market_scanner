# -*- coding: utf-8 -*-
"""‏Together — «عند الطلب فقط» وعدٌ لا يحرس نفسه.

═══ لماذا لا يكفي أن أنوي ═══

«لن أناديه إلّا بزرّ» نيّةٌ صحيحة، ويكسرها سطرٌ واحد بعد أشهر:
حلقةٌ تنادي المحلّل لكل رمز، أو زرٌّ يُضغط مرّتين، أو صفحةٌ تُعاد
كل عشرين ثانية وفيها نداءٌ نُسي خلف شرط.

ولا شيء يقول إنّ ذلك وقع — حتى تصل الفاتورة.

فالحراسة ثلاثٌ، وكلٌّ منها مفحوصة هنا:

    ١. سقفٌ ماليّ يُفحَص **قبل** الإرسال
    ٢. لا يُستورَد من ``cron.py`` ولا من أيّ معالج مهمّة
    ٣. لا يُختار في أيّ مسار ارتدادٍ تلقائيّ

═══ والفحص الثاني هو الأهمّ ═══

الأوّل يحدّ الضرر، والثاني يمنعه. ومن أضاف غداً استيراداً في
معالج مهمّة يسقط هذا الفحص قبل أن يُنشَر.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.ai_advisor import spend as S  # noqa: E402
from scanner.ai_advisor.providers import together_provider as TP  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


# ═══════════ ١) التكلفة تُحسب ═══════════
cost = S.estimate_cost("openai/gpt-oss-120b", 1_000_000, 1_000_000)
c("١ السعر يُطبَّق", abs(cost - 0.75) < 1e-6, str(cost))
c("  والصفر صفر", S.estimate_cost("openai/gpt-oss-120b", 0, 0) == 0.0)
# ═══ والسعر قابلٌ للتعديل ═══
#
# أسعار المزوّدين تتغيّر، وتثبيتُها في الكود يجعل الرقم يكذب بصمت.
c("  والسعر من البيئة",
  "AI_PRICE_IN" in code_of(ROOT / "scanner" / "ai_advisor" / "spend.py"))
c("  وتاريخه معلن", "PRICES_AS_OF" in code_of(
    ROOT / "scanner" / "ai_advisor" / "spend.py"))


# ═══════════ ٢) السقف يُفحَص قبل الإرسال ═══════════
ssrc = source_of(ROOT / "scanner" / "ai_advisor" / "spend.py")
scode = code_of(ROOT / "scanner" / "ai_advisor" / "spend.py")
c("٢ فحصٌ قبليّ موجود", "def check_budget" in scode)
c("  والسبب مكتوب", "دفتر محاسبةٍ لا حارس" in ssrc)

tcode = code_of(ROOT / "scanner" / "ai_advisor" / "providers"
                / "together_provider.py")
# ═══ قبل الإرسال لا بعده ═══
_body = tcode.split("def complete")[1][:2200] if "def complete" in tcode else ""
c("  ويُنادى قبل الطلب",
  ("check_budget" in _body and "urlopen" in _body
   and _body.index("check_budget") < _body.index("urlopen")), _body[:160])

# والسقف الواحد يمنع نداءً ضخماً
os.environ["AI_PER_CALL_USD"] = "0.001"
try:
    S.check_budget("openai/gpt-oss-120b", 1_000_000, 1_000_000)
    c("  والنداء الضخم يُرفَض", False, "مرّ!")
except S.BudgetExceeded as exc:
    c("  والنداء الضخم يُرفَض", True)
    c("  والرسالة تقول ما يُفعل", "AI_PER_CALL_USD" in str(exc), str(exc)[:80])
finally:
    os.environ.pop("AI_PER_CALL_USD", None)

# والصغير يمرّ
os.environ["AI_PER_CALL_USD"] = "1"
try:
    S.check_budget("openai/gpt-oss-120b", 1000, 500)
    c("  والصغير يمرّ", True)
except S.BudgetExceeded as exc:
    c("  والصغير يمرّ", False, str(exc)[:80])
finally:
    os.environ.pop("AI_PER_CALL_USD", None)

# ═══ والافتراض منخفض ═══
#
# سقفٌ كبير منسيّ لا يحرس شيئاً.
lim = S.limits()
c("  والافتراض اليوميّ متحفّظ", lim["daily_usd"] <= 5.0, str(lim))


# ═══════════ ٣) لا نداءَ من جدولة ═══════════
#
# وهذا الفحص هو الذي يمنع العطب لا يحدّه.
cron = code_of(ROOT / "web" / "dashboard" / "cron.py")
for bad in ("together", "TOGETHER"):
    c(f"٣ لا «{bad}» في cron", bad not in cron, "استُورد في الجدولة!")

# ولا في أيّ معالج أو أمرٍ مجدول
for mod in ("web/dashboard/wallet_monitor.py",
            "web/dashboard/monitor.py",
            "web/dashboard/management/commands/run_jobs.py",
            "web/dashboard/management/commands/scan.py"):
    p = ROOT / mod
    if p.exists():
        c(f"  ولا في {Path(mod).name}",
          "together" not in code_of(p).lower())

# ═══ ولا يُختار تلقائياً ═══
#
# مزوّدٌ مدفوع يُنادى بخطأٍ في الاختيار أسوأ من مزوّدٍ غائب.
reg = source_of(ROOT / "scanner" / "ai_advisor" / "provider_registry.py")
c("  ويُسجَّل بمعرّفه", "create_together_provider" in reg)
c("  ولا يصير افتراضياً", "يُسجَّل ولا يصير افتراضياً" in reg)
cfg = code_of(ROOT / "scanner" / "ai_advisor" / "provider_config.py")
c("  ولا في الارتداد", "together" not in cfg.lower())


# ═══════════ ٤) الوحدات من الردّ لا تُخمَّن ═══════════
#
# تقديرُها بعدّ الحروف يخطئ بثلاثين بالمئة على العربية — ويُقرأ
# كأنّه دقيق.
c("٤ ‎usage‎ يُقرأ من الردّ", "prompt_tokens" in tcode
  and "completion_tokens" in tcode)
tsrc = source_of(ROOT / "scanner" / "ai_advisor" / "providers"
                 / "together_provider.py")
c("  والسبب مكتوب", "يخطئ بثلاثين بالمئة" in tsrc)
c("  والتقدير للسقف وحده", "للسقف وحده لا للفوترة" in tsrc)
# وسقفٌ على المخرجات: حارسٌ ثانٍ
c("  وسقفٌ للمخرجات", "DEFAULT_MAX_TOKENS" in tcode)
# والردّ غير الصالح لا يُرمى: دُفع ثمنه
c("  والردّ المعطوب يُعاد", '"_raw"' in tcode)
c("  وسببه", "دفعت ولم ترَ شيئاً" in tsrc)


# ═══════════ ٥) كلّ نداءٍ يُسجَّل ═══════════
with tempfile.TemporaryDirectory() as tmp:
    old = S.LEDGER
    S.LEDGER = str(Path(tmp) / "x.jsonl")
    try:
        # ``_path`` يبني من الجذر — فالاختبار على الدالّة لا الملفّ
        row = S.record(provider="together", model="openai/gpt-oss-120b",
                       tokens_in=1000, tokens_out=500, purpose="t")
        c("٥ السطر يحمل التكلفة", row["cost"] > 0, str(row["cost"]))
        c("  والوحدات", row["tokens_in"] == 1000 and row["tokens_out"] == 500)
        c("  والوقت", "at" in row and len(row["at"]) >= 19)
        c("  والغرض", row["purpose"] == "t")
    finally:
        S.LEDGER = old

c("  والملخّص يعدّ اليوم والشهر",
  all(k in S.summary() for k in ("today_usd", "month_usd", "limits")))
# والسطر المبتور لا يُسقط السجلّ
c("  والمبتور يُتخطّى", "continue" in scode and "except ValueError" in scode)


# ═══════════ ٦) الواجهة تعرض الثمن ═══════════
v = code_of(ROOT / "web" / "dashboard" / "together_views.py")
c("٦ الحال بلا نداءٍ مدفوع", "def api_together_health" in v)
c("  والنداء في خيط", "threading.Thread" in v)
c("  وواحدٌ في وقتٍ واحد", 'v["state"] == "running"' in v)
c("  والغرض محصور", "PURPOSES" in v and "غرض غير معروف" in v)
c("  وحدٌّ على المُدخَل", "24000" in v)
# ولا يُرسَل نصٌّ حرّ من المتصفّح نظاماً
c("  والنظام من الخادم", "SYSTEM_AR" in v)
c("  ولا يوصي بشراء", "ولا توصي بشراءٍ أو بيع" in source_of(
    ROOT / "web" / "dashboard" / "together_views.py"))

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "together-ask.js").read_text(encoding="utf-8")
c("  والمتبقّي معروض", "day_left" in js or "daily_usd" in js)
c("  والتقدير قبل النتيجة", "estimate_usd" in js)
c("  والفعليّ بعدها", "u.cost" in js)
# ═══ والحمولة تُبنى عند الضغط ═══
#
# بناؤها عند التركيب يرسل ما كان عند فتح الصفحة لا ما يراه الآن.
sj = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "study-page.js").read_text(encoding="utf-8")
c("  والحمولة دالّة", "payload: askPayload" in sj)
c("  والملخَّص لا الجدول كلّه", "slice(0, 5)" in sj)

u = code_of(ROOT / "web" / "dashboard" / "urls.py")
for p in ("api/ai/together/", "api/ai/together/ask/",
          "api/ai/together/status/"):
    c(f"  والمسار {p}", f'"{p}"' in u)


# ═══════════ ٧) المفتاح يصل الحاوية ═══════════
#
# ضُبط مفتاح Binance في بورتينر ولم يصل — لأنّه لم يُذكر في
# ``environment:``. والعطب نفسه ينتظر كلّ مفتاحٍ جديد.
comp = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
for var in ("TOGETHER_API_KEY", "AI_DAILY_USD", "AI_MONTHLY_USD"):
    c(f"٧ {var} يُمرَّر", comp.count(var) >= 2, f"{comp.count(var)} مرّة")
tpl = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
c("  والقالب يذكره", "TOGETHER_API_KEY=" in tpl)
c("  وبلا قيمة", "TOGETHER_API_KEY=\n" in tpl)


sys.exit(c.report())
