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
c("  وواحدٌ في وقتٍ واحد", "_running_count() >= 1" in v)

# ═══ ٦أ) الحالة على القرص لا في الذاكرة ═══
#
# ‏gunicorn بثلاثة عمّال: الطلب الذي يبدأ النداء يصل عاملاً،
# والاستعلام قد يصل آخر لا يعرف المفتاح — فيردّ ``idle`` أبداً.
# فبدا الزرّ «لا يفعل شيئاً» والنداء يعمل ويُنفَق.
vsrc = source_of(ROOT / "web" / "dashboard" / "together_views.py")
c("٦أ الحالة على القرص", "def _write" in v and "def _read" in v)
c("  والسبب موثَّق", "ثلاثة عمّال" in vsrc)
c("  ولا قاموسٌ في الذاكرة", "_JOBS" not in v, "ما زال في الذاكرة")
# ═══ ومفتاحٌ ثابت ═══
#
# ``hash`` مُعشّى لكل عملية، فالمفتاح يختلف بين عاملٍ وآخر.
c("  والمفتاح ‎sha1‎ لا ‎hash‎",
  "hashlib.sha1" in v and "abs(hash(" not in v)
c("  والكتابة ذرّية", "tmp.replace(path)" in v)
# و‎idle‎ حالةٌ صريحة لا فراغ
c("  و‎idle‎ تُردّ صريحة", '"state": "idle"' in v)
js_idle = js.split('d.state === "idle"')[1][:400] if \
    'd.state === "idle"' in js else ""
c("  والواجهة تعالجها", bool(js_idle), "تمرّ إلى فرع «تمّ»")
c("  ولا تُرسَم نجاحاً", "ضاع أثر الطلب" in js)
# والشارة لا تمتلئ بشَرَطات
c("  والشارة تقول السبب", "تعذّرت قراءة الإنفاق" in js)
# وأداةٌ تقطع الشكّ
doc = ROOT / "tools_doctor_ai.py"
c("  وأداة تشخيص", doc.exists())
if doc.exists():
    dt = source_of(doc)
    c("    تفحص بلا إنفاق", "--live" in dt and "لم يُرسَل شيء" in dt)
    c("    وتفحص مجلّد المهامّ", "قابل للكتابة" in dt)
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

# ═══ والموضع: صفحة الرمز ═══
#
# هناك يُقرأ التحليل، وهناك يُسأل عنه.
sym = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "symbol.html").read_text(encoding="utf-8")
c("  والزرّ في صفحة الرمز", 'id="sym-ai"' in sym)
c("  والسكربت محمَّل", "together-ask.js" in sym)
c("  ورابطٌ إلى السقوف", "/settings/#ai_cost" in sym)
# ═══ والحمولة تُبنى عند الضغط ═══
#
# بناؤها عند التحميل يرسل ما كان عند فتح الصفحة لا ما يراه الآن
# بعد تبديل الفريم.
c("  والحمولة دالّة", "payload: function ()" in sym)
c("  والموضوع يُمرَّر", "subject: DATA.symbol" in sym)


# ═══════════ ٦ج) العرض والحفظ ═══════════
#
# ═══ ما كان ═══
#
# ``JSON.stringify(JSON.parse(text), null, 2)`` يُعيد تهريب
# النصّ، فتظهر ‎\n‎ و‎\"‎ حروفاً على الشاشة: فقرةٌ متلاصقة فيها
# ``•n\.`` و``\"الدرجة\"``. وهو ما رآه المستخدم.
c("٦ج لا تهريبٌ مزدوج",
  "JSON.stringify(JSON.parse(text)" not in js, "ما زال يُعاد تهريبه")
c("  والإجابة تُرسَم أقساماً", "function renderAnswer" in js
  and "function section" in js)
c("  والمصفوفة قائمة", "Array.isArray(v)" in js)
c("  والنصّ يُفكَّك بالأسطر", "split(/\\r?\\n+" in js)
# ═══ والمضادّ قبل المؤيّد ═══
#
# ما يُقرأ أوّلاً يُوزن أكثر، والانحياز الطبيعيّ نحو التأكيد.
_ord = js.split("var ORDER")[1][:120] if "var ORDER" in js else ""
c("  و«يضعف» قبل «يدعم»",
  _ord.index("يضعف") < _ord.index("يدعم")
  if ("يضعف" in _ord and "يدعم" in _ord) else False, _ord[:80])
# ═══ والردّ المخالف لا يُرمى ═══
#
# كلّفك مالاً فعلاً.
c("  والمخالف يُعرَض نصّاً", "لم يلتزم النموذج" in js)

# ═══ ومخطَّطٌ ثابت ═══
#
# بلا حقولٍ محدّدة يخترع النموذج حقولاً في كل مرّة ونصوصاً فيها
# ‎\n‎ داخل السطر — فتعذّر عرضُها إلّا خاماً.
for fld in ("الخلاصة", "يدعم", "يضعف", "ما_لا_نعرفه"):
    c(f"  والحقل «{fld}» مطلوب", fld in vsrc)
c("  والبنود مصفوفات", "القائمة تتكفّل بذلك" in vsrc)


# ═══════════ ٦د) كلّ إجابةٍ تُحفَظ ═══════════
#
# إجابةٌ تُعرَض ثمّ تُفقَد بإغلاق التبويب تعني أنّك دفعت مرّتين
# للسؤال نفسه — وهو نقيض «عند الطلب فقط».
from scanner.ai_advisor import archive as A  # noqa: E402

asrc = source_of(ROOT / "scanner" / "ai_advisor" / "archive.py")
acode = code_of(ROOT / "scanner" / "ai_advisor" / "archive.py")
c("٦د الأرشيف موجود", "def save" in acode and "def list_for" in acode)
c("  والسبب مكتوب", "دفعت مرّتين للسؤال نفسه" in asrc)
# ═══ ومنفصلٌ عن سجلّ المال ═══
#
# إثقالُ السجلّ المحاسبيّ بالنصوص يجعل كل حساب ميزانية يقرأ
# ميغابايتات.
c("  ومنفصل عن الإنفاق", A.ARCHIVE != S.LEDGER)
c("  وسببه", "سجلٌّ محاسبيّ" in asrc)
c("  ويُحفَظ عند النجاح", "archive.save(" in v)
c("  والفشل لا يُضيّع الإجابة",
  "تعذّرت أرشفة الإجابة" in v)
c("  ويُرشَّح بالرمز", "def list_for" in acode and "subject" in acode)
c("  وسقفٌ للملفّ", "MAX_ROWS" in acode and "def _trim" in acode)
c("  والقصّ بالعدّ لا بالحجم", "القصّ بالعدّ لا بالحجم" in asrc)
# ولا مفاتيح في الأرشيف
c("  ولا أسرار فيه",
  "api_key" not in acode.lower() and "token\"" not in acode.lower())

c("  ونقطةُ قراءة", "def api_together_history" in v)
c("  وبلا نداءٍ مدفوع", "لا نداءَ مدفوع هنا" in vsrc)
_u = code_of(ROOT / "web" / "dashboard" / "urls.py")
c("  ومسجَّلة", '"api/ai/together/history/"' in _u)
c("  والشاشة تعرضها", "mountHistory" in js and "sym-ai-history" in sym)

# والأرشيف يعمل فعلاً — لا بقراءة المصدر وحدها
_row = A.save(subject="TESTUSDT", purpose="symbol", model="m",
              answer='{"الخلاصة":"ت"}', question="س", cost=0.0001,
              tokens_in=10, tokens_out=5)
c("  والحفظ يعيد معرّفاً", bool(_row.get("id")), str(_row)[:80])
_got = A.list_for("TESTUSDT")
c("  والقراءة تجده", any(r["id"] == _row["id"] for r in _got),
  str(len(_got)))
c("  وبلا نصّ السؤال", all("question" not in r for r in _got))
c("  والمفرد يحمل الإجابة",
  (A.get(_row["id"]) or {}).get("answer") == '{"الخلاصة":"ت"}')
c("  ورمزٌ آخر لا يراه", not A.list_for("LAYOUJADUSDT"))

u = code_of(ROOT / "web" / "dashboard" / "urls.py")
for p in ("api/ai/together/", "api/ai/together/ask/",
          "api/ai/together/status/"):
    c(f"  والمسار {p}", f'"{p}"' in u)


# ═══════════ ٦ب) السقوف في شاشة الإعدادات ═══════════
#
# متغيّر بيئةٍ يحتاج إعادة نشرٍ لتعديله. والسقف الماليّ يُضبط
# بالتجربة — فمكانه الشاشة.
sch = code_of(ROOT / "scanner" / "settings_schema.py")
for key in ("ai_together_enabled", "ai_model", "ai_daily_usd",
            "ai_monthly_usd", "ai_per_call_usd", "ai_price_in",
            "ai_price_out", "ai_max_tokens"):
    c(f"٦ب {key} في المخطّط", f'"{key}"' in sch)

# ═══ والأسبقية: الشاشة ثمّ البيئة ═══
c("  والشاشة تسبق البيئة", "def _setting" in scode and "_env(" in scode)
c("  والترتيب موثَّق", "شاشة الإعدادات ← متغيّر البيئة ← الافتراض" in ssrc)
c("  ولا ترمي القراءة", "except Exception" in scode)
# ═══ ومفتاح إيقافٍ واحد ═══
c("  ومفتاح إيقاف", "def enabled" in scode)
# والفحص داخل ``complete`` — قبل المفتاح وقبل السقف، فما بعده يكلّف
c("  ويُفحَص أوّلاً",
  ("spend.enabled()" in _body and "check_budget" in _body
   and _body.index("spend.enabled()") < _body.index("check_budget")),
  _body[:140])

# ═══ والمفتاح لا يُحفَظ في الشاشة ═══
#
# ما يُحفظ هناك يدخل قاعدة البيانات، وهي تُنسَخ في ``scanner.dump``
# عند كل ترحيل — فمفتاحٌ هنا يسافر في كل نسخةٍ احتياطية.
c("  والمفتاح ليس حقلاً", "TOGETHER_API_KEY" not in sch
  and "together_api_key" not in sch.lower())
c("  والسبب مكتوب",
  "تُنسَخ في ‎scanner.dump‎" in source_of(
      ROOT / "scanner" / "settings_schema.py"))


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
