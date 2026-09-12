# -*- coding: utf-8 -*-
"""الصفقات الذهبية — ترتيبٌ معروضٌ بتفصيله، وفراغٌ معلَّل.

═══ الخطر في اسم الصفحة ═══

«ذهبية» توحي بضمان. وقِيس على ٢٩٥ صفقة محسومة::

    نسبة الفوز        46.4٪  [41–52]
    التصنيف A مقابل C   فرقٌ ضمن الصدفة
    أسبابٌ نجت ضبط التعدّد   صفر

فلا شيء في السجلّ يقول إنّ الأعلى ترتيباً يفوز أكثر. ولذلك:

    · الترتيب مركّبٌ يُعرض بتفصيله، فيمكن مخالفته عن علم.
    · وسجلّ الأسباب أثقل مركّب — وهو وحده المبنيّ على نتائج.
    · والبطاقة الفارغة تُعلَّل: «لا إشارة» غير «المسح متوقّف».
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


src = (ROOT / "web" / "dashboard"
       / "golden_views.py").read_text(encoding="utf-8")
tree = ast.parse(src)
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

# ── تحميل المُرتِّب بلا Django ──
node = next(n for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_score_candidate")
ns: dict = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), "g", "exec"), ns)
score_candidate = ns["_score_candidate"]


class Row:
    def __init__(self, **kw):
        self.rr = kw.get("rr", 2.0)
        self.confluence = kw.get("confluence", 2)
        self.score = kw.get("score", 40.0)
        self.reasons = kw.get("reasons", "")


def pop(w, l, reasons):
    base = {"market": "crypto", "timeframe": "1h", "side": "buy",
            "grade": "A", "source": "auto", "score": 30.0, "rr": 2.0,
            "reasons": reasons}
    return ([{**base, "id": i, "symbol": f"W{i}", "status": "won",
              "r_multiple": 2.0} for i in range(w)]
            + [{**base, "id": 900 + i, "symbol": f"L{i}", "status": "lost",
                "r_multiple": -1.0} for i in range(l)])


# ── ١) الترتيب يُشرح ──
population = pop(2, 30, "سبب سيّئ") + pop(40, 20, "سبب عادي")
out = score_candidate(Row(reasons="سبب عادي"), population)
check("١ للترتيب مجموع", isinstance(out.get("total"), float))
check("  وتفصيل", len(out.get("parts") or []) >= 4, str(len(out.get("parts") or [])))
labels = {p["label"] for p in out["parts"]}
for want in ("عائد/مخاطرة", "التقاء العوامل", "سجلّ أسباب الإشارة",
             "نقاط النظام"):
    check(f"  وفيه «{want}»", want in labels, str(labels))
# ولكل مركّب سقفه، فيُرى نصيبه من الكلّ
check("  ولكل مركّب سقف", all("max" in p and p["max"] > 0
                              for p in out["parts"]))
check("  وقيمته معروضة", all(str(p.get("value")) for p in out["parts"]))


# ═══ ٢) سجلّ الأسباب أثقل مركّب ═══
#
# هو وحده المبنيّ على نتائج حقيقية. والنقاط رقمٌ يعطيه النظام
# لنفسه، فوزنُه أخفّ عمداً.
hist = next(p for p in out["parts"] if p["label"] == "سجلّ أسباب الإشارة")
sysp = next(p for p in out["parts"] if p["label"] == "نقاط النظام")
check("٢ السجلّ أثقل من النقاط", hist["max"] > sysp["max"],
      f"{hist['max']} مقابل {sysp['max']}")

# ═══ والسبب المضادّ يخفض الترتيب ═══
#
# ترتيبٌ يجمع المؤيّدات ويهمل المضادّات يرفع أسوأ الإشارات.
bad = score_candidate(Row(reasons="سبب سيّئ"), population)
good = score_candidate(Row(reasons="سبب عادي"), population)
check("  والمضادّ يخفض", bad["total"] < good["total"],
      f"{bad['total']} مقابل {good['total']}")


# ── ٣) عائد/مخاطرة يرفع، وضعفه يخفض ──
hi = score_candidate(Row(rr=3.0, reasons="سبب عادي"), population)
lo = score_candidate(Row(rr=1.5, reasons="سبب عادي"), population)
check("٣ العائد الأعلى يرفع", hi["total"] > lo["total"],
      f"{hi['total']} مقابل {lo['total']}")


# ── ٤) حدود معلنة ──
check("٤ حدّ لعمر الإشارة", "MAX_AGE_HOURS" in code)
check("  وحدّ لعائد/مخاطرة", "MIN_RR" in code)
mod: dict = {}
for n in tree.body:
    if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant):
        mod[n.targets[0].id] = n.value.value
check("  والعمر معقول", 6 <= mod.get("MAX_AGE_HOURS", 0) <= 168,
      str(mod.get("MAX_AGE_HOURS")))
check("  والعائد ≥ 1", mod.get("MIN_RR", 0) >= 1.0, str(mod.get("MIN_RR")))


# ═══ ٥) الفراغ يُعلَّل ═══
#
# بطاقةٌ فارغة تُقرأ «السوق هادئ»، وقد يكون المسح متوقّفاً منذ
# يومين — والفرق يغيّر ما يفعله القارئ.
check("٥ لا إشارة يُقال سببها", "لا إشارة قابلة للتنفيذ خلال" in code)
check("  وضعف العائد يُقال", "دون الحدّ" in code)
check("  ويُذكر عدد المرشّحين", '"considered"' in code)


# ── ٦) واحدة من كل سوق ──
check("٦ يدور على الأسواق", "for market in MARKETS" in code)
check("  ويأخذ الأولى بعد الترتيب", "cards[0]" in code)
check("  والترتيب تنازليّ", '-c["rank_total"]' in code)


# ── ٧) الحركة بالنسبة المئوية ──
#
# الهدف بالسعر لا يقول كم يلزم من حركة.
check("٧ المخاطرة نسبةً", '"risk_pct"' in code)
check("  والهدف نسبةً", '"gain_pct"' in code)


# ── ٨) الواجهة ──
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "golden-page.js").read_text(encoding="utf-8")
check("٨ تعرض تفصيل الترتيب", "rank_parts" in js and "details" in js)
check("  وتعرض المضادّ", "opposing" in js)
check("  وتربط بـ«هل أدخل؟»", "Advice.openSetup" in js)
html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "golden.html").read_text(encoding="utf-8")
# الاسم يوحي بضمان، فيُنفى في الصفحة نفسها لا في وثيقة جانبية
check("  والصفحة تنفي الضمان", "لا الرابحة" in html)
check("  وتذكر معدّل الفوز المقيس", "46.4" in html)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
check("  والمسار مسجَّل", "api_golden" in urls and "golden_page" in urls)
cp = (ROOT / "web" / "dashboard"
      / "context_processors.py").read_text(encoding="utf-8")
check("  وفي الشريط الجانبي", '"golden"' in cp)


bad_n = 0
for ok, name, extra in results:
    if not ok:
        bad_n += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad_n} من {len(results)}" if bad_n
      else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad_n else 0)
