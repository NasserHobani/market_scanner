# -*- coding: utf-8 -*-
"""نموذج التنبؤ: مصدر التسمية، وبوّابة الترقية، واسم المحرّك.

═══ ما شُخِّص ═══

‏LightGBM «غير متاح» ليس عطباً في النموذج بل جوعاً في البيانات::

    صفقات محسومة                 298
    منها مربوطة بلقطة ميزات       29
    صفوف مؤهّلة للتدريب           13   (المطلوب 100)
    وتيرة الربط                 0.7/يوم → نحو 120 يوماً

والـ٢٦٩ الباقية لا تُستردّ: أُنشئت قبل أن يعمل الالتقاط، ولا تعرف
من أيّ ميزات وُلدت. وجُرِّبت مطابقتها بالمفتاح الطبيعي (رمز وفريم
ووقت شمعة) فلم تزد عن ١٣.

═══ وما يحرسه هذا الملف ═══

    ١) ألّا تُخلط تسمية المحاكاة بنتيجة الصفقة الحقيقية.
    ٢) ألّا يُسرَّب المستقبل: التسمية من شموعٍ **بعد** القرار.
    ٣) ألّا يُرقَّى نموذجٌ لم يُقَس على صفقاتٍ حقيقية لم يرها.
    ٤) ألّا يُدَّعى LightGBM وهو مصنّفٌ بسيط مكتوب بيد.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── تحميل predictor بلا Django ──
src = (ROOT / "web" / "dashboard" / "predictor.py").read_text(encoding="utf-8")
tree = ast.parse(src)
DJANGO = {"_scan_rows", "_real_rows", "build_datasets"}
keep = [n for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name in DJANGO)]
ns: dict = {"__name__": "predictor"}
exec(compile(ast.Module(body=keep, type_ignores=[]), "p", "exec"), ns)

from scanner.feature_snapshots import tiers  # noqa: E402
from scanner.predictive import dataset_sim  # noqa: E402


# ── ١) الطبقات تقسم العقد بلا بقايا ──
from scanner.feature_snapshots.builder import V3_FEATURE_SPECS  # noqa: E402

names = {n for n, _, _ in V3_FEATURE_SPECS}
core, opt = set(tiers.CORE_FEATURES), set(tiers.OPTIONAL_FEATURES)
check("١ التصنيف يغطّي العقد", core | opt == names,
      str((names - core - opt) | ((core | opt) - names)))
check("  ولا تداخل", not (core & opt), str(core & opt))
# ═══ السقف كان غير قابل للبلوغ ═══
#
# خمس ميزات لا تُحسب أبداً، فأعلى تغطية ‎0.861‎ وحدّ «جيّدة» ‎0.90‎.
# فعدد الجيّدات صفرٌ بنيوياً — لا لعطبٍ في الالتقاط.
check("  والميتة كلّها اختيارية",
      set(tiers.KNOWN_DEAD) <= opt, str(set(tiers.KNOWN_DEAD) - opt))
check("  فالسقف بلغ 1.0", tiers.core_coverage({f: 1 for f in core}) == 1.0)
# وميزةٌ أساسية غائبة تُسقط الأهلية — هذا عطبٌ حقيقي يُحاسَب
part = {f: 1 for f in list(core)[:-3]}
check("  والنقص الأساسي يُسقط الأهلية", not tiers.is_eligible(part),
      str(tiers.core_coverage(part)))
check("  والاختياري لا يُسقطها",
      tiers.is_eligible({f: 1 for f in core}))
check("  وسببُ الغياب محفوظ",
      set(tiers.optional_gaps({}).keys()) == opt)


# ═══ ٢) لا تسرّب: التسمية من بعد القرار ═══
#
# شمعة القرار هي التي بُنيت عليها الميزات. واستعمالها في التسمية
# يقيس النجاح بما عُرف وقت الدخول — فيبدو النموذج ممتازاً في
# الاختبار عاجزاً في السوق.
sim_src = (ROOT / "scanner" / "predictive"
           / "dataset_sim.py").read_text(encoding="utf-8")
code = "\n".join(l for l in sim_src.splitlines()
                 if not l.strip().startswith("#"))
check("٢ الشموع بعد القرار قطعاً", "idx > ts" in code, "شرط غير قاطع؟")
check("  ولا تساوي", "idx >= ts" not in code)
check("  وحدّ أدنى للشموع اللاحقة", "MIN_FORWARD_BARS" in code)
check("  والحدّ معقول", 4 <= dataset_sim.MIN_FORWARD_BARS <= 30,
      str(dataset_sim.MIN_FORWARD_BARS))
# ═══ لا تُخترع تسمية ═══
#
# صفٌّ لم يبلغ هدفاً ولا وقفاً يُستبعد، كما تُستبعد الصفقة
# المعلّقة من الإحصاءات — لا يُعدّ خسارة.
check("  وغير المحسوم يُستبعد", "return None" in code
      and '"هدف", "وقف", "تعادل"' in code)
check("  والقاعدة هي المنفَّذة فعلاً", '"fixed"' in code,
      "تسمية بقاعدة لا تُنفَّذ؟")


# ── ٣) الوسم لا يُخلط ──
check("٣ لمجموعة المحاكاة وسم", dataset_sim.LABEL_SOURCE == "simulated")
check("  ويُكتب في كل صفّ", 'row["label_source"]' in code)
pred_code = "\n".join(l for l in src.splitlines()
                      if not l.strip().startswith("#"))
check("  وللحقيقي وسمه", '"real_trades"' in pred_code)


# ═══ ٤) البوّابة تحكم بالحقيقي ═══
#
# نسبة الفوز في المحاكاة ‎68.4٪‎ وفي الصفقات الحقيقية ‎46.4٪‎.
# فنموذجٌ يُقاس على المحاكاة وحدها يُرقَّى بثقةٍ لا سند لها.
gate = ns["train_and_gate"]
empty_sim = {"rows": [], "eligible_count": 0}
out = gate(empty_sim, {"rows": []})
check("٤ بلا عيّنة حقيقية لا ترقية", not out["gate"]["passed"])
check("  والسبب العيّنة لا الأداء", "العيّنة" in out["gate"]["reason"],
      out["gate"]["reason"])
check("  والحدّ معقول", 20 <= ns["MIN_REAL_FOR_GATE"] <= 100,
      str(ns["MIN_REAL_FOR_GATE"]))
check("  ولا يُرقّى بلا اجتياز", not out.get("promoted"))
# والحَكَم لا يدخل التدريب
check("  والحقيقي لا يُدرَّب عليه",
      "train_and_gate" in pred_code and "real_rows" in pred_code
      and "_fit(X, y)" in pred_code and "_fit(real" not in pred_code)
# وتفوّقٌ ضئيل ليس تفوّقاً
check("  ويُشترط هامش", ns["MIN_EDGE"] > 0, str(ns["MIN_EDGE"]))


# ═══ ٥) اسم المحرّك يُقال ═══
#
# السلسلة: lightgbm ← sklearn ← مصنّفٌ بسيط مكتوب بيد. والثالث
# يعمل ويُنتج «نموذجاً»، فتقول الشاشة «نشط» ويظنّه القارئ LightGBM.
eng = ns["engine_name"]()
check("٥ المحرّك يُسمّى", eng["name"] in
      ("lightgbm", "sklearn_rf", "simple_fallback"), str(eng))
check("  وله شرح", bool(eng.get("note")))
cmd = (ROOT / "web" / "dashboard" / "management" / "commands"
       / "train_predictor.py").read_text(encoding="utf-8")
check("  والأمر ينبّه إن لم يكن lightgbm",
      'eng["name"] != "lightgbm"' in cmd and "pip install lightgbm" in cmd)
# والبديل يُوصف بديلاً لا نموذجاً
check("  والبديل موصوف بأنّه بديل",
      "للتشغيل لا للإنتاج" in pred_code)


# ═══ ٥ب) خطّ الأساس العشوائي قيمةٌ متوقَّعة لا رمية ═══
#
# كان: ``rand = rng.integers(0, 2, n_test)`` ثمّ يُقاس على الحقيقة.
# وهي عيّنةٌ واحدة من موزّعٍ قيمته المتوقَّعة ٠٫٥، وخطؤها المعياريّ
# على ٩٦٠ عيّنة نحو ١٫٦ نقطة — فتقع بين ٤٧٪ و٥٣٪.
#
# و``best`` هو أعلى خطوط الأساس، وهو السقف الذي يجب أن يتجاوزه
# حدُّ ثقة النموذج الأدنى. فحين حالف الحظّ الرمية بلغت ٥١٫٠٪
# وصارت **أفضل خطّ أساس** على شاشة البتكوين — فحُوكم النموذج على
# حظّ عملةٍ معدنية.
#
# وتقريرٌ لا يُعاد إنتاجه ليس تقريراً: الرقم يتغيّر مع كل شمعةٍ
# جديدة لأنّ ``n_test`` يتغيّر، على البيانات نفسها تقريباً.
_DIR = ROOT / "scanner" / "btc" / "direction.py"
_dcode = _DIR.read_text(encoding="utf-8")
_dbody = "\n".join(l for l in _dcode.splitlines()
                   if not l.strip().startswith("#"))
check("٥ب العشوائي ٠٫٥ بالضبط", '"عشوائي": 0.50' in _dbody, "ما زال رمية")
check("  ولا مولّد في التقييم",
      "rng.integers" not in _dbody, "ما زال يرمي")
# والأغلبية والاستمرار تبقيان محسوبتين — هما خطّا الأساس الحقيقيّان
check("  والأغلبية تُحسب", "base_major" in _dbody)
check("  والاستمرار كذلك", "base_persist" in _dbody)

# ═══ و«لا يعمل» له معنيان ═══
#
# المكتبة غائبة (ارتدّ إلى انحدارٍ لوجستيّ) ≠ المكتبة تعمل
# والنموذج خسر. وكان الفرق يظهر في كلمةٍ يسهل ألّا تُقرأ بينما
# الشارة تقول «لا يُستعمل» في الحالتين.
_btpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
         / "btc.html").read_text(encoding="utf-8")
check("  وحال المكتبة يُقال", "m.has_lightgbm" in _btpl)
check("  والخسارة تُسمّى خسارة", "خسر أمام خطّ الأساس" in _btpl)
_doc = (ROOT / "tools_doctor_lgb.py")
check("  وأداةُ فصلٍ بينهما", _doc.exists())
if _doc.exists():
    _dt = _doc.read_text(encoding="utf-8")
    check("    تفحص الاستيراد", "import lightgbm" in _dt)
    check("    وتدرّب فعلاً", ".fit(" in _dt)
    check("    وتذكر libgomp", "libgomp" in _dt)


# ── ٦) ترتيب الأعمدة ثابت ──
#
# قاموس بايثون يحفظ ترتيب الإدراج. فصفٌّ ينقصه عمود يُزيح ما بعده
# ويتدرّب النموذج على أعمدةٍ مختلطة بلا أن يفشل شيء.
from scanner.predictive.feature_registry import (  # noqa: E402
    V3_COLUMNS, v3_columns_with_missing,
)

cols = v3_columns_with_missing()
check("٦ الأعمدة من العقد", cols[:len(V3_COLUMNS)] == list(V3_COLUMNS))
check("  ومؤشّر لكل اختيارية",
      sum(1 for c in cols if c.endswith("__missing")) == len(opt),
      str(sum(1 for c in cols if c.endswith("__missing"))))
mat = ns["_matrix"]
X, y, used = mat([{"features": {"rsi": 1.0}, "label_binary_win": 1}])
check("  والمصفوفة بطول العقد", len(X[0]) == len(cols))
check("  والغائب None لا صفر", X[0][cols.index("atr_pct")] is None,
      str(X[0][cols.index("atr_pct")]))
# الصفر يعني «قيمة صفر» والـNone يعني «لا نعرف» — وخلطهما يعلّم
# النموذج أنّ الجهل قيمة
check("  والحاضر يمرّ", X[0][cols.index("rsi")] == 1.0)


# ── ٧) الجدولة تدرّب نفسها ──
cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
ccode = "\n".join(l for l in cron.splitlines()
                  if not l.strip().startswith("#"))
check("٧ للتدريب معالج مجدول", '"train_predictor": _h_train' in ccode)
check("  ويوميّاً لا بالساعة",
      '"interval_type": "days"' in ccode)
check("  وله اسم عربي", "تدريب نموذج التنبؤ" in cron)
# نقص البيانات ليس فشلاً: يُؤجَّل ولا يُصبغ أحمر كل يوم
check("  ونقص البيانات تأجيل لا فشل", "raise JobBusy" in ccode)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
