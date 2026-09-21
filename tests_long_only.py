# -*- coding: utf-8 -*-
"""المنصّة شراءٌ فقط — ولا بيع على المكشوف.

═══ أين كانت الثغرة ═══

محرّك التوصية لا يُنتج بيعاً: يعيد ``buy`` أو ``—``. لكنّ المداخل
تقبل اتّجاهاً من الخارج وتثق به:

    advice_views   ``request.POST.get("side")``   ← من المتصفّح
    trades         ``reco.get("side", "buy")``
    scan           ``reco.get("side", "buy")``

فطلبٌ واحد بـ``side=sell`` يفتح صفقة بيعٍ في نظامٍ كلُّ حسابٍ فيه
يفترض الشراء: الوقف فوق الدخول، و‏R محسوبة بالمقلوب، والمحفظة
الورقية تبيع ما لا تملكه.

و«المحرّك لا يُنتج بيعاً اليوم» ليست ضماناً — الضمان يُكتب.

═══ والرفض لا التصحيح ═══

تحويل ``sell`` إلى ``buy`` بهدوء أسوأ ما يمكن: إشارةٌ هابطة تصير
مركزاً صاعداً — يُفتح الشراء في اللحظة التي قال فيها التحليل
«اهبط». فالرفض، ويُقال سببه.

═══ والتاريخ لا يُمسّ ═══

قياسُ الماضي ليس فتحَ صفقة. فصفقات البيع القديمة في السجلّ
تُقرأ وتُحسم وتُحدَّث — والمنع على **الإنشاء** وحده. ومنعُ الحفظ
عليها يجمّدها «مفتوحة» إلى الأبد ويُفسد كل نسبةٍ تُحسب على
المغلقات.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner import direction as D  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ═══════════ ١) التمييز ═══════════
for w in ("sell", "SELL", " Sell ", "short", "بيع", "هابط"):
    check(f"١ يُعرَف بيعاً: {w!r}", D.is_short(w) is True)
for w in ("buy", "BUY", "long", "spot", "شراء"):
    check(f"  ويُعرَف شراءً: {w!r}", D.is_long(w) is True)
# ═══ والمجهول ليس بيعاً ولا شراءً ═══
#
# عدُّه شراءً يجعل خطأً إملائياً يفتح صفقة — وهو الصنف نفسه الذي
# جعل «sell» تمرّ: الثقة بما يُمرَّر.
check("  والمجهول ليس أحدهما",
      not D.is_short("xyz") and not D.is_long("xyz"))


# ═══════════ ٢) الإذن ═══════════
check("٢ الشراء مسموح", D.allowed("buy") is True)
check("  والفارغ مسموح (افتراضه شراء)", D.allowed("") is True)
check("  والغائب مسموح", D.allowed(None) is True)
check("  والبيع ممنوع", D.allowed("sell") is False)
check("  والمجهول ممنوع", D.allowed("xyz") is False)


# ═══════════ ٣) ensure_long ═══════════
check("٣ الشراء يعود buy", D.ensure_long("long") == "buy")
check("  والفارغ يعود buy", D.ensure_long("") == "buy")
for bad in ("sell", "short", "بيع"):
    try:
        D.ensure_long(bad)
        check(f"  و{bad!r} يرمي", False, "لم يرمِ")
    except D.ShortNotSupported:
        check(f"  و{bad!r} يرمي", True)
# ═══ ولا يُصحَّح بصمت ═══
#
# لو أعاد ``buy`` لبيعٍ لكان أخطر من عدم وجوده: مركزٌ صاعد على
# إشارةٍ هابطة، بلا أثرٍ يقول ما جرى.
_coerced = None
try:
    _coerced = D.ensure_long("sell")
except D.ShortNotSupported:
    pass
check("  ولا يُحوَّل البيع إلى شراء", _coerced is None, str(_coerced))
# والرسالة تقول من حاول — مسارٌ من خمسة هو ما يحتاج الإصلاح
check("  والرسالة تذكر الموضع",
      "المحفظة" in D.reject_reason("sell", where="المحفظة"),
      D.reject_reason("sell", where="المحفظة"))
check("  والمسموح بلا سبب رفض", D.reject_reason("buy") == "")


# ═══════════ ٤) المداخل محروسة ═══════════
def _src(rel: str) -> str:
    """مصدرٌ بلا تعليقات ولا توثيق — التعليق يشرح ولا يُنفَّذ."""
    txt = (ROOT / rel).read_text(encoding="utf-8")
    try:
        tree = ast.parse(txt)
    except SyntaxError:
        return txt
    out = txt
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out = out.replace(doc, "", 1)
    return "\n".join(l for l in out.splitlines()
                     if not l.strip().startswith("#"))


_adv = _src("web/dashboard/advice_views.py")
check("٤ التوصية اليدوية تُرفَض عند الباب",
      "reject_reason" in _adv and "status=400" in _adv)
check("  ولا تُقرأ side من POST بلا فحص",
      'request.POST.get("side")' not in _adv
      or "reject_reason" in _adv.split('request.POST.get("side")')[1][:900])

_tr = _src("web/dashboard/trades.py")
check("  وفتح الصفقة يسأل direction", "_dir.allowed" in _tr)
check("  ويعيد None لا يُصحّح", "return None" in
      _tr.split("_dir.allowed")[1][:260])
check("  والخطّة تُبنى شراءً صراحةً", "side=_dir.LONG" in _tr)

_scan = _src("web/dashboard/management/commands/scan.py")
check("  والمراقبة كذلك", "_dir.allowed" in _scan)
# مراقبةُ بيعٍ محفوظة تعني صفقةَ بيعٍ مؤجّلة حين يتحقّق شرطها
check("  وتُحفَظ شراءً", "side=_dir.LONG" in _scan)


# ═══════════ ٥) الحارس الأخير في النموذج ═══════════
_models = _src("web/dashboard/models.py")
check("٥ ‏Trade.save يحرس", "ensure_long" in _models)
# ═══ على الإنشاء وحده ═══
#
# صفقات البيع القديمة يجب أن تبقى قابلةً للحسم والتحديث — وإلّا
# جُمّدت «مفتوحة» أبداً وفسدت كل نسبةٍ تُحسب على المغلقات.
check("  على الإنشاء لا التحديث", "self.pk is None" in _models)
check("  ويستدعي super بعده", "super().save(" in _models)


# ═══════════ ٦) القاعدة مكتوبة لا مستنتَجة ═══════════
check("٦ ‏LONG_ONLY معرَّفة", D.LONG_ONLY is True)
check("  و‎LONG‎ هي buy", D.LONG == "buy")
_dsrc = (ROOT / "scanner" / "direction.py").read_text(encoding="utf-8")
check("  والوحدة تشرح سبب الرفض", "الرفض لا التصحيح" in _dsrc)
check("  وتستثني قياس الماضي", "قياسُ الماضي ليس فتحَ صفقة" in _dsrc)


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name
          + (f"   [{extra}]" if extra and not ok else ""))
bad = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad)}/{len(results)} "
      + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
sys.exit(1 if bad else 0)
