# -*- coding: utf-8 -*-
"""المراجعة التلقائية بالمسار الجديد — وحفظ المرفوض.

═══ ما استُبدل ═══

المسار القديم أنتج ٧٥ قراراً::

    wait          65
    insufficient   5   ← عُرضت «⚪ مراقبة»
    avoid          4
    watch          1
    buy            0

و``buy`` **موجودة** في مفرداته ويمرّرها التطبيع سليمة. ومع ذلك لم
تخرج ولا مرّة. و``actionable_advice`` فارغ في ١٦٤ من ١٦٤.

وأخطر ما فيه أنّ الرفض لم يكن يُرى: المخرَج المرفوض يُسقَط صامتاً
فيبدو السجلّ نظيفاً وهو ناقص.

═══ ما يحرسه هذا الملف ═══

    ١) أن يُنادى النموذج للمرشّح القابل للتنفيذ وحده.
    ٢) أن يُحفظ المرفوض **بسببه** لا يُسقَط.
    ٣) أن يبقى ``reasons`` في المسار — فهو مدخل «لماذا قد تنجح».
    ٤) أن يظلّ السجلّ محدوداً — ``events.jsonl`` بلغ ٣٠٥ ميغابايت.
    ٥) أن يُعرض «ادخل» حين تسنده الأدلّة — لا صفر أبداً.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.ai_advisor import auto_review as ar  # noqa: E402
from scanner.ai_advisor import verdict_store as vs  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── ١) من يستحقّ نداءً ──
check("١ الجاهز يُراجَع", ar.is_actionable({"ready": True}))
check("  و«now» يُراجَع", ar.is_actionable({"action": "now"}))
check("  و«pending» يُراجَع", ar.is_actionable({"action": "pending"}))
# المسح يمرّ على مئات الرموز — ونداءٌ على كلٍّ منها ساعات
check("  وغير الجاهز لا", not ar.is_actionable({"ready": False,
                                                "action": "none"}))
check("  والفارغ لا", not ar.is_actionable({}) and not ar.is_actionable(None))


# ── ٢) الصفّ → إعداد ──
row = {"symbol": "BTCUSDT", "market": "crypto", "timeframe": "4h",
       "grade": "—", "score": "34.9", "rr": 2.0, "entry": 100.0,
       "stop": 95.0, "target1": 110.0, "close": "101.5",
       "reasons": "خصم · قاع القناة · الدرجة 35", "action": "pending"}
st = ar.setup_from_row(row)
check("٢ الرمز يُنقَل", st["symbol"] == "BTCUSDT")
check("  والأرقام تُحوَّل", st["score"] == 34.9 and st["close"] == 101.5)
# ═══ وأسباب الإشارة تبقى ═══
#
# ``reasons`` هو مدخل «لماذا قد تنجح» الذي يقيس كل سببٍ مزعوم على
# السجلّ. وإسقاطه هنا يُفقد التفسير كلَّه بلا أن يفشل شيء.
check("  و«reasons» يبقى", st["reasons"] == row["reasons"], st["reasons"])
# «—» ليست تقديراً بل غيابه — وتمريرها سمةً يصنع مجموعةً وهميّة
check("  و«—» ليست تقديراً", st["grade"] == "", repr(st["grade"]))
check("  والمفقود None لا صفر", ar.setup_from_row({})["score"] is None)


# ── ٣) المخزن ──
def pop(w, l, **k):
    b = {"market": "crypto", "timeframe": "4h", "side": "buy",
         "grade": "A", "source": "auto", "score": 34.0, "rr": 2.0,
         "reasons": "سبب قويّ"}
    b.update(k)
    return ([{**b, "id": i, "symbol": f"W{i}", "status": "won",
              "r_multiple": 2.0} for i in range(w)]
            + [{**b, "id": 500 + i, "symbol": f"L{i}", "status": "lost",
                "r_multiple": -1.0} for i in range(l)])


with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "v.jsonl"
    vs.append({"id": "a", "accepted": True, "fields": {"القرار": "ادخل"}},
              path=p)
    vs.append({"id": "b", "accepted": False,
               "rejected_because": "بلا رقم"}, path=p)
    got = vs.load_all(path=p)
    check("٣ يُكتب ويُقرأ", len(got) == 2)
    check("  والأحدث أوّلاً", got[0]["id"] == "b", got[0]["id"])
    check("  والبحث بالمعرّف", (vs.get("a", path=p) or {}).get("id") == "a")
    check("  والمفقود None", vs.get("zz", path=p) is None)
    s = vs.stats(path=p)
    check("  والإحصاء يفصل المرفوض",
          s["accepted"] == 1 and s["rejected"] == 1, json.dumps(s))
    check("  ويعدّ القرارات", s["decisions"].get("ادخل") == 1)

    # ═══ السطر التالف لا يعمي السجلّ ═══
    #
    # ملفٌّ قُطعت كتابته مرّة يجب ألّا يُسقط ما قبله.
    with p.open("a", encoding="utf-8") as fh:
        fh.write("{ليس JSON\n\n")
    vs.append({"id": "c", "accepted": True, "fields": {}}, path=p)
    check("  والتالف يُتخطّى", len(vs.load_all(path=p)) == 3,
          str(len(vs.load_all(path=p))))

    # الملفّ المفقود لا يرمي
    check("  والمفقود لا يرمي",
          vs.load_all(path=Path(d) / "nope.jsonl") == [])

    # ═══ والسجلّ محدود ═══
    #
    # ``events.jsonl`` بلغ ٣٠٥ ميغابايت بلا حدّ، فصارت قراءة سطرٍ
    # منه تكلّف ثوانٍ.
    p2 = Path(d) / "big.jsonl"
    for i in range(vs.MAX_RECORDS + 40):
        vs.append({"id": f"x{i}"}, path=p2)
    kept = vs.load_all(path=p2)
    check("  والسقف مفروض", len(kept) <= vs.MAX_RECORDS, str(len(kept)))
    check("  والأحدث محفوظ",
          kept[0]["id"] == f"x{vs.MAX_RECORDS + 39}", kept[0]["id"])


# ── ٤) المراجعة الكاملة بموفّر مزيَّف ──
#
# لا Ollama هنا: المطلوب فحص **المسار** لا النموذج.
import scanner.ai_advisor.advise as adv_mod  # noqa: E402

population = pop(30, 6) + pop(10, 40, grade="C", reasons="سبب ضعيف")


class FakeProvider:
    def __init__(self, text): self.text = text
    def model_name(self): return "fake"
    def analyze(self, prompt, package=None): return self.text


def run_with(text, rows, path):
    class Reg:
        def get(self, pid): return FakeProvider(text)
    orig = adv_mod.get_registry if hasattr(adv_mod, "get_registry") else None
    import scanner.ai_advisor.provider_registry as pr
    saved = pr.get_registry
    pr.get_registry = lambda: Reg()
    saved_path = vs._default_path
    vs._default_path = lambda: path
    try:
        return ar.review_candidates(rows, population)
    finally:
        pr.get_registry = saved
        vs._default_path = saved_path
        if orig:
            pass


rows = [{"symbol": "AAA", "market": "crypto", "timeframe": "4h",
         "ready": True, "grade": "A", "score": 34.0, "rr": 2.0,
         "entry": 100.0, "stop": 95.0, "target1": 110.0,
         "reasons": "سبب قويّ", "action": "pending"},
        {"symbol": "BBB", "market": "crypto", "timeframe": "4h",
         "ready": False, "action": "none", "reasons": "سبب ضعيف"}]

with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "v.jsonl"
    good = json.dumps({"القرار": "ادخل", "السبب": "مستوى الوقف 95",
                       "الرقم": "95", "الإبطال": "95", "الثقة": 70},
                      ensure_ascii=False)
    recs = run_with(good, rows, path)
    check("٤ غير الجاهز لا يُنادى عليه", len(recs) == 1, str(len(recs)))
    check("  والحكم مقبول", recs[0]["accepted"], recs[0].get("rejected_because"))
    # ═══ «ادخل» ممكنة فعلاً ═══
    #
    # المسار القديم لم يقلها ولا مرّة في ٧٥ قراراً.
    check("  و«ادخل» تخرج",
          recs[0]["fields"].get("القرار") == "ادخل",
          json.dumps(recs[0]["fields"], ensure_ascii=False))
    check("  والأدلّة محفوظة", "[" in recs[0]["evidence"])
    check("  والتفسير محفوظ", recs[0]["why"] is not None)
    check("  والسكّان معدودون", recs[0]["population"] == len(population))
    check("  ويُكتب في المخزن", len(vs.load_all(path=path)) == 1)

with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "v.jsonl"
    # مخرَجٌ يشبه ما أنتجه المسار القديم: كلامٌ يصف السؤال
    recs = run_with("راقب التحوّل في الاتجاه", rows, path)
    check("  والمخرَج غير المفحوص يُرفض", not recs[0]["accepted"])
    # ═══ والمرفوض يُحفظ ═══
    #
    # إسقاطه صامتاً يجعل السجلّ يبدو نظيفاً وهو ناقص. ومعدّل الرفض
    # أصدق مقياسٍ لصلاحية النموذج للمهمّة.
    saved = vs.load_all(path=path)
    check("  ويُحفظ رغم رفضه", len(saved) == 1, str(len(saved)))
    check("  وسببه معه", bool(saved[0]["rejected_because"]),
          saved[0].get("rejected_because"))
    check("  وحقوله فارغة لا مخترعة", saved[0]["fields"] == {})

# عطب الموفّر لا يُسقط المسح
with tempfile.TemporaryDirectory() as d:
    path = Path(d) / "v.jsonl"

    class Boom:
        def model_name(self): return "x"
        def analyze(self, *a, **k): raise RuntimeError("انقطع")

    import scanner.ai_advisor.provider_registry as pr
    saved_get, saved_p = pr.get_registry, vs._default_path
    pr.get_registry = lambda: type("R", (), {"get": lambda s, p: Boom()})()
    vs._default_path = lambda: path
    try:
        recs = ar.review_candidates(rows, population)
        check("  وعطب النموذج لا يرمي", True)
        check("  ويُسجَّل كرفض", recs and not recs[0]["accepted"])
    except Exception as exc:  # noqa: BLE001
        check("  وعطب النموذج لا يرمي", False, str(exc))
    finally:
        pr.get_registry, vs._default_path = saved_get, saved_p

check("  والملخّص يذكر الرفض",
      "مرفوض" in ar.summarize([{"accepted": False}]),
      ar.summarize([{"accepted": False}]))
check("  وبلا مرشّح يُقال ذلك", "لم يُنادَ" in ar.summarize([]))


# ── ٥) الربط ──
scan = (ROOT / "web" / "dashboard" / "management" / "commands"
        / "scan.py").read_text(encoding="utf-8")
code = "\n".join(l for l in scan.splitlines() if not l.strip().startswith("#"))
check("٥ المسح ينادي المسار الجديد", "_run_verdicts(" in code)
# المسار القديم لا يُحذف — يُطفأ، كي يبقى سجلّه قابلاً للفحص
check("  والقديم خلف مفتاح",
      'LEGACY_AI_REVIEW' in code, "لم يُطفأ")
check("  ولا يُنادى افتراضاً",
      'os.environ.get("LEGACY_AI_REVIEW") == "1"' in code)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for n in ("api_verdicts_list", "api_verdict_detail"):
    check(f"  و{n} مسجَّل", n in urls)
views = (ROOT / "web" / "dashboard" / "advice_views.py").read_text(
    encoding="utf-8")
check("  والمرفوض يُصفّى", '"مرفوض"' in views)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "verdicts-page.js").read_text(encoding="utf-8")
check("  والواجهة تعرض الرفض", "لم يُنتج حكماً" in js)
check("  وتعرض شرط الإبطال", "الإبطال" in js)
check("  وتعرض «لماذا»", "whyCell" in js)
html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "ai.html").read_text(encoding="utf-8")
check("  والصفحة فيها تبويب الأحكام", 'data-tab="verdicts"' in html)
check("  وتُحمّل ملفّها", "verdicts-page.js" in html)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
