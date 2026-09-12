# -*- coding: utf-8 -*-
"""مرشّحا الرمز والتاريخ — في الصفقات والمراقبة.

═══ ما يحرسه هذا الملف ═══

المرشّح عطبُه صامت: يظهر الشريط ممتلئاً ويعود الجدول غير مرشَّح،
فيبدو أنّه يعمل. ولا يكتشفه أحد إلّا بعد أن يبني قراراً على نتيجةٍ
لم تُرشَّح.

فهنا تُفحص الأشياء التي تنكسر بلا صوت:

    ١) المدى المقلوب — «من 27 إلى 20» يعطي صفراً ويُقرأ «لا صفقات».
    ٢) المنطقة الزمنية — يومُ المستخدم لا يوم UTC. وقِيس على
       السجلّ: ١٣ صفقة من ٦١٢ يختلف يومها بين التوقيتين، أي أنّ
       ترشيح يومٍ بعينه كان سيخطئ في ٢٪ من الحالات بلا إنذار.
    ٣) وحدة السلوك — «btc» تجد BTCUSDT في الشاشتين لا في واحدة.
    ٤) الحقول المخفيّة — بحثٌ بالرمز لا يمحو «محسومة · يدوية».
"""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── تحميل الدوالّ بلا Django ──
#
# ``views.py`` يستورد Django. والمطلوب هنا أربع دوالّ نقيّة، فتُنتزع
# بـ AST وتُنفَّذ وحدها — اختبارٌ لا يحتاج قاعدة بيانات يبقى سريعاً
# فيُشغَّل، والاختبار الذي لا يُشغَّل ليس اختباراً.
import ast  # noqa: E402

src = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
tree = ast.parse(src)
WANT = {"_clean_symbol", "_one_date", "_date_range", "_apply_date",
        "_watch_filters", "_apply_watch_filters", "_trade_filters"}
picked = [n for n in tree.body
          if isinstance(n, ast.FunctionDef) and n.name in WANT]
check("٠ الدوالّ موجودة", len(picked) == len(WANT),
      str(sorted(WANT - {n.name for n in picked})))

ns: dict = {"MARKETS": ("crypto", "us", "saudi"),
            "UI_TIMEFRAMES": ("15m", "1h", "4h", "1d"),
            "STATUS_FILTERS": {"all": (), "won": ("won",)},
            "STATUS_LABELS": {"all": "الكل", "won": "رابحة"}}
exec(compile(ast.Module(body=picked, type_ignores=[]), "views", "exec"), ns)
clean_symbol = ns["_clean_symbol"]
one_date = ns["_one_date"]
date_range = ns["_date_range"]
apply_date = ns["_apply_date"]


class Req:
    def __init__(self, **kw):
        self.GET = kw


# ── ١) الرمز ──
check("١ يُرفَع إلى الكبير", clean_symbol("btc") == "BTC")
check("  والفراغ يُقصّ", clean_symbol("  eth  ") == "ETH")
check("  والفارغ فارغ", clean_symbol(None) == "" and clean_symbol("") == "")
# خانة الرمز في القاعدة 32 محرفاً — وما زاد لا يطابق شيئاً أبداً
check("  والطويل يُقصّ", len(clean_symbol("A" * 99)) == 32)
check("  والرقمي يمرّ", clean_symbol("2222") == "2222")


# ── ٢) التاريخ ──
check("٢ الصيغة تُقرأ", one_date("2026-08-27") == dt.date(2026, 8, 27))
check("  والفارغ None", one_date("") is None and one_date(None) is None)
for bad in ("27-08-2026", "2026/08/27", "abc", "2026-13-01", "2026-02-30"):
    check(f"  و«{bad}» تُهمَل", one_date(bad) is None, str(one_date(bad)))


# ═══ ٣) المدى المقلوب يُصحَّح ═══
#
# «من 2026-08-27 إلى 2026-08-20» يعطي صفر نتيجة. والصفر يُقرأ «لا
# صفقات في هذه الفترة» — فيبحث المستخدم عن عطبٍ في البيانات وهو في
# إدخاله.
a, b = date_range(Req(**{"from": "2026-08-27", "to": "2026-08-20"}))
check("٣ المقلوب يُبدَّل",
      a == dt.date(2026, 8, 20) and b == dt.date(2026, 8, 27), f"{a}..{b}")
a2, b2 = date_range(Req(**{"from": "2026-08-01", "to": "2026-08-31"}))
check("  والسليم يبقى",
      a2 == dt.date(2026, 8, 1) and b2 == dt.date(2026, 8, 31))
a3, b3 = date_range(Req(**{"from": "2026-08-05"}))
check("  والطرف الواحد يمرّ", a3 == dt.date(2026, 8, 5) and b3 is None)
check("  والفارغ يعطي None", date_range(Req()) == (None, None))


# ═══ ٤) الترشيح بالتوقيت المحلّي لا بـ UTC ═══
#
# ``__date`` في Django مع ``USE_TZ`` يحوّل العمود إلى المنطقة
# النشطة قبل المقارنة. وقِيس على السجلّ الحقيقي: ١٣ صفقة من ٦١٢
# يختلف يومها بين UTC والرياض — فترشيح «8 أغسطس» كان سيُسقط صفقات
# التاسعة مساءً ويضعها في اليوم التالي.
class FakeQS:
    """يسجّل ما طُلب منه — الفحص على الاستعلام المبنيّ لا على النيّة."""

    def __init__(self):
        self.calls: dict = {}

    def filter(self, **kw):
        self.calls.update(kw)
        return self


q = apply_date(FakeQS(), "signal_at", dt.date(2026, 8, 1),
               dt.date(2026, 8, 31))
check("٤ يستعمل __date لا __gte خاماً",
      "signal_at__date__gte" in q.calls and "signal_at__date__lte" in q.calls,
      str(list(q.calls)))
check("  والقيم تواريخ لا نصوص",
      isinstance(q.calls["signal_at__date__gte"], dt.date))
q2 = apply_date(FakeQS(), "created_at", None, None)
check("  وبلا مدىً لا يُرشَّح", q2.calls == {}, str(q2.calls))
q3 = apply_date(FakeQS(), "created_at", dt.date(2026, 8, 5), None)
check("  والطرف الواحد وحده", list(q3.calls) == ["created_at__date__gte"],
      str(list(q3.calls)))


# ── ٥) وحدة السلوك بين الشاشتين ──
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
TPL = ROOT / "web" / "dashboard" / "templates" / "dashboard"
bar = (TPL / "_filterbar.html").read_text(encoding="utf-8")
check("٥ المراقبة تستعمل الدوالّ نفسها",
      "_date_range(request)" in code
      and code.count("_clean_symbol(") >= 3, "نسخة ثانية؟")
check("  والصفقات كذلك", "_apply_date(qs, \"signal_at\"" in code)
# ═══ حقل التاريخ ليس اعتباطياً ═══
#
# ``closed_at`` يُخفي كل صفقة مفتوحة، و``triggered_at`` فارغ في كل
# مراقبة مسلّحة — فأيّ مدىً عليهما يفرّغ الجدول.
check("  والصفقة على وقت الإشارة", '_apply_date(qs, "signal_at"' in code)
check("  والمراقبة على وقت الإنشاء", '"created_at"' in code)
check("  ولا على closed_at", '_apply_date(qs, "closed_at"' not in code)


# ═══ ٥ب) خيارات القائمة من مصدر التحقّق نفسه ═══
#
# الخطر هنا صامت تماماً: تعرض القائمة خياراً يرفضه المُتحقِّق، فيختاره
# المستخدم ويُهمَل بصمت — يرى الخيار محدَّداً في الشريط والجدول غير
# مرشَّح، فيظنّ أنّ السوق بلا صفقات.
#
# فالشرط: ما يُعرَض هو ما يُقبَل. ``MARKETS`` تبني الخيارات
# و``MARKETS`` تتحقّق؛ و``UI_TIMEFRAMES`` كذلك.
check("٥ب خيارات السوق من MARKETS",
      "for m in MARKETS" in code and "market_options()" in code)
check("  والتحقّق بـ MARKETS نفسها",
      'market if market in MARKETS else ""' in code)
check("  وخيارات الفريم من UI_TIMEFRAMES",
      "for t in UI_TIMEFRAMES" in code)
check("  والتحقّق بها", "tf if tf in UI_TIMEFRAMES" in code)

# والأسماء العربية من مكانٍ واحد — ثلاثة قوالب تعرض الأسواق
check("  والتسميات في مصدر واحد", "MARKET_LABELS" in code)
check("  ولا تُكتب في القالب",
      "العملات" not in bar and "السعودي" not in bar, "اسم سوق في القالب")

# والصفحتان تمرّران الخيارات
for page in ("trades.html", "watches.html"):
    html = (TPL / page).read_text(encoding="utf-8")
    check(f"  و{page} يمرّر الأسواق", "market_options=market_options" in html)


# ── ٦) الرمز بحثٌ جزئي ──
check("٦ الرمز icontains لا exact",
      "symbol__icontains" in code and "symbol__exact" not in code)
# والسوق تطابقٌ تامّ لا جزئيّ: «us» بحثاً جزئياً تطابق كل ‏USDT
check("  والسوق تطابقٌ تامّ",
      code.count("filter(market=f[") >= 2, "بحث جزئي في السوق؟")

# ═══ زرّ المسح يمسح كل شيء ═══
#
# زرٌّ اسمه «امسح الترشيح» يترك مرشّحاً قائماً أسوأ من غيابه:
# المستخدم يظنّ أنّه عاد إلى الكلّ وهو في نطاقٍ ضيّق.
clear = re.search(r"qs_set([^%]*)%\}\">امسح", bar)
check("  وزرّ المسح يشمل الجميع",
      clear is not None and all(f"{k}=None" in clear.group(1)
                                for k in ("symbol", "market", "tf",
                                          "from", "to")),
      clear.group(1) if clear else "لا زرّ")
check("  ويظهر عند وجود مرشّح فقط",
      "filters.market or" in bar or "or filters.market" in bar)


# ── ٧) العنوان يحمل المرشّح ──
#
# بلا هذا لا يُنسخ الرابط ولا يعمل زرّ الرجوع.
check("٧ المرشّح في سلسلة الاستعلام",
      '"symbol"] = f["symbol"]' in code or 'parts["symbol"]' in code)
check("  والتاريخ كذلك", 'parts["from"]' in code and 'parts["to"]' in code)


# ── ٨) الشريط جزءٌ واحد ──
for page in ("trades.html", "watches.html"):
    html = (TPL / page).read_text(encoding="utf-8")
    check(f"٨ {page} يضمّ الشريط", "_filterbar.html" in html)
    # التسمية تُمرَّر: «التاريخ» وحدها تترك المستخدم يخمّن أيّ تاريخ
    check("  ويمرّر تسمية التاريخ", "date_label=" in html)

check("  والشريط نموذج GET", 'method="get"' in bar)
# ═══ الحقول المخفيّة ═══
#
# نموذج GET يرسل حقوله وحدها. فبحثٌ بالرمز يمحو ``status`` و
# ``source`` من العنوان، وتقفز الصفحة من «محسومة · يدوية» إلى
# الافتراضي — فيبدو أنّ البحث أعاد نتائج خاطئة وهو أعاد نطاقاً آخر.
check("  ويحمل بقيّة المرشّحات", "qs_hidden" in bar)
owned = re.search(r"\{%\s*qs_hidden([^%]*)%\}", bar)
check("  ويستثني حقوله الظاهرة",
      owned is not None and all(k in owned.group(1)
                                for k in ("symbol", "market", "tf",
                                          "from", "to")),
      owned.group(1) if owned else "لا وسم")
# حقلٌ مخفيّ باسم خانة ظاهرة يُرسل مرّتين، والخادم يأخذ القديمة
for field in ("symbol", "market", "tf", "from", "to"):
    check(f"  ولا ازدواج في {field}",
          bar.count(f'name="{field}"') == 1,
          str(bar.count(f'name="{field}"')))


# ── ٩) المراقبة تنقل المرشّح إلى ندائها ──
#
# الجدول يُبنى من ‎/api/watches/‎ لا من القالب. فبلا نقل المرشّح
# يظهر الشريط ممتلئاً والجدول غير مرشَّح.
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "watches-page.js").read_text(encoding="utf-8")
check("٩ النداء يحمل المرشّح", "filterQuery()" in js)
check("  والمفاتيح محدودة", "FILTER_KEYS" in js)
for k in ("symbol", "market", "tf", "from", "to"):
    check(f"  وفيها {k}", f'"{k}"' in js)
# ═══ الفراغ بسبب المرشّح ليس فراغاً ═══
#
# «لا فرص مراقَبة الآن» مع ١٤٦ مراقبة قائمة رسالةٌ كاذبة المعنى.
check("  والفراغ المرشَّح يُفرَّق", "لا مراقبة تطابق الترشيح" in js)
check("  ويُذكر العدد الكلّي", "meta.total" in js)
check("  والخادم يرسله", '"total": total' in code)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
