# -*- coding: utf-8 -*-
"""أدواتٌ للفواحص — ومنها التجريد الذي أخطأناه أربع مرّات.

═══ العطب المتكرّر ═══

كثيرٌ من الفواحص هنا تقرأ **مصدر** وحدةٍ وتطابق فيه نصّاً:

    check("لا قراءة من iloc[-1]", "iloc[-1]" not in code)

والمصيدة أنّ التعليق وسلسلة التوثيق يشرحان غالباً **لماذا**
نتجنّب الشيء — فتجد المطابقةُ الشرحَ وتحسبه كوداً:

    ""\"... والقراءة من ``iloc[-1]`` تعطي انقلاباً يظهر ويختفي""\"
                          ↑ الفحص وجدها هنا وأعلن العطب

ووقع هذا في ``tests_pes_history`` و``tests_ship`` و``tests_docker``
و``tests_supertrend`` — أربع مرّات، وكلّها في جلسةٍ واحدة. والقياس:
**٩٥ موضعاً في ٤٠ ملفّاً** يعيد كلٌّ منها كتابة التجريد بصيغته،
وبعضها ينسى التوثيق، وبعضها ينسى التعليق الذيليّ.

فالتجريد هنا مرّةً واحدة، صحيحاً، ويُستورَد.

═══ ولماذا ``tokenize`` لا قصُّ الأسطر ═══

الصيغ السابقة كانت تحذف السطر إن **بدأ** بـ``#``. وهي آمنة لكنّها
ناقصة: التعليق الذيليّ يبقى.

    st_line = None      # لم يُحسب بعد   ← «لم يُحسب» تبقى في النصّ

والحذف بـ``line.split("#")[0]`` أسوأ: يقطع كل سلسلةٍ فيها ``#`` —
وألوان CSS في هذا المشروع كلّها ``"#3ddc97"``. فتُشوَّه الشيفرة
ويُفحَص شيءٌ آخر.

و``tokenize`` يعرف الفرق بين تعليقٍ وسلسلة، فيُقصّ بموضعه بالضبط.
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

__all__ = [
    "strip_comments", "strip_docstrings", "code_of", "source_of",
    "body_of", "css_rule", "js_code", "Checks",
]


# ═══════════════════════════════════════════════════════════════
#  بايثون
# ═══════════════════════════════════════════════════════════════

def strip_comments(src: str) -> str:
    """يحذف تعليقات بايثون — الذيليّة منها والسطرية.

    ولا يمسّ السلاسل: ``"#3ddc97"`` تبقى كما هي.
    ويعيد المصدر كما هو إن تعذّر التحليل — فحصٌ على نصٍّ خامّ
    أضعفُ من فحصٍ لا يعمل.
    """
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return "\n".join(l for l in src.splitlines()
                         if not l.strip().startswith("#"))

    # أوّل عمودٍ يبدأ عنده تعليقٌ في كل سطر
    cut: dict[int, int] = {}
    for tok in toks:
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            cut[row] = min(cut.get(row, col), col)

    out = []
    for i, line in enumerate(src.splitlines(), start=1):
        out.append(line[:cut[i]].rstrip() if i in cut else line)
    return "\n".join(out)


def strip_docstrings(src: str) -> str:
    """يحذف سلاسل التوثيق — للوحدة والأصناف والدوالّ.

    والحذف بالنصّ لا بالموضع: ``ast`` لا يعطي مدى السلسلة في كل
    إصدار. والتكرار مقصود بـ``replace(..., 1)``: توثيقان
    متطابقان في دالّتين يُحذفان واحداً تلو الآخر.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    out = src
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                out = out.replace(doc, "", 1)
    return out


def code_of(path: str | Path) -> str:
    """مصدر ملفٍّ بلا تعليقاتٍ ولا توثيق — جاهزٌ للمطابقة.

    هذه هي الدالّة التي تُستعمل في ٩٠٪ من الحالات.
    """
    return strip_comments(strip_docstrings(
        Path(path).read_text(encoding="utf-8")))


def source_of(path: str | Path) -> str:
    """المصدر الخامّ — حين يكون المقصود فحص **الشرح** نفسه.

    وهذا يقع: «هل التحذير مكتوبٌ في الوثيقة؟» فحصٌ مشروع. فالتمييز
    بالاسم كي لا يُخلط القصدان.
    """
    return Path(path).read_text(encoding="utf-8")


def body_of(path: str | Path, func: str) -> str:
    """جسد دالّةٍ واحدة، بلا توثيقها ولا تعليقاتها.

    ويعيد سلسلةً فارغة إن لم تُوجد — والفحص الذي يطابق فراغاً
    يسقط، وهو الصواب: دالّةٌ غابت يجب أن تُسقط فحصها لا أن
    تُمرّره.
    """
    src = Path(path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == func:
            seg = ast.get_source_segment(src, node) or ""
            doc = ast.get_docstring(node, clean=False)
            if doc:
                seg = seg.replace(doc, "", 1)
            return strip_comments(seg)
    return ""


# ═══════════════════════════════════════════════════════════════
#  ‏CSS و JS
# ═══════════════════════════════════════════════════════════════

def css_rule(src: str, selector: str) -> str:
    """جسد أوّل قاعدةٍ لهذا المحدِّد، بلا تعليقات.

    و‏CSS لا توثيق فيها، لكنّ تعليقاتها تشرح القواعد المقلوبة
    نصّاً — وهو ما أسقط فحص القائمة الجانبية.
    """
    clean = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", clean)
    return m.group(1) if m else ""


def js_code(src: str) -> str:
    """جافاسكربت بلا تعليقات ``//`` ولا ``/* */``."""
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return "\n".join(l for l in no_block.splitlines()
                     if not l.strip().startswith("//"))


# ═══════════════════════════════════════════════════════════════
#  جامع النتائج
# ═══════════════════════════════════════════════════════════════

class Checks:
    """يجمع النتائج ويطبع التقرير — بدل تكراره في كل ملفّ.

    كل فحصٍ هنا يعيد كتابة ``results`` و``check`` وحلقة الطباعة
    ورمز الخروج. وهو ثمانية أسطرٍ متطابقة في مئة ملفّ — وأيّ
    تحسينٍ في الشكل يحتاج مئة تعديل.
    """

    def __init__(self, title: str = "") -> None:
        self.title = title
        self.rows: list[tuple[bool, str, str]] = []

    def __call__(self, name: str, cond, extra: str = "") -> bool:
        ok = bool(cond)
        self.rows.append((ok, name, str(extra)))
        return ok

    # الاسم الصريح لمن يفضّله على النداء المباشر
    check = __call__

    @property
    def failed(self) -> list[str]:
        return [n for ok, n, _ in self.rows if not ok]

    def report(self) -> int:
        """يطبع ويعيد رمز الخروج — ``0`` للنجاح.

        والتفصيل يُطبع للفاشل وحده: سطرُ سببٍ تحت كل ✓ يدفن
        الفشل وسط النجاح.
        """
        if self.title:
            print(self.title)
            print()
        for ok, name, extra in self.rows:
            print(("✓ " if ok else "✗ ") + name
                  + (f"   [{extra}]" if extra and not ok else ""))
        bad = self.failed
        print()
        print(f"{len(self.rows) - len(bad)}/{len(self.rows)} "
              + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
        return 1 if bad else 0
