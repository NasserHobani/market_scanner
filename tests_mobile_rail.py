# -*- coding: utf-8 -*-
"""القائمة الجانبية على الجوّال — وإشارةٌ مقلوبة أبقتها فوق المحتوى.

═══ العطب ═══

الشريط مثبَّت بـ``inset-inline-end: 0``. و``inline-end`` في واجهةٍ
عربية هو **اليسار** — فهو ملتصقٌ بالحافّة اليسرى.

وإخفاؤه يحتاج دفعه يساراً: ``translateX(-100%)``. وكان مكتوباً
``translateX(+100%)`` لـ‏RTL، فيُدفَع **يميناً** بمقدار عرضه:

    مخفيّ صحيحاً   [شريط][=== المحتوى ===]
    ما كان يقع     [فراغ][شريط][المحتوى]

فلا يختفي — يزحف إلى وسط الشاشة ويقف فوق المحتوى ويبتلع اللمس.

═══ ولماذا لم يظهر على الحاسوب ═══

الشريط هناك ظاهرٌ دائماً ولا يُخفى، والقاعدة كلّها داخل استعلام
الجوّال. فالعطب لا يُرى إلّا على شاشةٍ دون ‎992px‎.

═══ والسبب الجذريّ: خلط المحاور ═══

``inset-inline-*`` منطقية تنعكس مع الاتجاه. و``translateX``
فيزيائية لا تنعكس أبداً. وخلطُ النوعين يقلب الإشارة في اتّجاهٍ
واحد دون الآخر — فيعمل أحدهما ويُكسر الثاني.

و``.ds-drawer`` في الملفّ نفسه يفعلها صحيحةً. فالقياس عليه.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
CSS = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "design-system.css").read_text(encoding="utf-8")
BASE = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "base.html").read_text(encoding="utf-8")

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def _rule(selector: str, src: str = CSS) -> str:
    """جسد أوّل قاعدةٍ لهذا المحدِّد — بلا تعليقات.

    التعليقات تشرح الإشارة المقلوبة نصّاً، فمطابقتها تجد الشرح
    لا الكود. وهو الفخّ الذي وقع في هذه الجلسة أربع مرّات.
    """
    clean = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", clean)
    return m.group(1) if m else ""


# ═══════════ ١) اتّفاق الشريط والدرج ═══════════
#
# كلاهما مثبَّت بـ‎inset-inline-end‎، فيجب أن يُخفَيا بالإشارة
# نفسها. واختلافُهما دليلٌ على أنّ أحدهما مقلوب.
rail = _rule(".ds-rail")
drawer = _rule(".ds-drawer")
check("١ الدرج مثبَّت بـ‎inline-end‎", "inset-inline-end" in drawer, drawer[:60])
check("  والشريط كذلك", "inset-inline-end" in rail, rail[:60])

_rail_rtl = "translateX(-100%)" in rail
check("  والشريط يُخفى بـ‎-100%‎ (العربية)", _rail_rtl,
      rail.replace("\n", " ")[:120])
check("  والدرج كذلك", "translateX(-100%)" in drawer,
      drawer.replace("\n", " ")[:120])


# ═══════════ ٢) لا قاعدة ‎rtl‎ تقلبها ═══════════
#
# هذا هو الفحص الذي كان سيمسك العطب: قاعدةٌ لاحقة تدهس الأساس
# بالإشارة المعاكسة.
_clean = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
_rtl_flip = re.search(
    r'html\[dir="rtl"\]\s*\.ds-rail\s*\{[^}]*translateX\(100%\)', _clean)
check("٢ لا قاعدة rtl تدفع الشريط يميناً", _rtl_flip is None,
      _rtl_flip.group(0)[:90] if _rtl_flip else "")

# والإنجليزية هي الاستثناء — كما في الدرج
_ltr = re.search(
    r'html\[dir="ltr"\]\s*\.ds-rail\s*\{[^}]*translateX\(100%\)', _clean)
check("  و‎ltr‎ هي الاستثناء", _ltr is not None)
_drawer_ltr = re.search(
    r'\[dir="ltr"\]\s*\.ds-drawer\s*\{[^}]*translateX\(100%\)', _clean)
check("  والدرج يتبع القاعدة نفسها", _drawer_ltr is not None)

# والمفتوح بلا إزاحة في الاتّجاهين
check("  والمفتوح ‎transform: none‎",
      ".ds-rail.is-open" in _clean and
      re.search(r"\.ds-rail\.is-open[^{]*\{[^}]*transform:\s*none", _clean)
      is not None)


# ═══════════ ٣) مقاس الجوّال ═══════════
_mobile = ""
_m = re.search(r"@media \(max-width: 991\.98px\)\s*\{(.*?)\n\}", _clean, re.S)
if _m:
    _mobile = _m.group(1)
check("٣ وُجد استعلام الجوّال", bool(_mobile))
# ‏vh تُقاس على أطول حالة في سفاري، فيُدفَع آخر عنصرٍ تحت الحافّة
check("  والارتفاع ‎dvh‎ لا ‎vh‎", "100dvh" in _mobile)
check("  والعرض بالنسبة لا بالبكسل", "86vw" in _mobile or "vw" in _mobile,
      _mobile[:80])
# ‏viewport-fit=cover مضبوط، فبلا env يقع آخر عنصرٍ تحت شريط المنزل
check("  والحوافّ الآمنة محسوبة", "safe-area-inset" in _mobile)
check("  والقالب يطلب ‎viewport-fit‎", "viewport-fit=cover" in BASE)
# الإصبع ليس مؤشّراً: أقلّ هدفٍ موثوق 44px
_mh = re.search(r"min-height:\s*(\d+)px", _mobile)
check("  وهدف اللمس ‎≥44px‎", bool(_mh) and int(_mh.group(1)) >= 44,
      _mh.group(1) if _mh else "غائب")


# ═══════════ ٤) الخلفية لا تتحرّك ═══════════
#
# بلا قفلٍ يمرّر الإصبعُ الصفحةَ تحت القائمة، فتُغلق على موضعٍ
# غير الذي فُتحت منه.
check("٤ صنف القفل معرَّف",
      re.search(r"body\.rail-open\s*\{[^}]*overflow:\s*hidden", _clean)
      is not None)
_js = "\n".join(l for l in BASE.splitlines()
                if not l.strip().startswith("/*")
                and not l.strip().startswith("*"))
check("  والجافاسكربت يضعه", 'classList.toggle("rail-open"' in _js)
check("  ويُزيله عند الإغلاق", "setOpen(false)" in _js)
# والتركيز ينتقل إلى القائمة ويعود — من يتنقّل بلوحة المفاتيح
check("  والتركيز ينتقل ويعود",
      "first.focus()" in _js and "openBtn.focus()" in _js)
check("  و‎Escape‎ يُغلق", '"Escape"' in _js)


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
