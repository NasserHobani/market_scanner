# -*- coding: utf-8 -*-
"""‏tests_helpers نفسه — لأنّ خطأً فيه يُفسد كل فحصٍ يستورده.

═══ لماذا يُفحَص الفاحص ═══

هذه الوحدة تُجرّد التعليقات والتوثيق قبل المطابقة. وخطأٌ فيها لا
يُسقط فحصاً واحداً بل **يقلب مئة**: تجريدٌ نَهِم يحذف كوداً
فيُعلَن غيابُه، وتجريدٌ ناقص يُبقي شرحاً فيُعلَن وجودُه.

والصنف الثاني هو ما وقع أربع مرّات: فحصٌ يجد العبارة في التوثيق
الذي يشرح تجنّبها، فيقول «العطب موجود» والكود سليم.

═══ والفخّ الثالث: السلاسل ═══

قصُّ السطر عند ``#`` يقطع كل لونٍ في CSS: ``"#3ddc97"`` تصير
``"``. فتُشوَّه الشيفرة ويُفحَص شيءٌ آخر — وهو أخطر من الاثنين
لأنّه يُغيّر النصّ لا يحذف منه.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import tests_helpers as H  # noqa: E402

c = H.Checks(__doc__.strip().splitlines()[0])


# ═══════════ ١) التعليقات ═══════════
SRC = '''
x = 1  # تعليقٌ ذيليّ فيه كلمة سرية
# سطرٌ تعليقيّ كامل فيه كلمة سرية
color = "#3ddc97"          # لون
hash_in_str = "a#b#c"
'''
out = H.strip_comments(SRC)
c("١ التعليق الذيليّ يُحذف", "تعليقٌ ذيليّ" not in out)
c("  والسطر التعليقيّ يُحذف", "سطرٌ تعليقيّ" not in out)
c("  والكود يبقى", "x = 1" in out and "color =" in out)
# ═══ الفخّ الذي يقطع الألوان ═══
c("  ولون CSS يبقى سليماً", '"#3ddc97"' in out, out)
c("  والسلسلة ذات ‎#‎ تبقى", '"a#b#c"' in out, out)
# «كلمة سرية» كانت في تعليقين فقط — فغيابها دليلُ اكتمال التجريد
c("  ولا أثر للتعليقات", "كلمة سرية" not in out, out)

# ونصٌّ معطوب لا يرمي — الفحص على نصٍّ خامّ أضعف من فحصٍ لا يعمل
c("  والمعطوب لا يرمي",
  isinstance(H.strip_comments("def ("), str))


# ═══════════ ٢) التوثيق ═══════════
DOC = '''
"""توثيق الوحدة فيه العبارة الممنوعة."""


def f():
    """توثيق الدالّة فيه العبارة الممنوعة."""
    return 1


class K:
    """توثيق الصنف فيه العبارة الممنوعة."""

    def m(self):
        """وتوثيق التابع أيضاً."""
        return 2
'''
d = H.strip_docstrings(DOC)
c("٢ توثيق الوحدة يُحذف", d.count("العبارة الممنوعة") == 0, d)
c("  والكود يبقى", "def f()" in d and "class K" in d and "return 2" in d)
c("  وتوثيق التابع يُحذف", "وتوثيق التابع" not in d)


# ═══════════ ٣) ‎code_of‎ — الاثنان معاً ═══════════
#
# هذا هو المسار الذي تستعمله الفواحص فعلاً. ووقوع الخطأ فيه
# يعني أنّ كل مستوردٍ لها يفحص شيئاً آخر.
tmp = ROOT / "_helpers_probe.py"
tmp.write_text('''"""توثيقٌ فيه iloc[-1] لشرح تجنّبها."""
# وتعليقٌ فيه iloc[-1] أيضاً
value = df.iloc[:-1]        # لا نقرأ iloc[-1]
''', encoding="utf-8")
try:
    code = H.code_of(tmp)
    # ═══ الفحص الحاسم ═══
    #
    # ``iloc[-1]`` مذكورة ثلاث مرّات في الشرح ولا مرّة في الكود.
    # فبقاؤها يعني أنّ الفحص سيُعلن عطباً غير موجود — وهو ما وقع
    # أربع مرّات قبل هذه الوحدة.
    c("٣ الشرح لا يُفحَص", "iloc[-1]" not in code, code)
    c("  والكود يُفحَص", "iloc[:-1]" in code, code)
    c("  والخامّ يُبقي كل شيء", "iloc[-1]" in H.source_of(tmp))
finally:
    tmp.unlink(missing_ok=True)


# ═══════════ ٤) ‎body_of‎ ═══════════
tmp2 = ROOT / "_helpers_probe2.py"
tmp2.write_text('''
def alpha():
    """توثيق ألفا — فيه كلمة بيتا."""
    return "داخل ألفا"


def beta():
    """توثيق بيتا."""
    return "داخل بيتا"
''', encoding="utf-8")
try:
    b = H.body_of(tmp2, "alpha")
    c("٤ يعيد الدالّة المطلوبة", "داخل ألفا" in b, b)
    # ═══ ولا يتسرّب إليها غيرها ═══
    c("  ولا يتسرّب جسد غيرها", "داخل بيتا" not in b, b)
    c("  وتوثيقها محذوف", "توثيق ألفا" not in b, b)
    # ═══ والغائبة تعيد فراغاً ═══
    #
    # الفراغ يُسقط الفحص الذي يطابقه — وهو الصواب: دالّةٌ أُزيلت
    # يجب أن تُسقط فحصها لا أن تُمرّره.
    c("  والغائبة تعيد فراغاً", H.body_of(tmp2, "لا_توجد") == "")
finally:
    tmp2.unlink(missing_ok=True)


# ═══════════ ٥) ‎CSS‎ و ‎JS‎ ═══════════
CSS = """
/* تعليقٌ فيه translateX(100%) لشرح الخطأ */
.a { transform: translateX(-100%); color: #3ddc97; }
.b { transform: none; }
"""
c("٥ قاعدة CSS تُستخرج",
  "translateX(-100%)" in H.css_rule(CSS, ".a"), H.css_rule(CSS, ".a"))
c("  ولا تلتقط تعليقاً", "100%)" not in H.css_rule(CSS, ".a")
  or "translateX(100%)" not in H.css_rule(CSS, ".a"))
c("  ولا قاعدةً أخرى", "none" not in H.css_rule(CSS, ".a"))
c("  والغائبة فراغ", H.css_rule(CSS, ".zz") == "")

JS = """
// تعليقٌ فيه groups[0]
/* وكتلةٌ فيها groups[0] */
var x = d.groups.filter(f);
"""
c("  و‎JS‎ يُجرَّد", "groups[0]" not in H.js_code(JS), H.js_code(JS))
c("  وكوده يبقى", "d.groups.filter" in H.js_code(JS))


# ═══════════ ٦) ‎Checks‎ ═══════════
probe = H.Checks("عنوان")
probe("ناجح", True)
probe("فاشل", False, "السبب")
c("٦ يجمع النتائج", len(probe.rows) == 2)
c("  ويعرف الفاشل", probe.failed == ["فاشل"], str(probe.failed))
c("  ورمز الخروج ١ عند الفشل", probe.report() == 1)
ok_only = H.Checks()
ok_only("ناجح", 1)
c("  و٠ عند النجاح", ok_only.report() == 0)


sys.exit(c.report())
