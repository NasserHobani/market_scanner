# -*- coding: utf-8 -*-
"""سجلّ رصد ‏PES — وثلاثة أعطال تجعل السجلّ يكذب وهو يعمل.

═══ الأوّل: التكرار ═══

المسح يعمل كل ربع ساعة. ورمزٌ يبقى ‏PRE_BREAKOUT ثلاثة أيّام
يُنتج ٢٨٨ صفّاً لو سُجّل في كل دورة — فتصير «نسبة النجاح» نسبةَ
الرموز البطيئة لا نسبةَ الإشارات. والعطب لا يظهر: الجدول ممتلئ
والأرقام تُحسب.

═══ الثاني: النظر إلى المستقبل ═══

قياس المسار من شمعة الرصد **نفسها** — وهي جارية لحظة القرار —
يسرّب ما لم يكن معروفاً. وتسريبٌ بشمعةٍ واحدة يكفي ليجعل أيّ
نسبةٍ تبدو ممتازة.

═══ الثالث: عدُّ الجاري فشلاً ═══

الرصد الحديث لم يُقَس بعد. وعدُّه «لم ينفجر» يخفض كل نسبةٍ بمقدار
ما هو حديث — فتبدو الاستراتيجية تسوء كلّما مسحتَ أكثر، وهي لم
تتغيّر.
"""
from __future__ import annotations

import ast
import sys
from datetime import datetime, timedelta, timezone as tz
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


HIST = ROOT / "web" / "dashboard" / "pes_history.py"
src = HIST.read_text(encoding="utf-8")
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
tree = ast.parse(src)


def _body(name: str) -> str:
    """جسدُ دالّةٍ بلا تعليقاتها ولا سلسلة توثيقها.

    ═══ لماذا هذا لازم ═══

    الفحص على النصّ الخام يطابق **الشرح** لا الكود. ووقع ذلك هنا
    مرّتين: فحصٌ يبحث عن ``get_or_create`` بقي أخضر بعد أن أُزيلت
    الدالّة، لأنّ اسمها ظلّ مذكوراً في تعليقٍ يصف ما كان.

    وفحصٌ يطابق التوثيق يمرّ دائماً — وهو أسوأ من غيابه، لأنّه
    يشتري طمأنينةً بلا ثمن.
    """
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    seg = ast.get_source_segment(src, fn) or ""
    doc = ast.get_docstring(fn, clean=False)
    if doc:
        seg = seg.replace(doc, "", 1)
    return "\n".join(l for l in seg.splitlines()
                      if not l.strip().startswith("#"))


# ═══════════ ١) التكرار ممنوع بحزامين ═══════════
#
# المنطق يمنعه، والقيد في القاعدة يمنعه ولو عمل ماسحان معاً —
# وقد حدث فعلاً: محرّك الخادم والأمر الخارجي في اللحظة نفسها.
# ═══ القياس داخل الدالّة لا على الملفّ ═══
#
# النسخة الأولى بحثت عن ``get_or_create`` في نصّ الملفّ كلّه —
# فبقيت خضراء بعد أن أُزيلت الدالّة، لأنّ اسمها ظلّ مذكوراً في
# **شرحٍ** يصف ما كان. فحصٌ يطابق التوثيق لا الكود يمرّ دائماً.
rec = _body("record")
check("١ المفتاح يشمل شمعة القرار",
      "candle_time=ct" in rec and "state=state" in rec)

# ═══ الكتابة دفعةً لا صفّاً صفّاً ═══
#
# ‏SQLite يسمح بكاتبٍ واحد. و``get_or_create`` لكل رمز يعني مئات
# الأقفال المتتابعة في كل دورة مسح — وهو ما أوقع «القاعدة مقفلة»
# على أربع مهامّ دفعةً واحدة.
check("  والكتابة دفعةً واحدة", "bulk_create" in rec)
check("  في معاملةٍ واحدة", "transaction.atomic()" in rec)
check("  ولا get_or_create لكل صفّ", "get_or_create" not in rec)
check("  ولا save() داخل الحلقة", ".save(" not in rec)
# والموجود يُستبعَد قبل الكتابة، وإلّا صار العدد المُبلَّغ كاذباً
check("  والموجود يُستبعَد أوّلاً", "values_list" in rec and "have" in rec)
check("  ويُعاد عدد الجديد فقط", "return len(new)" in rec)
check("  وignore_conflicts حزامٌ ثانٍ", "ignore_conflicts=True" in rec)

models = (ROOT / "web" / "dashboard" / "models.py").read_text(encoding="utf-8")
check("  وقيدٌ فريد في النموذج", "uniq_pes_detection" in models)
mig = (ROOT / "web" / "dashboard" / "migrations"
       / "0019_pesdetection.py").read_text(encoding="utf-8")
check("  وفي الهجرة أيضاً", "uniq_pes_detection" in mig)
check("  على الحقول الأربعة",
      '"symbol", "market", "state", "candle_time"' in models)


# ═══════════ ١ب) المتابعة لا تحتكر القاعدة ═══════════
#
# أوّل نسخةٍ نادت ``det.save()`` لكل صفّ. فلمّا بلغ السجلّ ٦٥٩
# صفّاً صار كل تشغيلٍ ٦٥٩ معاملةَ كتابةٍ متتابعة على قاعدةٍ يكتب
# فيها المسحُ والحسمُ والمزامنة معاً — وهي العلّة المقيسة.
fu = _body("follow_up")
check("١ب المتابعة تكتب دفعات", "bulk_update" in fu)
check("  ولا save() لكل صفّ", ".save(" not in fu)
check("  وبسقفٍ لكل تشغيل", "MAX_PER_RUN" in code)
check("  والسقف محدود", 0 < int(code.split("MAX_PER_RUN = ")[1]
                                .split("\n")[0]) <= 1000)
check("  والدفعة محدودة", 0 < int(code.split("BATCH = ")[1]
                                  .split("\n")[0]) <= 500)
# والأقدم أوّلاً: عكسُه يترك أقدم الصفوف بلا متابعةٍ أبداً
check("  والأقدم أوّلاً", 'order_by("id")' in fu)
check("  وفشل الكتابة لا يرمي", "def _flush" in fu and "OperationalError" in fu)
check("  ويُبلَّغ عمّا لم يُتابَع", '"pending"' in fu)


# ═══════════ ٢) لا نظر إلى المستقبل ═══════════
wf = _body("_walk_forward")
# ‏> لا ‎>=‎: شمعة الرصد كانت جارية لحظة القرار
check("٢ القصّ بـ ‎>‎ لا ‎>=‎", "idx > cut" in wf, wf[wf.find("after ="):][:60])
check("  ولا ‎>=‎ في القصّ", "idx >= cut" not in wf)

# والقياس الفعليّ: شمعةٌ ضخمة **عند** لحظة الرصد يجب ألّا تُحتسب
sys.modules.setdefault("django", SimpleNamespace())


def _series(n=120, start="2024-01-01"):
    idx = pd.date_range(start, periods=n, freq="4h", tz="UTC")
    close = np.full(n, 100.0)
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": np.full(n, 1e3)},
                        index=idx)


# نُعيد بناء ‎_walk_forward‎ بمعزلٍ عن Django لاختبار منطقه وحده
ns: dict = {}
exec(compile(ast.Module(
    body=[n for n in tree.body
          if isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign))
          or (isinstance(n, ast.FunctionDef)
              and n.name in ("_walk_forward", "_tz_aware", "_parse_dt",
                             "wilson", "summarize"))],
    type_ignores=[]), "<hist>", "exec"), ns)

df = _series()
mark = df.index[60]
# قفزةٌ ‎+50٪‎ **في** شمعة الرصد نفسها — يجب ألّا تُحسب
df.loc[mark, ["high", "close"]] = 150.0
det = SimpleNamespace(candle_time=mark, price=100.0, resistance=None)
path = ns["_walk_forward"](df, det)
check("  وقفزة شمعة الرصد لا تُحتسب",
      path.get("max_gain", 0) < 1.0, str(path.get("max_gain")))

# بينما قفزةٌ **بعدها** تُحتسب
df2 = _series()
df2.loc[df2.index[62], ["high", "close"]] = 130.0
path2 = ns["_walk_forward"](df2, det)
check("  وقفزة ما بعدها تُحتسب",
      abs(path2.get("max_gain", 0) - 30.0) < 0.01, str(path2.get("max_gain")))
check("  ويُسجَّل متى بلغها",
      path2.get("hours_to_max") == 8.0, str(path2.get("hours_to_max")))


# ═══════════ ٣) المدى محدود ولا يتجاوزه ═══════════
#
# حركةٌ بعد شهرين لا تُنسب إلى إشارةٍ عمرها شهران.
far = _series(n=400)
far.loc[far.index[300], ["high", "close"]] = 500.0
p3 = ns["_walk_forward"](far, SimpleNamespace(
    candle_time=far.index[60], price=100.0, resistance=None))
check("٣ ما بعد المدى لا يُحتسب",
      p3.get("max_gain", 0) < 1.0, str(p3.get("max_gain")))
check("  والمدى ١٤ يوماً", "HORIZON_DAYS = 14" in code)
# ١٤ يوماً على 4H = ٨٤ شمعة
check("  أي ٨٤ شمعة", p3.get("bars") == 84, str(p3.get("bars")))


# ═══════════ ٤) التراجع قبل القمّة لا بعدها ═══════════
#
# ارتفاعٌ ‎+20٪‎ سبقه نزولٌ ‎-15٪‎ لا يُدرَك: الوقف يضربك قبله.
dd = _series()
dd.loc[dd.index[62], "low"] = 85.0          # نزول قبل القمّة
dd.loc[dd.index[65], ["high", "close"]] = 120.0
dd.loc[dd.index[70], "low"] = 60.0          # نزولٌ **بعد** القمّة
p4 = ns["_walk_forward"](dd, det)
check("٤ التراجع يُقاس قبل القمّة",
      abs(p4.get("drawdown", 0) + 15.0) < 0.01, str(p4.get("drawdown")))


# ═══════════ ٥) العتبة تتحرّك فعلاً ═══════════
def _fake(gain, outcome="settled"):
    return SimpleNamespace(outcome=outcome, max_gain_pct=gain,
                           hours_to_max=10.0, max_drawdown_pct=-3.0,
                           broke_resistance=False, volatility_expanded=False,
                           state="WATCH", state_label="للمراقبة")


rows = [_fake(g) for g in (2, 4, 6, 9, 12, 18, 25)]
s3 = ns["summarize"](rows, 3.0)
s10 = ns["summarize"](rows, 10.0)
s20 = ns["summarize"](rows, 20.0)
check("٥ العتبة ٣٪ تعطي نسبةً أعلى", s3["rate"] > s10["rate"] > s20["rate"],
      f"{s3['rate']} · {s10['rate']} · {s20['rate']}")
check("  والحساب صحيح", s10["hits"] == 3 and s10["settled"] == 7,
      f"{s10['hits']}/{s10['settled']}")
# ولا عمود «نجح» مخزَّن: العتبة تُحسب عند العرض
check("  ولا حكمٌ مخزَّن في النموذج",
      "succeeded" not in models and "exploded" not in models)
check("  ولا عمود نسبة", "success_rate" not in models)


# ═══════════ ٦) الجاري ليس فشلاً ═══════════
mixed = [_fake(20), _fake(1), _fake(None, "watching"), _fake(None, "watching")]
s = ns["summarize"](mixed, 8.0)
check("٦ الجاري خارج النسبة", s["settled"] == 2, str(s["settled"]))
check("  والنسبة ٥٠٪ لا ٢٥٪", s["rate"] == 50.0, str(s["rate"]))
check("  ويُعدّ منفصلاً", s["watching"] == 2)
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "pes-history-page.js").read_text(encoding="utf-8")
check("  والشاشة تفرّقه بنصّ", "قيد المتابعة" in js
      and "لم يُقَس بعد" in js)


# ═══════════ ٧) العيّنة الرقيقة تُعلَن ═══════════
thin = ns["summarize"]([_fake(20), _fake(20), _fake(1)], 8.0)
check("٧ يُعلَن رقّة العيّنة", thin["thin"] is True)
lo, hi = thin["ci_low"], thin["ci_high"]
# ‏٢ من ٣ = ٦٧٪، وفترتها واسعة جدّاً — وهذا ما يجب أن يُرى
check("  والفترة واسعة", hi - lo > 50, f"{lo}–{hi}")
check("  و Wilson لا Wald", "Wilson" in src and "def wilson" in code)
check("  والشاشة تعرض التحذير", "أرقّ من أن تُقرأ" in js)
check("  وتعرض الفترة دائماً", "فترة الثقة" in js)


# ═══════════ ٨) سعر الرصد من شمعة القرار ═══════════
#
# ``close`` إغلاقُ الشمعة الجارية لحظة المسح — وقد تحرّك عن
# الموضع الذي بُني عليه القرار.
scan = (ROOT / "scanner" / "strategies" / "pes_scan.py").read_text(
    encoding="utf-8")
check("٨ المسح يحفظ شمعة القرار", '"candle_time"' in scan)
check("  وسعرها", '"decision_close"' in scan)
check("  ومن الشمعة المغلقة", 'index[-2]' in scan and 'iloc[-2]' in scan)
check("  والتسجيل يفضّلها", 'r.get("decision_close")' in code)


# ═══════════ ٩) التسجيل والمتابعة مربوطان بالمسح ═══════════
cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
check("٩ يُسجَّل مع المسح", "pes_history.record" in cron)
check("  ويُتابَع معه", "pes_history.follow_up" in cron)
# فشل التسجيل لا يُسقط المسح: النتائج معروضة والسجلّ يُستدرَك
check("  وفشله لا يُسقط المسح", "تعذّر تسجيل رصد PES" in cron)
check("  والمرفوض يُسجَّل أيضاً",
      "LATE_MOMENTUM" in code and "ALREADY_EXPANDED" in code)


# ═══════════ ١٠) الصفحة والمسار ═══════════
urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
check("١٠ المسار مسجَّل", "pes/history/" in urls)
check("  والصفحة في الشريط",
      "pes_history" in (ROOT / "web" / "dashboard"
                        / "context_processors.py").read_text(encoding="utf-8"))
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "pes_history.html").read_text(encoding="utf-8")
check("  والعتبة حقلٌ لا ثابت", 'id="f-threshold"' in tpl)
check("  وتُطبَّق عند الإدخال", 'addEventListener("input"' in js)
check("  ومنحنى العتبات معروض", '"curve"' in
      (ROOT / "web" / "dashboard"
       / "pes_history_views.py").read_text(encoding="utf-8"))


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
