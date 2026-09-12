# -*- coding: utf-8 -*-
"""حظر الرموز — قرار المستخدم، يُقطع من الجذر لا يُخفى.

═══ الفرق عن الفرز القائم ═══

``scanner/compliance.py`` يفرز ولا يحكم: يصنّف مبدئياً ويقول
«يحتاج مراجعة»، والرمز **يُمسح ويُحلَّل** ويظهر موسوماً. وقواعده
في ملفّ ‏YAML يحتاج تحريراً وإعادة تشغيل.

والحظر هنا قرارُ المستخدم: يُقطع الرمز من قائمة المسح قبل أوّل
نداء شبكة، ويسري على المسح التالي بلا إقلاع.

═══ ولماذا لا يكفي الإخفاء ═══

الإخفاء في العرض يترك الرمز يُجلب ويُحلَّل — فيستهلك زمن المسح،
وتبقى الصفقة قابلة للفتح من مسارٍ آخر: مراقبةٌ سُلّحت قبل الحظر،
أو توصيةٌ مخزّنة، أو ضغطة يدوية.

فهذا الملفّ يحرس المسارات الأربعة.
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


# ── تحميل المنطق النقيّ بلا Django ──
src = (ROOT / "web" / "dashboard" / "blocklist.py").read_text(encoding="utf-8")
tree = ast.parse(src)
PURE = {"base_of", "is_blocked", "filter_symbols", "count", "_table"}
keep = [n for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name in ("_load",))]
ns: dict = {"__name__": "blocklist"}
exec(compile(ast.Module(body=keep, type_ignores=[]), "b", "exec"), ns)
base_of = ns["base_of"]

# جدولٌ مزيّف بدل القاعدة
ns["_cache"]["at"] = 9e18          # يمنع إعادة القراءة
ns["_cache"]["data"] = {
    "crypto": {"exact": {"XRPUSDT"}, "base": {"AAVE", "COMP"}},
    "saudi": {"exact": set(), "base": {"1120"}},
}
is_blocked = ns["is_blocked"]
filter_symbols = ns["filter_symbols"]


# ═══ ١) الأصل يحظر كل أزواجه ═══
#
# من حظر ‏AAVE حظر ‏AAVEUSDT. ولو لزم تكرار الحظر لكل زوج لأفلت
# الزوج الجديد بلا أن ينتبه أحد.
check("١ الأصل يُستخرج", base_of("AAVEUSDT", "crypto") == "AAVE")
for q in ("USDC", "BUSD", "FDUSD", "BTC", "ETH"):
    check(f"  ولاحقة {q}", base_of("AAVE" + q, "crypto") == "AAVE")
check("  والسعودي", base_of("1120.SR", "saudi") == "1120")
check("  والأمريكي كما هو", base_of("AAPL", "us") == "AAPL")
# ولا يُقصّ ما ليس لاحقة: رمزٌ اسمه ‏BTC نفسه لا يصير فارغاً
check("  ولا يُفرَّغ الرمز", base_of("BTC", "crypto") == "BTC")
check("  والحروف تُرفع", base_of("aaveusdt", "crypto") == "AAVE")


# ── ٢) المطابقة ──
check("٢ الأصل يحظر الزوج", is_blocked("crypto", "AAVEUSDT"))
check("  وزوجاً آخر للأصل", is_blocked("crypto", "AAVEBTC"))
check("  والدقيق يحظر نفسه", is_blocked("crypto", "XRPUSDT"))
# «دقيق» يعني هذا الرمز وحده — لا أصله
check("  والدقيق لا يحظر غيره", not is_blocked("crypto", "XRPBTC"))
check("  وغير المحظور يمرّ", not is_blocked("crypto", "BTCUSDT"))
# ═══ الحظر لا يعبر الأسواق ═══
#
# ‏1120 محظور في السعودي، ورمزٌ مشابه في سوقٍ آخر شركةٌ أخرى.
check("  ولا يعبر الأسواق", not is_blocked("us", "1120"))
check("  والسعودي يُطابَق", is_blocked("saudi", "1120.SR"))
check("  وسوقٌ بلا حظر", not is_blocked("crypto2", "AAVEUSDT"))


# ═══ ٣) المحظور يُعاد ليُذكر ═══
#
# حذفٌ صامت يجعل المستخدم يرى «320 رمزاً» بدل 326 ولا يعرف أين
# ذهبت الستّة.
allowed, blocked = filter_symbols(
    "crypto", ["BTCUSDT", "AAVEUSDT", "ETHUSDT", "XRPUSDT", "COMPUSDT"])
check("٣ المسموح يمرّ", allowed == ["BTCUSDT", "ETHUSDT"], str(allowed))
check("  والمحظور يُعاد",
      set(blocked) == {"AAVEUSDT", "XRPUSDT", "COMPUSDT"}, str(blocked))
check("  والفارغ لا يكسر", filter_symbols("crypto", []) == ([], []))
check("  و None كذلك", filter_symbols("crypto", None) == ([], []))


# ── ٤) الحراسة في المسارات الأربعة ──
scan = (ROOT / "web" / "dashboard" / "management" / "commands"
        / "scan.py").read_text(encoding="utf-8")
scode = "\n".join(l for l in scan.splitlines()
                  if not l.strip().startswith("#"))
check("٤ قائمة المسح تُصفّى", "blocklist.filter_symbols(cfg.name, symbols)"
      in scode)
# ═══ قبل بوّابة الحداثة ═══
#
# التصفية بعدها تعني أنّ المحظور يدخل في حساب «كم رمزاً متأخّر»،
# فيُرفض المسح كلّه بسبب رموزٍ لن تُمسح.
check("  قبل بوّابة الحداثة",
      scode.index("filter_symbols") < scode.index("scan_freshness_gate"))
check("  والعدد يُذكر", "استُبعدت" in scan)
# وعطب القائمة لا يمنع مسحاً
check("  وعطبها لا يوقف المسح", "قائمة الحظر:" in scan)

check("  والمراقبة محروسة",
      "is_blocked(result_row.market, result_row.symbol)" in scode)
trades = (ROOT / "web" / "dashboard" / "trades.py").read_text(encoding="utf-8")
tcode = "\n".join(l for l in trades.splitlines()
                  if not l.strip().startswith("#"))
check("  وفتح الصفقة الآلي", tcode.count("blocklist.is_blocked") >= 2,
      str(tcode.count("blocklist.is_blocked")))
check("  واليدوي", "def open_manual" in trades
      and trades.index("def open_manual") < trades.rindex("is_blocked"))


# ═══ ٥) النظام لا يفتي ═══
#
# لا يُضاف رمز إلى القائمة تلقائياً — لا من الفرز ولا من غيره.
views = (ROOT / "web" / "dashboard"
         / "block_views.py").read_text(encoding="utf-8")
# النسخة الأولى منعت ``get_or_create`` في الملفّات كلّها، فرصدت
# ``Trade.objects.get_or_create`` — وهو استعمالٌ مشروع لا علاقة له.
# والشرط الحقيقي أضيق: لا يكتب في ``BlockedSymbol`` أحدٌ خارج
# واجهتها.
writers = []
for path in sorted((ROOT / "web" / "dashboard").rglob("*.py")):
    if path.name in ("block_views.py", "models.py") or "migrations" in str(path):
        continue
    text = path.read_text(encoding="utf-8")
    body = "\n".join(l for l in text.splitlines()
                      if not l.strip().startswith("#"))
    for verb in (".create(", ".get_or_create(", ".update(", ".delete(",
                 ".save("):
        if "BlockedSymbol" in body and f"BlockedSymbol.objects{verb}" in body:
            writers.append(f"{path.name}{verb}")
check("٥ لا كاتب خارج الواجهة", not writers, str(writers))
check("  ولا في الماسح", "BlockedSymbol" not in scode)
check("  ولا في الصفقات", "BlockedSymbol" not in tcode)
# والوحدة نفسها تقرأ ولا تكتب
check("  والوحدة تقرأ فقط",
      ".values(" in src and "BlockedSymbol.objects.create" not in src)
check("  والإضافة من الواجهة وحدها",
      "get_or_create" in views and "require_POST" in views)
html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "blocked.html").read_text(encoding="utf-8")
check("  والصفحة تعلن ذلك", "النظام لا يفتي" in html)
check("  وتفرّق عن الفرز", "يحتاج مراجعة" in html and "لا يمنع" in html)
# وحقل المصدر: تذكرةٌ لصاحب القرار متى يراجع
check("  وللمصدر حقل", 'name="source"' in html)


# ── ٦) الأثر فوريّ بلا إقلاع ──
check("٦ للذاكرة عمر قصير", ns["CACHE_SECONDS"] <= 60,
      str(ns["CACHE_SECONDS"]))
check("  وتُبطَل عند التعديل", "blocklist.refresh()" in views)
check("  في كل مسار تعديل",
      views.count("blocklist.refresh()") >= 3,
      str(views.count("blocklist.refresh()")))


# ── ٧) الواجهة ──
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "app.js").read_text(encoding="utf-8")
check("٧ زرّ الحظر في صفّ الماسح", "sym-block" in js)
# الأثر واسع — يُستبعد من المسح كلّه لا من هذا الصفّ
check("  ويؤكّد قبل الحظر", "confirm(" in js)
check("  ويدلّ على الرفع", "الرموز المحظورة" in js)
scanner_html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
                / "scanner.html").read_text(encoding="utf-8")
check("  وللعمود رأس", "حظر" in scanner_html)
# عمودٌ أُضيف فوجب أن يتّسع صفّ «لا نتائج»
check("  و colspan يطابق", 'colspan="23"' in js, "عمودٌ مضاف بلا تحديث")

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for n in ("api_blocked", "api_block_add", "api_block_remove",
          "api_block_toggle", "api_block_check"):
    check(f"  و{n} مسجَّل", n in urls)


# ═══ ١٠) الحجب في العرض لا في المسح وحده ═══
#
# وقع فعلاً: حُظر ‏ACXUSDT وبقيت له ثلاثة عشر صفّاً مخزّنة تُعرض،
# فبدا الحظر معطّلاً. الحرس يمنع المسح **القادم**، وما مُسح قبله
# باقٍ في القاعدة.
check("١٠ للعرض مرشّح", "def drop_blocked" in src)
views_py = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
vcode2 = "\n".join(l for l in views_py.splitlines()
                   if not l.strip().startswith("#"))
check("  وجدول الماسح يُصفّى",
      "blocklist.drop_blocked(list(run.results.all())" in vcode2)
check("  والمراقبة كذلك", "blocklist.drop_blocked(rows)" in vcode2)
gold = (ROOT / "web" / "dashboard"
        / "golden_views.py").read_text(encoding="utf-8")
check("  والذهبية كذلك", "blocklist.drop_blocked" in gold)
sq = (ROOT / "web" / "dashboard"
      / "squeeze_views.py").read_text(encoding="utf-8")
check("  والانضغاط كذلك", "blocklist.drop_blocked" in sq)
pes_v = (ROOT / "web" / "dashboard" / "pes_views.py").read_text(encoding="utf-8")
check("  و PES كذلك", "blocklist.drop_blocked" in pes_v)
# ═══ ولا تُحجب مراكزك ═══
#
# صفقةٌ مفتوحة على رمزٍ حُظر لاحقاً مالُك — وإخفاؤها يمنعك من
# إدارتها. فالحجب للاكتشاف لا للملكية.
trades_v = (ROOT / "web" / "dashboard" / "trades.py").read_text(encoding="utf-8")
check("  والصفقات لا تُحجب", "drop_blocked" not in trades_v,
      "أُخفيت مراكز قائمة؟")
check("  والقاعدة موثّقة", "لا يُحجب من **مراكزك**" in src)


# ═══ ١١) الفشل لا يُقرأ نجاحاً ═══
#
# ``postJSON`` لا يرفض أبداً: يعيد ``{ok:false, reason}``. فـ
# ``.catch`` وحده شبكةٌ لا يقع فيها شيء — ومرّ فشلُ حظرٍ كأنّه
# نجاح، فظنّ المستخدم أنّه حظر رمزين وواحدٌ سُجّل.
base_html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
             / "base.html").read_text(encoding="utf-8")
check("١١ postJSON يعيد ok:false", '{ ok: false, reason: why }' in base_html)
app_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
          / "app.js").read_text(encoding="utf-8")
blk_block = app_js.split("sym-block")[-1][:2600]
check("  وزرّ الحظر يفحص ok", "d.ok === false" in blk_block, "يبتلع الفشل")
check("  ويُخبر المستخدم", "window.alert" in blk_block)
blocked_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
              / "blocked-page.js").read_text(encoding="utf-8")
check("  ونموذج اللصق كذلك", "d.ok === false" in blocked_js)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
