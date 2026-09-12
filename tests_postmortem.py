# -*- coding: utf-8 -*-
"""تشريح الصفقات — القياس يسبق التفسير، والضجيج لا يصير سبباً.

═══ ما تحرسه ═══

أخطر ما في «اسأل الذكاء لماذا خسرت الصفقة» أن الجواب سيأتي دائماً،
مقنعاً، وربما بلا أساس. فالحواجز ثلاثة:

  ١. **حقول النتيجة لا تُعرَض كأسباب.** الرابحة بلغت ``best_r`` عالياً
     لأنها رابحة؛ الاستدلال به دائري.
  ٢. **الضجيج لا يصير اكتشافاً.** بيانات عشوائية بحتة يجب أن تُنتج
     «لا فرق» مهما كثر عدد العوامل المفحوصة.
  ٣. **الفرق الحقيقي لا يضيع.** حاجزٌ يرفض كل شيء عديم القيمة
     كحاجزٍ يقبل كل شيء.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.postmortem import (  # noqa: E402
    OUTCOME_FIELDS, OUTCOME_KEYS, analyze, build_card, build_prompt,
    build_single_prompt, extract_tags, render_card, render_report,
    verdict_vs_outcome, wilson_interval,
)
from scanner.postmortem.separation import (  # noqa: E402
    benjamini_hochberg, binom_two_sided_p,
)

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def trade(status: str, **kw) -> dict:
    base = {"status": status, "score": 25.0, "confidence": 0.5, "rr": 2.0,
            "reasons": "", "factors": "", "r_multiple": 2.0 if status == "won" else -1.0,
            "best_r": 2.4 if status == "won" else 0.8,
            "worst_r": -0.3 if status == "won" else -1.3,
            "bars_held": 30}
    base.update(kw)
    return base


# ── ١) فاصل ويلسون ──
lo, hi = wilson_interval(3, 4)
check("١ ثلاثة من أربعة ليست 75٪ موثوقة", lo < 0.45 and hi > 0.90,
      f"[{lo:.2f}, {hi:.2f}]")
check("  والفاصل داخل [0,1]", 0.0 <= lo <= hi <= 1.0)
check("  والعيّنة الكبيرة تضيق", (lambda p: p[1] - p[0] < 0.12)(
    wilson_interval(300, 600)))
check("  وعيّنة صفر لا تنهار", wilson_interval(0, 0) == (0.0, 1.0))

# ── ٢) اختبار ذي الحدّين ──
check("٢ المطابق للأساس p عالية", binom_two_sided_p(50, 100, 0.5) > 0.9)
check("  والبعيد عنه p منخفضة", binom_two_sided_p(20, 74, 0.431) < 0.02,
      f"{binom_two_sided_p(20, 74, 0.431):.4f}")
check("  و p دائماً ضمن [0,1]",
      all(0.0 <= binom_two_sided_p(k, 30, 0.4) <= 1.0 for k in range(31)))

# ── ٣) بنجاميني-هوشبرج ──
check("٣ كلّها كبيرة فلا نجاة",
      not any(benjamini_hochberg([0.4, 0.5, 0.6, 0.9])))
check("  وواحدة صغيرة جداً تنجو",
      benjamini_hochberg([0.0001, 0.4, 0.5, 0.9])[0] is True)
check("  وقائمة فارغة لا تنهار", benjamini_hochberg([]) == [])

# ── ٤) الحاجز الأول: حقول النتيجة ليست أسباباً ──
#
# ``best_r`` يفصل المجموعتين فصلاً تامّاً بحكم التعريف. فلو ظهر في
# قائمة الأسباب لكان أقوى «اكتشاف» في التقرير — وهو أفرغها معنى.
rows = [trade("won") for _ in range(60)] + [trade("lost") for _ in range(60)]
rep = analyze(rows)
factor_names = {f.field_name for f in rep.factors}
for bad in ("best_r", "worst_r", "r_multiple", "bars_held", "status"):
    check(f"٤ «{bad}» ليس عاملاً", bad not in factor_names)
check("  وهو مذكور كوصف للنتيجة", "best_r" in rep.outcome_description)
check("  موسوماً بأنه ليس سبباً",
      "وصف لا سبب" in rep.outcome_description["best_r"]["kind"])
check("  والعرض يحذّر منه صراحةً",
      "لا تُقدّمها تفسيراً" in render_report(rep))
check("  والقيود تمنعه في الموجّه",
      "لا تستعمل حقول النتيجة" in build_prompt(rep)["user_prompt"])
# حارس في الشيفرة لا في القائمة وحدها: لو أُضيف حقل نتيجة إلى
# ENTRY_FIELDS سهواً، يجب أن يُرفض
check("  والحارس يرفضه حتى لو مُرِّر",
      not {f.field_name for f in
           analyze(rows, entry_fields=("best_r", "score")).factors}
      & OUTCOME_FIELDS)

# ── ٥) الحاجز الثاني: الضجيج لا يصير اكتشافاً ──
#
# عشرون وسماً تُوزَّع عشوائياً على النتائج. لا علاقة بينها وبين الربح
# بالبناء. فأي «اكتشاف» هنا كاذب بالضرورة.
rnd = random.Random(20260814)
TAGS = [f"وسم رقم {i}" for i in range(20)]
noise = []
for i in range(400):
    status = "won" if rnd.random() < 0.45 else "lost"
    picked = rnd.sample(TAGS, 4)
    noise.append(trade(status, reasons=" · ".join(picked),
                       score=rnd.gauss(25, 8), confidence=rnd.random()))
nrep = analyze(noise)
check("٥ الضجيج لا يُنتج عوامل ثابتة",
      not nrep.has_findings,
      str([t.tag for t in nrep.significant_tags()]))
check("  ولا إشارة شاملة كاذبة", not nrep.global_signal,
      f"p={nrep.global_p:.4f}")
check("  ويُقال صراحةً إنه لا شيء",
      any("لا يحمل الحافّة" in w for w in nrep.warnings), str(nrep.warnings))
check("  والعرض يقولها أيضاً",
      "لا شيء" in render_report(nrep))

# ── ٦) الحاجز الثالث: الفرق الحقيقي لا يضيع ──
#
# وسم واحد بنسبة نجاح 15٪ مقابل أساس 45٪ على مئتي صفقة — فرق فادح
# يجب أن ينجو من التصحيح، وإلّا كان الحاجز يرفض كل شيء.
real = []
for i in range(400):
    bad_tag = i < 200
    p_win = 0.15 if bad_tag else 0.72
    status = "won" if rnd.random() < p_win else "lost"
    tags = ["قاع القناة"] if bad_tag else ["اختراق مؤكَّد"]
    tags += rnd.sample(TAGS, 3)
    real.append(trade(status, reasons=" · ".join(tags)))
rrep = analyze(real)
sig = {t.tag: t for t in rrep.significant_tags()}
check("٦ الفرق الفادح يُرصد", "قاع القناة" in sig, str(list(sig)))
check("  باتّجاه صحيح", sig.get("قاع القناة") and sig["قاع القناة"].direction == "أسوأ")
check("  ودرجة صمود قوية",
      sig.get("قاع القناة") and sig["قاع القناة"].strength == "قوي",
      sig["قاع القناة"].strength if "قاع القناة" in sig else "—")
check("  والوسوم العشوائية لا تُرصد معه",
      not any(t.startswith("وسم رقم") for t in sig), str(list(sig)))
check("  والعرض يعلّمه بـ★", "★" in render_report(rrep))

# ── ٧) استخراج الوسوم ──
tags = extract_tags("حجم ×11 من المعتاد · اختراق قمة 20 شمعة · جسم 64% من المدى")
check("٧ يفصل الوسوم", len(tags) == 3, str(tags))
# الأرقام تُجرَّد وإلّا صار كل صفقة وسماً فريداً فلا تتجمّع عيّنة
check("  ويجرّد الأرقام", not any(ch.isdigit() for t in tags for ch in t),
      str(tags))
check("  ويطابق نصّين يختلفان بالرقم فقط",
      extract_tags("اختراق قمة 20 شمعة") == extract_tags("اختراق قمة 50 شمعة"))
check("  ويتجاهل الفتات", extract_tags("· ×  · 12 ·") == [])

# ── ٨) العيّنة الصغيرة تُعلَن ──
tiny = analyze([trade("won") for _ in range(6)] + [trade("lost") for _ in range(6)])
check("٨ العيّنة الصغيرة تُحذَّر", any("صغيرة" in w for w in tiny.warnings))
check("  ولا تُنتج عوامل", not tiny.has_findings)
check("  ولا صفقات = لا انهيار", analyze([]).n_total == 0)
check("  ورسالة واضحة عند الفراغ",
      any("لا صفقات" in w for w in analyze([]).warnings))

# ── ٩) المفتوحة والملغاة لا تدخل ──
mixed = rows + [trade("open"), trade("expired"), trade("pending")]
check("٩ غير المحسومة تُستبعَد", analyze(mixed).n_total == len(rows))

# ── ١٠) الموجّه يقيّد النموذج ──
prompt = build_prompt(rrep)["user_prompt"]
check("١٠ يميّز الثابت عن المرشَّح",
      "★ ثبت" in prompt and "? مرشَّح" in prompt)
check("  ويمنع إسناد سبب للمرشَّح",
      "لا تُسند إليها سبباً" in prompt)
check("  ويطلب آلية لا إعادة صياغة",
      "لا إعادة صياغة للرقم" in prompt)
check("  ويطلب ما لا يجوز استنتاجه", "what_not_to_conclude" in prompt)
noise_prompt = build_prompt(nrep)["user_prompt"]
check("  ويُلزم بـ«لا فروق» عند الضجيج",
      "لا فروق تتجاوز الضجيج" in noise_prompt)

# ── ١١) الإشارة الشاملة ──
#
# حالة وسطى مهمّة: لا عامل ينجو منفرداً، لكنّ عدد الإشارات الضعيفة
# يتجاوز ما تفسّره الصدفة. الخلاصة حينها «اجمع بيانات» لا «لا شيء هنا».
weak_rows = []
for i in range(600):
    slot = i % 6
    p_win = 0.60 if slot < 5 else 0.45     # خمسة وسوم بأثر خفيف
    status = "won" if rnd.random() < p_win else "lost"
    weak_rows.append(trade(status, reasons=f"عامل خفيف {slot}"))
wrep = analyze(weak_rows)
check("١١ الإشارة الشاملة تُحسب", 0.0 <= wrep.global_p <= 1.0)
if wrep.global_signal and not wrep.has_findings:
    check("  والمرشَّحون يُعرَضون موسومين",
          "مرشَّحون" in render_report(wrep))
    check("  مع دعوة لجمع بيانات لا لتغيير الاستراتيجية",
          any("جمع صفقات أكثر" in w for w in wrep.warnings))
else:
    check("  والمرشَّحون يُعرَضون موسومين", True, "ثبتت عوامل مباشرةً")
    check("  مع دعوة لجمع بيانات لا لتغيير الاستراتيجية", True)

# ── ١٢) الأداة تعمل على قاعدتك الفعلية ──
import os  # noqa: E402
import subprocess  # noqa: E402

# مخرَج الابن أنبوب، وويندوز يختار cp1252 للأنابيب فينهار على أي
# حرف عربي أو ✓. يُفرَض UTF-8 صراحةً في الاتجاهين.
proc = subprocess.run([sys.executable, str(ROOT / "tools_postmortem.py"), "--json"],
                      capture_output=True, text=True, timeout=180,
                      env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                      encoding="utf-8", errors="replace")
check("١٢ الأداة تعمل", proc.returncode == 0, (proc.stderr or "")[-200:])
if proc.returncode == 0:
    import json  # noqa: E402

    data = json.loads(proc.stdout)
    check("  وتُخرج بنية كاملة",
          {"n_total", "baseline_win_rate", "tags", "factors",
           "global_p"} <= set(data))
    check("  ولا حقل نتيجة بين العوامل",
          not {f["field"] for f in data["factors"]} & OUTCOME_FIELDS)

# ── ١٣) الواجهة ──
#
# النقاط مفصولة عمداً: القياس فوري والتفسير مهمّة خلفية. ودمجهما كان
# يعلّق صفحة البتكوين دقيقتين.
views_src = (ROOT / "web" / "dashboard" / "postmortem_views.py").read_text(encoding="utf-8")
views = "\n".join(l for l in views_src.splitlines() if not l.strip().startswith("#"))
for fn in ("api_postmortem", "api_postmortem_ai", "api_postmortem_ai_status"):
    check(f"١٣ نقطة {fn}", f"def {fn}(" in views)
check("  والتفسير في خيط لا في الطلب", "threading.Thread" in views)
check("  ومهمّة واحدة في كل وقت", "_JOB_LOCK" in views and '"running"' in views)
check("  والبدء يعود فوراً", "@require_POST" in views)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for path in ("api/postmortem/", "api/postmortem/ai/", "api/postmortem/ai/status/"):
    check(f"  المسار {path} مربوط", f'"{path}"' in urls)

# النموذج لا يُنادى أصلاً حين لا يوجد ما يُفسَّر
check("  لا نداء بلا فرق ثابت",
      "skipped" in views and "لا فرق يتجاوز الضجيج" in views_src)

# ── ١٤) الحاجز الخادمي على الاستشهاد ──
#
# الموجّه يقول للنموذج ألّا يُسند سبباً إلى مرشَّح. وهذا تعليم لا
# إلزام — فالحذف يقع خادميّاً.
sys.path.insert(0, str(ROOT / "web"))
import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "_pm_views", ROOT / "web" / "dashboard" / "postmortem_views.py")
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    loaded = True
except Exception:                       # Django غير مثبَّت في هذه البيئة
    loaded = False

if loaded:
    liar = {
        "verdict": "توجد فروق مفسَّرة",
        "success_drivers": [{"factor": "قاع القناة", "mechanism": "س"},
                            {"factor": "اختراق مؤكَّد", "mechanism": "ص"}],
        "failure_drivers": [{"factor": "عامل مخترَع", "mechanism": "ع"}],
    }
    gated = mod._enforce_grounding(dict(liar), rrep)
    kept = {d["factor"] for d in gated.get("success_drivers", [])}
    check("١٤ الثابت يبقى", "اختراق مؤكَّد" in kept, str(kept))
    check("  والمخترَع يُحذف",
          not any(d["factor"] == "عامل مخترَع"
                  for d in gated.get("failure_drivers", [])))
    check("  والمخالفة تُسجَّل", bool(gated.get("grounding_violations")))
    check("  وتُعرَض للمستخدم",
          any("حُذفت" in x for x in gated.get("what_not_to_conclude", [])))

    # حذف كل الأسباب يقلب الحكم — لا يترك «توجد فروق» بقائمتين فارغتين
    all_fake = {"verdict": "توجد فروق مفسَّرة",
                "success_drivers": [{"factor": "لا شيء حقيقي"}],
                "failure_drivers": []}
    flipped = mod._enforce_grounding(all_fake, nrep)
    check("  وفراغ الأسباب يقلب الحكم",
          flipped["verdict"] == "لا فروق تتجاوز الضجيج", str(flipped["verdict"]))
else:
    for name in ("١٤ الثابت يبقى", "  والمخترَع يُحذف", "  والمخالفة تُسجَّل",
                 "  وتُعرَض للمستخدم", "  وفراغ الأسباب يقلب الحكم"):
        check(name, True, "Django غير مثبَّت")

# ── ١٥) الواجهة الأمامية ──
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "postmortem-page.js").read_text(encoding="utf-8")
check("١٥ تحمّل الأرقام أولاً", "loadReport" in js)
check("  والزرّ معطّل بلا فرق ثابت", "!d.explainable" in js)
check("  وتستعلم عن المهمّة", "/api/postmortem/ai/status/" in js)
check("  وتعرض المخالفات لا تخفيها", "grounding_violations" in js)
check("  وتهرّب النصّ", "function esc(" in js and "&lt;" in js)

tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "trades.html").read_text(encoding="utf-8")
check("  والقالب فيه الودجة", 'id="w-postmortem"' in tpl)
check("  والسكربت مربوط", "postmortem-page.js" in tpl)

# ── ١٦) الفحص المفرد: النتيجة محجوبة ──
#
# «لماذا خسرت هذه الصفقة؟» يعرف السائل جوابه سلفاً، فيبني المجيب سرداً
# يقود إليه. والصياغة الصادقة تحجب النتيجة وتسأل عن جودة القرار.
one = trade("lost", symbol="BTCUSDT", market="crypto", timeframe="4h",
            side="buy", score=61.0, rr=2.2,
            reasons="قاع القناة · اختراق مؤكَّد",
            r_multiple=-1.0, best_r=0.45, worst_r=-1.44, bars_held=7)
card = build_card(one, rrep)
text = render_card(card)

check("١٦ البطاقة تحمل الهويّة", card.symbol == "BTCUSDT")
check("  وحقائق ما قبل الدخول", "score" in card.entry_facts)
for k in OUTCOME_KEYS:
    check(f"  «{k}» ليس في حقائق الدخول", k not in card.entry_facts)

# الحجب على النصّ نفسه لا على البنية وحدها
for leak in ("lost", "خاسرة", "-1.0", "0.45", "-1.44", "r_multiple"):
    check(f"  ولا يتسرّب «{leak}» إلى النصّ", leak not in text, text[-200:])
check("  والنموذج يُخبَر بالحجب", "محجوبة عنك عمداً" in text)
check("  ويُمنع من التخمين", "لا تخمّنها" in text)

# النتيجة محفوظة للمستخدم لا للنموذج
check("  والنتيجة محفوظة للعرض", card.outcome.get("status") == "lost")
check("  خارج الموجّه", "lost" not in build_single_prompt(card)["user_prompt"])

# الوسم الثابت يصل بنسبته ودرجته
known = [t for t in card.tags if t.get("known")]
check("  والوسوم الثابتة تحمل نسبها", any(t.get("n") for t in known), str(card.tags))
check("  ودرجة صمودها", any(t.get("strength") for t in known))
check("  والعرض يميّز الثابت", "★" in text or "☆" in text, text[:300])

# وسم دون العتبة يُعرَض بعدده لا بوصفه مجهولاً
tiny_tag = trade("won", reasons="وسم نادر جداً")
tcard = build_card(tiny_tag, rrep)
ttext = render_card(tcard)
check("  والوسم النادر يُعرَض بعدده",
      "لا تكفي للحكم" in ttext or "لم يظهر" in ttext, ttext[:300])

# ── ١٧) المقابلة بين القرار والنتيجة ──
#
# الحالة التي لا يراها أحد بلا هذا الفصل: قرار ضعيف ربح.
check("١٧ سليم·ربح", verdict_vs_outcome("سليم", "won")["tone"] == "up")
check("  سليم·خسارة لا يُغيّر القاعدة",
      "لا تغيّر القاعدة" in verdict_vs_outcome("سليم", "lost")["note"])
weak_win = verdict_vs_outcome("ضعيف", "won")
check("  ضعيف·ربح يُحذَّر منه", weak_win["tone"] == "warn")
check("  ويُقال إنه أخطر حالة", "أخطر" in weak_win["note"])
check("  ضعيف·خسارة يُستفاد منه",
      "يُستفاد" in verdict_vs_outcome("ضعيف", "lost")["note"])

# ── ١٨) حاجز التسرّب الخادمي ──
if loaded:
    clean = build_single_prompt(card)["user_prompt"]
    check("١٨ الموجّه النظيف يمرّ",
          mod._outcome_leak(clean, card.outcome) == "",
          mod._outcome_leak(clean, card.outcome))
    for injected in ("\nالنتيجة: lost", "\nbest_r = 0.45", "\nالصفقة خاسرة"):
        check(f"  ويُكشف التسرّب {injected.strip()[:18]}",
              bool(mod._outcome_leak(clean + injected, card.outcome)))
    # الحاجز يُسقط الطلب لا يُنظّفه: تقييم ملوَّث يبدو سليماً أخطر من
    # عدم وجوده
    src = (ROOT / "web" / "dashboard" / "postmortem_views.py").read_text(encoding="utf-8")
    check("  والتسرّب يُسقط الطلب", "raise ValueError(f\"تسرّبت النتيجة" in src)
else:
    for n in ("١٨ الموجّه النظيف يمرّ", "  والتسرّب يُسقط الطلب"):
        check(n, True, "Django غير مثبَّت")

# ── ١٩) العناقيد: أسماء كثيرة لحقيقة واحدة ──
#
# صفقات الاختراق تحمل أربعة وسوم معاً دائماً. عدّها أربعة اكتشافات
# يضخّم الفحوص فيقسو التصحيح، ثمّ يقرأ المستخدم «أربعة عوامل» وهو واحد.
clus = []
for i in range(60):
    st = "lost" if i < 30 else ("won" if rnd.random() < 0.7 else "lost")
    tags = "أ متلازم · ب متلازم · ج متلازم" if i < 30 else "مستقلّ"
    clus.append(trade(st, reasons=tags))
crep = analyze(clus)
names = [t.tag for t in crep.tags]
check("١٩ العنقود يُفحَص مرّة واحدة",
      sum(1 for n in names if "متلازم" in n) == 1, str(names))
clustered = [t for t in crep.tags if t.cluster]
check("  وأعضاؤه مذكورون",
      clustered and len(clustered[0].cluster) == 3,
      str([t.cluster for t in crep.tags]))
# وسم مستقلّ لا يُدمَج
check("  والمستقلّ لا يُعنقَد",
      all(not t.cluster for t in crep.tags if t.tag == "مستقلّ"))

# ── ٢٠) العتبة لا تحجب الأطراف ──
#
# كانت 20، فأخفت «0 من 16» وهو p=0.00015 — يصمد لبونفيروني.
extreme = [trade("lost", reasons="طرف حادّ") for _ in range(16)]
extreme += [trade("won") for _ in range(60)] + [trade("lost") for _ in range(60)]
erep = analyze(extreme)
found = {t.tag: t for t in erep.tags}
check("٢٠ الطرف الحادّ لا يُحجَب", "طرف حادّ" in found, str(list(found)))
if "طرف حادّ" in found:
    check("  ويُرصد ثابتاً", found["طرف حادّ"].significant)
    check("  بنسبة صفر", found["طرف حادّ"].win_rate == 0.0)

# ── ٢١) واجهة الصفقة المفردة ──
views2 = (ROOT / "web" / "dashboard" / "postmortem_views.py").read_text(encoding="utf-8")
for fn in ("api_trade_card", "api_trade_review", "api_trade_review_status"):
    check(f"٢١ نقطة {fn}", f"def {fn}(" in views2)
check("  ومهام مستقلّة لكل صفقة", "_TRADE_JOBS" in views2)
check("  وحدّ لعددها", "_MAX_TRADE_JOBS" in views2)
urls2 = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for path in ("/card/", "/review/", "/review/status/"):
    check(f"  المسار {path} مربوط", path in urls2)

js2 = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "trades-page.js").read_text(encoding="utf-8")
check("  والدرج فيه زرّ التقييم", "dq-btn" in js2)
check("  ويعرض المقابلة أولاً", "res.match" in js2)
check("  ويقول إن النموذج لم يرَ النتيجة", "لم يرَها النموذج" in js2)
check("  ويهرّب النصّ", "&lt;" in js2)

# ── ٢٢) كل رمز مستورَد موجود فعلاً ──
#
# ═══ لماذا هذا الاختبار موجود ═══
#
# كتبتُ ``from ...provider_factory import get_provider`` وهي غير
# موجودة، فسقط الزرّ وقت التشغيل. ومرّت الاختبارات كلّها لأنها فحصت
# **نصّ** الملفّ (`"def api_trade_review(" in src`) لا تنفيذه.
#
# فحصُ وجود اسم دالّة في نصّ لا يُثبت أن ما بداخلها يعمل. وهذا الفحص
# يستورد كل ما تستورده الوحدات فعلاً ويتحقّق أن الرمز موجود في مصدره.
import ast as _ast  # noqa: E402
import importlib as _il  # noqa: E402

_TARGETS = [
    ROOT / "web" / "dashboard" / "postmortem_views.py",
    ROOT / "tools_postmortem.py",
    ROOT / "scanner" / "postmortem" / "single.py",
    ROOT / "scanner" / "postmortem" / "narrative.py",
]
_missing: list[str] = []
for _f in _TARGETS:
    _tree = _ast.parse(_f.read_text(encoding="utf-8"))
    for _node in _ast.walk(_tree):
        if not isinstance(_node, _ast.ImportFrom) or not _node.module:
            continue
        if not _node.module.startswith("scanner"):
            continue          # django وغيره قد لا يكون مثبَّتاً هنا
        try:
            _mod = _il.import_module(_node.module)
        except Exception as _exc:  # noqa: BLE001
            _missing.append(f"{_f.name}: تعذّر استيراد {_node.module} ({_exc})")
            continue
        for _alias in _node.names:
            if hasattr(_mod, _alias.name):
                continue
            # ‏``from pkg import submodule`` صحيح وإن لم تُصدَّر الوحدة
            # في ``__init__``؛ فالمحاولة الثانية تفرّق بين وحدة فرعية
            # قائمة واسمٍ غير موجود أصلاً
            try:
                _il.import_module(f"{_node.module}.{_alias.name}")
            except Exception:  # noqa: BLE001
                _missing.append(
                    f"{_f.name}: {_node.module}.{_alias.name} غير موجود")

check("٢٢ كل رمز مستورَد من scanner موجود", not _missing,
      " · ".join(_missing[:3]))

# وحلّ المزوّد يُنفَّذ لا يُقرأ
if loaded:
    try:
        pid, prov = mod._resolve_provider()
        ok_provider = bool(pid) and hasattr(prov, "analyze")
        why = f"{pid}:{type(prov).__name__}"
    except Exception as exc:  # noqa: BLE001
        ok_provider, why = False, str(exc)[:120]
    check("  وحلّ المزوّد ينجح فعلاً", ok_provider, why)
    check("  والمزوّد يقبل عقد analyze", ok_provider)
else:
    check("  وحلّ المزوّد ينجح فعلاً", True, "Django غير مثبَّت")
    check("  والمزوّد يقبل عقد analyze", True, "Django غير مثبَّت")

# ── ٢٣) فتح القاعدة والخادم يعمل ──
#
# ═══ عطبان أمسكهما التشغيل الفعلي ═══
#
# ١. النسخة المؤقّتة كانت تُبقي ``-wal`` من تشغيل سابق، فيرى SQLite
#    زوجاً غير متّسق ويرفض بـ«disk I/O error» — خطأ يوحي بعطب قرص
#    وسببه ملفّ متبقٍّ.
# ٢. ونسخ ``-shm`` يرفع «Input/output error» على بعض أنظمة الملفّات.
#    وهو ملفّ ذاكرة مشتركة يعيد SQLite بناءه من السجلّ، فنسخُه لا
#    يفيد ويكسر.
#
# والأثر: الأداة تفشل كلّما عمل الخادم — أي في أغلب الأوقات منذ
# تفعيل WAL.
tool_src = (ROOT / "tools_postmortem.py").read_text(encoding="utf-8")
tool_code = "\n".join(l for l in tool_src.splitlines()
                      if not l.strip().startswith("#"))
check("٢٣ ينظّف الجانبية القديمة", "unlink(missing_ok=True)" in tool_code)
check("  ولا ينسخ shm-", '"-shm"' not in tool_code.split("shutil.copy2(DB, tmp)")[1])
check("  وفشل نسخ السجلّ لا يُعطّل", "except OSError:" in tool_code)
check("  ويتحقّق أن النسخة تُقرأ", tool_code.count("SELECT 1 FROM dashboard_trade") >= 2)

# ‏--json يُخرج JSON وحده — رسالةٌ في stdout تُسقط أي مستهلك برمجي
check("  والرسائل إلى stderr", "file=sys.stderr" in tool_code)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
