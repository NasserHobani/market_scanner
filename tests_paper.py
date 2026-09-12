# -*- coding: utf-8 -*-
"""المحفظة الورقية — الحساب الذي يجب أن يكون صحيحاً قبل المال الحقيقي.

═══ ثلاثة أشياء تُسقط أغلب المحاكيات ═══

**الرسوم.** بينانس ‎0.1٪‎ لكل طرف — ‎0.2٪‎ ذهاباً وإياباً. وصفقةٌ
ربحت ‎0.15٪‎ **خاسرة**. وقِيس هنا: حدّ التعادل ‎0.30٪‎ حركة بعد
الرسوم والانزلاق.

**الانزلاق.** يُفترَض ضدّك في الطرفين. وافتراض التنفيذ المثالي
يجعل المحاكاة تربح ما لا يُربَح.

**التحجيم.** «ادخل بألف دولار» يجعل الخسارة تتغيّر ببُعد الوقف.
والتحجيم بالمخاطرة يثبّتها ويغيّر الكمّية — وهو أصل إدارة المخاطر.

═══ والهدف ليس وعداً ═══

يوقف الفتح عند بلوغه ولا يضمن بلوغه.
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


# ── تحميل الدوالّ النقيّة بلا Django ──
src = (ROOT / "web" / "dashboard" / "paper.py").read_text(encoding="utf-8")
tree = ast.parse(src)
DJANGO = {"can_open", "open_trade", "close_trade", "mark_and_settle",
          "summary", "get_or_create_account"}
keep = [n for n in tree.body
        if not (isinstance(n, ast.FunctionDef) and n.name in DJANGO)]
ns: dict = {"__name__": "paper"}
exec(compile(ast.Module(body=keep, type_ignores=[]), "p", "exec"), ns)
DEFAULTS = ns["DEFAULTS"]
size = ns["position_size"]
fees_on = ns["fees_on"]
slip = ns["_slip"]
cfg = dict(DEFAULTS)


# ═══ ١) التحجيم يثبّت الخسارة ═══
#
# مهما تغيّر بُعد الوقف، الخسارة المخطَّطة واحدة.
bal = 10000.0
for entry, stop in ((100.0, 95.0), (100.0, 90.0), (50.0, 47.5)):
    s = size(bal, entry, stop, cfg)
    check(f"١ وقف {abs(entry - stop) / entry:.0%} مخاطرته 1٪",
          abs(s["risk_amount"] - 100.0) < 1e-6, str(s["risk_amount"]))
# والكمّية تتغيّر عكسياً مع بُعد الوقف
a = size(bal, 100.0, 95.0, cfg)["quantity"]
b = size(bal, 100.0, 90.0, cfg)["quantity"]
check("  والكمّية تنقص كلّما بعُد الوقف", a > b, f"{a} مقابل {b}")


# ═══ ٢) الوقف القريب لا يعطي مركزاً هائلاً ═══
#
# مخاطرة ‎1٪‎ ووقفٌ على بعد ‎0.1٪‎ تعني مركزاً بعشرة أضعاف الرصيد
# لولا السقف.
tight = size(bal, 100.0, 99.9, cfg)
check("٢ السقف يُطبَّق", tight["capped"], str(tight))
check("  والقيمة لا تتجاوزه",
      tight["notional"] <= bal * cfg["max_position_pct"] / 100 + 1e-6,
      str(tight["notional"]))
# والمخاطرة الفعلية تنقص عن المخطَّطة — ويُقال ذلك لا يُخفى
check("  والمخاطرة الفعلية تنقص",
      tight["risk_amount"] < 100.0 and tight["risk_pct_actual"] < 1.0,
      str(tight["risk_pct_actual"]))
check("  والوقف = الدخول يُرفض",
      size(bal, 100.0, 100.0, cfg)["ok"] is False)


# ═══ ٣) الرسوم تقلب الرابح خاسراً ═══
#
# هذا أكثر ما يُضلّل في المحاكيات: عرض الربح قبل الرسوم.
qty, entry = 100.0, 100.0
notional = qty * entry
for move, should_lose in ((0.15, True), (0.25, False), (1.0, False)):
    exit_px = entry * (1 + move / 100)
    proceeds = qty * exit_px
    net = (proceeds - notional) - fees_on(notional, cfg) - fees_on(proceeds, cfg)
    check(f"٣ حركة {move}٪ " + ("خاسرة بعد الرسوم" if should_lose
                                else "رابحة"),
          (net < 0) is should_lose, f"{net:.2f}")
# وحدّ التعادل يساوي الرسوم والانزلاق مجتمعين
be = 2 * cfg["fee_pct"] + 2 * cfg["slippage_pct"]
check("  وحدّ التعادل معلوم", abs(be - 0.30) < 1e-9, f"{be}٪")


# ═══ ٤) الانزلاق ضدّك في الطرفين ═══
#
# افتراض التنفيذ المثالي يجعل المحاكاة تربح ما لا يُربَح.
check("٤ الشراء أغلى", slip(100.0, cfg, buying=True) > 100.0)
check("  والبيع أرخص", slip(100.0, cfg, buying=False) < 100.0)
check("  وبلا انزلاق لا فرق",
      slip(100.0, {"slippage_pct": 0}, buying=True) == 100.0)


# ── ٥) الافتراضات معقولة ──
check("٥ المخاطرة ≤ 2٪", DEFAULTS["risk_per_trade_pct"] <= 2.0,
      str(DEFAULTS["risk_per_trade_pct"]))
check("  ورسوم بينانس 0.1٪", DEFAULTS["fee_pct"] == 0.1)
check("  وحدّ خسارة يومية", DEFAULTS["max_daily_loss_pct"] > 0)
check("  وسقف للمراكز", DEFAULTS["max_open_positions"] >= 1)
check("  وأدنى عائد/مخاطرة ≥ 1", DEFAULTS["min_rr"] >= 1.0)


# ═══ ٦) الحرّاس ═══
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
check("٦ حدّ المراكز المتزامنة", "max_open_positions" in code)
check("  وحدّ الخسارة اليومية", "max_daily_loss_pct" in code)
# الهدف يوقف الفتح — ولا يزعم ضمانه
check("  والهدف يوقف الفتح", "توقّف الفتح" in src)
check("  والمحظور لا يُفتح", "blocklist.is_blocked" in code)
check("  والوقف فوق الدخول يُرفض", "ليست شراءً" in src)
check("  ورمزٌ مفتوح لا يُكرَّر", "one_trade_per_symbol" in code)


# ═══ ٧) الوقف يُفحص قبل الهدف ═══
#
# الشمعة لا تخبرنا أيّهما لُمس أوّلاً، فيُفترَض الأسوأ.
i_stop = code.index("px <= t.stop")
i_target = code.index("px >= t.target")
check("٧ الوقف أوّلاً", i_stop < i_target)


# ═══ ٨) الربح المحفوظ صافٍ بعد الرسوم ═══
check("٨ الصافي يُخصم منه الطرفان",
      "gross - trade.fee_in - fee_out" in code)
check("  و R من المخاطرة المخطَّطة",
      "net / trade.risk_amount" in code)
# والرصيد يتغيّر بالنقد الفعلي لا بالربح
check("  والنقد يُخصم عند الفتح", "account.balance -= cost" in code)
check("  ويُعاد عند الإغلاق",
      "account.balance += proceeds - fee_out" in code)


# ── ٩) الإعدادات تُتحقّق قبل الحفظ ──
views = (ROOT / "web" / "dashboard"
         / "paper_views.py").read_text(encoding="utf-8")
vcode = "\n".join(l for l in views.splitlines()
                  if not l.strip().startswith("#"))
check("٩ لكل إعداد مدى", "NUM = {" in vcode)
check("  والخارج عنه يُرفض", "خارج المدى" in views)
check("  ورأس المال موجب", "يجب أن يكون موجباً" in views)
# ═══ التصفير يحذف الصفقات ═══
#
# رصيدٌ جديد وصفقاتٌ قديمة يُنتجان إحصاءً لا معنى له.
check("  والتصفير يحذف", ".delete()" in vcode)


# ── ١٠) الواجهة ──
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "paper-page.js").read_text(encoding="utf-8")
check("١٠ الرسوم عمودٌ مستقلّ",
      "fees_total" in js and 'esc(t.symbol)' in js)
check("  وتبويبات الحالات",
      all(f'data-tab="{k}"' in
          (ROOT / "web" / "dashboard" / "templates" / "dashboard"
           / "paper.html").read_text(encoding="utf-8")
          for k in ("open", "won", "lost")))
check("  والفشل يُفحص", js.count("d.ok === false") >= 3,
      str(js.count("d.ok === false")))
check("  والتصفير يؤكَّد", "confirm(" in js)
html = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "paper.html").read_text(encoding="utf-8")
check("  والصفحة تنفي الضمان", "لا وعدٌ ببلوغه" in html)
check("  وتذكر حدّ التعادل", "0.3" in html)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for n in ("api_paper", "api_paper_settings", "api_paper_reset",
          "api_paper_tick", "api_paper_close"):
    check(f"  و{n} مسجَّل", n in urls)
cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
check("  ولها مهمّة مجدولة", '"paper": _h_paper' in cron)
eng = (ROOT / "web" / "dashboard"
       / "paper_engine.py").read_text(encoding="utf-8")
# التقييم قبل الفتح: صفقةٌ بلغت وقفها تُحرّر مقعداً ونقداً
# المطابقة على النداء لا على الاسم: ``open_trades`` (متغيّر
# المفتوحة) يحوي «open_trade» فيسبق التقييم نصّاً لا ترتيباً.
check("  والتقييم قبل الفتح",
      eng.index("paper.mark_and_settle(") < eng.index("paper.open_trade("))


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
