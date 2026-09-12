# -*- coding: utf-8 -*-
"""فاحص قوالب Django بلا Django — يُشغَّل في أي بيئة.

بُني بعد خطأ حقيقي: نصّ تحويل حشر كتلة في بداية watches.html قبل
{% extends %}، فصار {% load l10n %} بعد استعمال unlocalize وانهار العرض.
عدّ الوسوم وحده لم يكشفه لأن الكتلتين كانتا متوازنتين — لذا الفحص هنا
يعتمد مكدّساً يتحقق من الترتيب والتداخل، لا من الأعداد.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TPL = ROOT / "web" / "dashboard" / "templates" / "dashboard"

# وسوم لها نهاية، وما يُسمح بظهوره داخلها
PAIRED = {"if": {"elif", "else"}, "for": {"empty"}, "block": set(),
          "with": set(), "comment": set(), "spaceless": set(),
          "autoescape": set(), "verbatim": set(), "filter": set()}

BUILTIN_FILTERS = {
    "add", "addslashes", "capfirst", "center", "cut", "date", "default",
    "default_if_none", "dictsort", "dictsortreversed", "divisibleby",
    "escape", "escapejs", "filesizeformat", "first", "floatformat", "force_escape",
    "get_digit", "iriencode", "join", "json_script", "last", "length",
    "length_is", "linebreaks", "linebreaksbr", "linenumbers", "ljust", "lower",
    "make_list", "phone2numeric", "pluralize", "pprint", "random", "rjust",
    "safe", "safeseq", "slice", "slugify", "stringformat", "striptags", "time",
    "timesince", "timeuntil", "title", "truncatechars", "truncatechars_html",
    "truncatewords", "truncatewords_html", "unordered_list", "upper",
    "urlencode", "urlize", "urlizetrunc", "wordcount", "wordwrap", "yesno",
    "escapeseq",
}
LIB_FILTERS = {"l10n": {"localize", "unlocalize"}, "static": set(),
               "fmt": {"price", "rmult", "num", "ratio", "pct", "money", "span"},
               "humanize": {"intcomma", "naturaltime", "intword",
                            "apnumber", "ordinal", "naturalday"},
               "tz": {"localtime", "utc", "timezone"}, "qs": set()}
# ═══ وسوم مكتبات Django نفسها ═══
#
# هذه لا تُقرأ من مشروعنا لأنّها ليست فيه.
LIB_TAGS = {"static": {"static", "get_static_prefix"}, "l10n": {"localize"},
            "tz": {"localtime", "timezone"}, "humanize": set()}


# ═══ ووسوم المشروع تُقرأ من مصدرها ═══
#
# كانت مكتوبةً هنا بخطّ اليد. ووقع العطب مرّتين: أُضيف ``asset``
# ولم يُسجَّل فرُفضت ثمانية قوالب سليمة، ثمّ أُضيف ``qs_hidden``
# فتكرّر الأمر. ومدقّقٌ يصرخ على الصواب يُصمَّت، فيسكت عن العطب
# الحقيقي حين يقع.
#
# فالقائمة تُشتقّ الآن من الشيفرة: كل ``@register.simple_tag`` أو
# ``@register.filter`` في ``templatetags/`` يُرصد باسمه — أو باسم
# الدالّة إن لم يُسمَّ صراحةً.
def _project_libs(root: Path) -> tuple[dict, dict]:
    import ast as _ast

    tags: dict[str, set] = {}
    filters: dict[str, set] = {}
    for path in sorted(root.glob("web/*/templatetags/*.py")):
        if path.name == "__init__.py":
            continue
        lib = path.stem
        tags.setdefault(lib, set())
        filters.setdefault(lib, set())
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                call = dec if isinstance(dec, _ast.Call) else None
                attr = (call.func if call is not None else dec)
                if not isinstance(attr, _ast.Attribute):
                    continue
                kind = attr.attr
                # الاسم الصريح ``@register.filter(name="x")`` أو
                # ``@register.simple_tag("x")`` يغلب اسم الدالّة
                name = node.name
                if call is not None:
                    for kw in call.keywords:
                        if kw.arg == "name" and isinstance(kw.value, _ast.Constant):
                            name = str(kw.value.value)
                    if call.args and isinstance(call.args[0], _ast.Constant):
                        name = str(call.args[0].value)
                if kind in ("simple_tag", "tag", "inclusion_tag",
                            "simple_block_tag"):
                    tags[lib].add(name)
                elif kind == "filter":
                    filters[lib].add(name)
    return tags, filters


_PROJ_TAGS, _PROJ_FILTERS = _project_libs(ROOT)
for _lib, _names in _PROJ_TAGS.items():
    LIB_TAGS.setdefault(_lib, set()).update(_names)
for _lib, _names in _PROJ_FILTERS.items():
    LIB_FILTERS.setdefault(_lib, set()).update(_names)
BUILTIN_TAGS = {
    "extends", "load", "include", "url", "csrf_token", "cycle", "firstof",
    "lorem", "now", "regroup", "resetcycle", "templatetag", "widthratio",
    "debug", "querystring",
}

TAG_RE = re.compile(r"{%\s*(\w+)([^%]*)%}")
VAR_RE = re.compile(r"{{\s*(.+?)\s*}}")


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    name = path.name
    errs: list[str] = []
    tags = list(TAG_RE.finditer(text))

    # ── 1. extends أولاً ──
    if any(t.group(1) == "extends" for t in tags):
        first = tags[0]
        if first.group(1) != "extends":
            errs.append(f"{name}: أول وسم {{% {first.group(1)} %}} وليس extends "
                        f"(الموضع {first.start()}) — Django يرفض ذلك")
        before = text[: tags[0].start()].strip()
        if before:
            errs.append(f"{name}: نصّ قبل {{% extends %}}: {before[:50]!r}")

    # ── 2. المكتبات المحمّلة ومواضع تحميلها ──
    loaded: set[str] = set()
    load_at: dict[str, int] = {}
    for t in tags:
        if t.group(1) == "load":
            for lib in t.group(2).split():
                if lib == "from":
                    break
                loaded.add(lib)
                load_at.setdefault(lib, t.start())

    # ── 3. الفلاتر: كل فلتر مستعمل إمّا مدمج أو من مكتبة محمّلة قبله ──
    filter_owner = {f: lib for lib, fs in LIB_FILTERS.items() for f in fs}
    for m in list(VAR_RE.finditer(text)) + [
        m for m in tags if m.group(1) in {"if", "elif", "for", "with", "blocktrans"}
    ]:
        body = m.group(1) if m.re is VAR_RE else m.group(2)
        pos = m.start()
        for fname in re.findall(r"\|\s*(\w+)", body):
            if fname in BUILTIN_FILTERS:
                continue
            lib = filter_owner.get(fname)
            if lib is None:
                errs.append(f"{name}: فلتر مجهول |{fname}")
            elif lib not in loaded:
                errs.append(f"{name}: |{fname} يحتاج {{% load {lib} %}}")
            elif load_at[lib] > pos:
                errs.append(f"{name}: |{fname} مستعمل قبل {{% load {lib} %}}")

    # ── 4. الوسوم من مكتبات ──
    tag_owner = {t: lib for lib, ts in LIB_TAGS.items() for t in ts}
    for t in tags:
        n = t.group(1)
        if n in PAIRED or n.startswith("end") or n in BUILTIN_TAGS:
            continue
        if n in {"elif", "else", "empty"}:
            continue
        lib = tag_owner.get(n)
        if lib is None:
            errs.append(f"{name}: وسم مجهول {{% {n} %}}")
        elif lib not in loaded:
            errs.append(f"{name}: {{% {n} %}} يحتاج {{% load {lib} %}}")
        elif load_at[lib] > t.start():
            errs.append(f"{name}: {{% {n} %}} مستعمل قبل {{% load {lib} %}}")

    # ── 5. التداخل بمكدّس، لا بعدّ ──
    stack: list[tuple[str, int]] = []
    for t in tags:
        n = t.group(1)
        line = text.count("\n", 0, t.start()) + 1
        if n in PAIRED:
            stack.append((n, line))
        elif n.startswith("end") and n[3:] in PAIRED:
            want = n[3:]
            if not stack:
                errs.append(f"{name}:{line}: {{% {n} %}} بلا فتح")
            elif stack[-1][0] != want:
                o, ol = stack[-1]
                errs.append(f"{name}:{line}: {{% {n} %}} يغلق {{% {o} %}} "
                            f"المفتوح في السطر {ol} — تداخل متقاطع")
                stack.pop()
            else:
                stack.pop()
        elif n in {"elif", "else", "empty"}:
            if not stack or n not in PAIRED.get(stack[-1][0], set()):
                ctx = stack[-1][0] if stack else "لا شيء"
                errs.append(f"{name}:{line}: {{% {n} %}} داخل {{% {ctx} %}}")
    for n, line in stack:
        errs.append(f"{name}:{line}: {{% {n} %}} لم يُغلق")

    # ── 6. أسماء الكتل فريدة ──
    names = [t.group(2).split()[0] for t in tags
             if t.group(1) == "block" and t.group(2).split()]
    for b in {n for n in names if names.count(n) > 1}:
        errs.append(f"{name}: كتلة مكرّرة {{% block {b} %}}")

    # ── 7. تعليق {# #} لا يتعدّى سطراً ──
    #
    # ═══ عطبٌ وقع وظهر للمستخدم ═══
    #
    # ‏Django يطابق التعليقات بـ ``{#.*?#}`` **بلا** ``re.DOTALL``.
    # فالتعليق الممتدّ على سطرين لا يُطابَق أصلاً، ويُطبَع حرفيّاً في
    # الصفحة — ظهر شرحٌ داخليّ كامل فوق جدول القطاعات في لوحة
    # المستخدم.
    #
    # والخداع أنّ القالب **يُصرَّف بلا خطأ**: لا استثناء ولا تحذير،
    # فقط نصٌّ زائد يظنّه القارئ جزءاً من الواجهة. والبديل الصحيح
    # ``{% comment %}`` وهو الذي يقبل الأسطر.
    for i, ln in enumerate(text.splitlines(), 1):
        if "{#" not in ln:
            continue
        after = ln.split("{#", 1)[1]
        if "#}" not in after:
            errs.append(
                f"{name}:{i}: تعليق {{# #}} ممتدّ على أكثر من سطر — "
                "‏Django لا يطابقه فيُطبَع للمستخدم. استعمل "
                "{% comment %}…{% endcomment %}")

    return errs


def main() -> int:
    all_errs: list[str] = []
    files = sorted(TPL.glob("*.html"))
    for f in files:
        e = check(f)
        print(("✗ " if e else "✓ ") + f.name)
        all_errs += e
    if all_errs:
        print("\n" + "\n".join("  ✗ " + x for x in all_errs))
        return 1
    print(f"\n✓ {len(files)} قوالب سليمة")
    return 0


if __name__ == "__main__":
    sys.exit(main())
