# -*- coding: utf-8 -*-
"""قراءة ‎.env‎ — العطب الذي وقع مرّتين لأنّ العلاج كان في المكان الخطأ.

═══ ما وقع ═══

‏``SAHMK_API_KEY`` في ``.env`` بثمانية وخمسين حرفاً، وأداة التشخيص
تقول «مفتاح سهمك غير مضبوط».

ولم تكن كاذبة: ``os.getenv`` أعاد فراغاً حقّاً، لأن **لا أحد حمّل
الملف**. القارئ كان مكتوباً — داخل ``web/config/settings.py`` وحده،
فلا يعمل إلا حين تُقلَع Django. وأدوات سطر الأوامر لا تُقلعها.

فصار السلوك يتفرّع بحسب **كيف** شُغّل الرمز لا **ماذا** يفعل:
النداء نفسه ينجح من اللوحة ويفشل من الطرفية. وهذا أخبث من عطبٍ
ثابت: تعيد المحاولة فتنجح مرّةً وتفشل مرّة، فتشكّ في المفتاح لا في
المسار.

═══ ولماذا مرّتين ═══

التعليق فوق القارئ القديم يحكي القصّة ذاتها مع توكن تلغرام: «تضع
التوكن في ‎.env‎ ولا يصل أبداً». عولج يومها بإضافة القارئ إلى
إعدادات Django — علاجٌ لمسارٍ واحد لا للسبب.

وثلاثة عشر مفتاحاً كانت في الملف، ولا واحد منها يصل أداةً.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import env as E  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── ١) التحليل يقبل ما يكتبه الناس فعلاً ──
SAMPLE = """
# تعليق
KEY_PLAIN=abc123
KEY_QUOTED="با كلمة"
KEY_SINGLE='مفرد'
export KEY_EXPORT=xyz
KEY_SPACED   =   مسافات
KEY_EQUALS=a=b=c
KEY_EMPTY=
سطر بلا مساواة
"""
p = E.parse_env(SAMPLE)
check("١ القيمة العادية", p.get("KEY_PLAIN") == "abc123", str(p.get("KEY_PLAIN")))
check("  والمزدوجة تُجرَّد", p.get("KEY_QUOTED") == "با كلمة")
check("  والمفردة كذلك", p.get("KEY_SINGLE") == "مفرد")
# ``export KEY=v`` صيغة تُنسَخ من الشروح كثيراً
check("  و export يُتخطّى", p.get("KEY_EXPORT") == "xyz", str(p))
check("  والمسافات تُقصّ", p.get("KEY_SPACED") == "مسافات")
# القيمة قد تحوي ``=`` — التقسيم على أوّل مساواة فقط
check("  والمساواة داخل القيمة تبقى", p.get("KEY_EQUALS") == "a=b=c")
check("  والفراغ قيمةٌ صالحة", p.get("KEY_EMPTY") == "")
check("  والتعليق يُهمَل", "# تعليق" not in p)
check("  والسطر بلا مساواة يُهمَل", len(p) == 7, str(sorted(p)))


# ── ٢) بيئة العمليّة أسبق ──
#
# وإلّا تعذّر تجاوز قيمة لطلبٍ واحد، وصار الملف قدراً لا افتراضاً.
with tempfile.TemporaryDirectory() as tmp:
    f = Path(tmp) / ".env"
    f.write_text("T_EXISTING=من_الملف\nT_NEW=جديد\n", encoding="utf-8")
    os.environ["T_EXISTING"] = "من_البيئة"
    os.environ.pop("T_NEW", None)
    added = E.load_env(f, force=True)
    check("٢ الغائب يُملأ من الملف", os.getenv("T_NEW") == "جديد")
    check("  والموجود لا يُبدَّل", os.getenv("T_EXISTING") == "من_البيئة")
    check("  والعدد المُعاد صحيح", added == 1, str(added))

    # التكرار بلا ضرر: الأدوات قد تناديها أكثر من مرّة
    check("  والنداء الثاني لا يضيف شيئاً", E.load_env(f) == 0)
    for k in ("T_EXISTING", "T_NEW"):
        os.environ.pop(k, None)

    check("  وملف غائب لا يرمي", E.load_env(Path(tmp) / "لا_يوجد") == 0)


# ── ٣) وهذا هو العطب نفسه: أداة مستقلّة ترى المفتاح ──
#
# الاختبار الحقيقي ليس نداء الدالّة — بل تشغيل عمليّة جديدة كما
# تفعل الأداة، والتحقّق أنّ ``import scanner`` وحده يكفي.
with tempfile.TemporaryDirectory() as tmp:
    proj = Path(tmp)
    (proj / "scanner").mkdir()
    for name in ("__init__.py", "env.py"):
        (proj / "scanner" / name).write_text(
            (ROOT / "scanner" / name).read_text(encoding="utf-8"),
            encoding="utf-8")
    (proj / ".env").write_text("ORPHAN_KEY=قيمة_سرّية\n", encoding="utf-8")

    code = ("import sys, os; sys.path.insert(0, r'%s'); "
            "import scanner; print(os.getenv('ORPHAN_KEY', 'فارغ'))" % proj)
    envv = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    envv.pop("ORPHAN_KEY", None)
    r = subprocess.run([sys.executable, "-c", code], capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       env=envv, timeout=60)
    check("٣ استيراد scanner وحده يحمّل .env",
          r.stdout.strip() == "قيمة_سرّية",
          (r.stdout + r.stderr).strip()[:120])

    # وبلا الاستيراد لا يصل شيء — إثباتُ أنّ الاستيراد هو الفاعل
    code2 = "import os; print(os.getenv('ORPHAN_KEY', 'فارغ'))"
    r2 = subprocess.run([sys.executable, "-c", code2], capture_output=True,
                        text=True, encoding="utf-8", errors="replace",
                        env=envv, cwd=proj, timeout=60)
    check("  وبلا استيراده لا يصل", r2.stdout.strip() == "فارغ",
          r2.stdout.strip()[:60])


# ── ٤) التشخيص يفرّق بين ثلاث حالات لا يجمعها ──
#
# «غير مضبوط» جوابٌ ناقص: الملف غائب؟ أم موجود بلا المفتاح؟ أم
# يحويه ولم يُحمَّل؟ علاج كلٍّ مختلف، وجمعها أرسلني أبحث عن مفتاح
# كان في مكانه.
os.environ["T_DESC"] = "س" * 12
check("٤ المضبوط يُوصف بطوله بلا قيمته",
      "12" in E.describe_key("T_DESC") and "س" * 12 not in E.describe_key("T_DESC"),
      E.describe_key("T_DESC"))
os.environ.pop("T_DESC", None)
_missing = E.describe_key("T_GHOST_KEY")
check("  والغائب يُقال إنّه ليس في .env", "غير مضبوط" in _missing, _missing)

st = E.env_status()
check("  والحالة تسرد الأسماء", isinstance(st.get("keys"), list))
check("  ولا تكشف قيمة", "value" not in st and "values" not in st)


# ── ٥) نسخة واحدة لا نسختان ──
#
# النسخة المكرّرة في إعدادات Django هي التي صنعت التفرّع. بقاؤها
# يعني عودة العطب عند أوّل اختلاف بين النسختين.
settings_src = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
check("٥ الإعدادات تستورد القارئ الواحد",
      "from scanner.env import load_env" in settings_src)
check("  ولا تحمل نسختها الخاصّة",
      "def _load_env(path" not in settings_src)
check("  والحزمة تحمّله عند الاستيراد",
      "from . import env" in (ROOT / "scanner" / "__init__.py")
      .read_text(encoding="utf-8"))


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
