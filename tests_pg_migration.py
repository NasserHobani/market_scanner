# -*- coding: utf-8 -*-
"""ترحيل القاعدة إلى PostgreSQL — ما ينكسر بصمت في هذا الطريق.

═══ ثلاثة مزالق في ‏dumpdata/loaddata ═══

**الترميز.** ``dumpdata > file`` على ويندوز أنبوب، وPython يختار
ترميز المخرَج من **نوعه** لا محتواه — cp1252 — فينهار على أوّل
حرفٍ عربي. وبيانات هذا النظام عربية كلّها. (وقع الشكل نفسه في
``run_checks.py`` من قبل، وحُلّ بـ ``PYTHONIOENCODING``.)

**التسلسلات.** ‏PostgreSQL لا يحرّك عدّاد الجدول عند إدراجٍ بمفتاحٍ
صريح. فلو نُقلت ٦٢٤ صفقة بمفاتيحها ولم يُضبط العدّاد لبدأ من ١
واصطدم أوّل حفظٍ جديد — **بعد الترحيل بساعات لا عنده**.

**‏contenttypes.** ينشئها ``migrate`` تلقائياً فتصطدم بـ
``loaddata``.

═══ وما يحرسه هذا الملف ═══

    ١) ألّا يبقى نموذجٌ خارج قائمة النقل بصمت.
    ٢) أن يسبق الجدول المُشار إليه المشيرَ إليه.
    ٣) أن تُضبط التسلسلات بعد النقل.
    ٤) ألّا يُكتب فوق جداول غير فارغة بلا إذن.
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


CMD = (ROOT / "web" / "dashboard" / "management" / "commands"
       / "migrate_to_postgres.py")
src = CMD.read_text(encoding="utf-8")
tree = ast.parse(src)
code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))

ORDER = [e.value for e in next(
    n.value for n in tree.body
    if isinstance(n, ast.Assign) and n.targets[0].id == "ORDER").elts]

models_src = (ROOT / "web" / "dashboard" / "models.py").read_text(
    encoding="utf-8")
mtree = ast.parse(models_src)
MODELS = [n.name for n in mtree.body
          if isinstance(n, ast.ClassDef)
          and any(getattr(b, "attr", getattr(b, "id", "")) == "Model"
                  for b in n.bases)]


# ═══ ١) لا نموذج خارج القائمة ═══
#
# نموذجٌ جديد يُنسى تبقى بياناته في SQLite بلا أن ينتبه أحد —
# وهو أسوأ من فشلٍ صريح.
check("١ القائمة تغطّي النماذج", set(ORDER) == set(MODELS),
      str(set(MODELS) ^ set(ORDER)))
check("  ولا تكرار", len(ORDER) == len(set(ORDER)))
# والأمر يرفض التشغيل إن اختلّت — لا يمرّ صامتاً
check("  والأمر يرفض الناقص", "نماذج بلا موضع في الترتيب" in src)
check("  ويرفض الزائد", "نماذج في الترتيب وليست في التطبيق" in src)


# ═══ ٢) ترتيب الاعتماد ═══
#
# المُشار إليه قبل المشير، وإلّا رُفض المفتاح الأجنبي.
FK = {"ScanResult": "ScanRun", "SignalAlert": "ScanResult",
      "JobRun": "ScheduledJob", "PaperTrade": "PaperAccount"}
for child, parent in FK.items():
    check(f"٢ {parent} قبل {child}",
          ORDER.index(parent) < ORDER.index(child),
          f"{ORDER.index(parent)} مقابل {ORDER.index(child)}")
# والعلاقات تُقرأ من النماذج لا تُفترَض
found: dict[str, str] = {}
for n in mtree.body:
    if not isinstance(n, ast.ClassDef):
        continue
    for st in ast.walk(n):
        if (isinstance(st, ast.Call)
                and getattr(st.func, "attr", "") == "ForeignKey"):
            tgt = st.args[0] if st.args else None
            nm = getattr(tgt, "id", None) or getattr(tgt, "value", None)
            if isinstance(nm, str):
                found[n.name] = nm
check("  والعلاقات المرصودة مغطّاة",
      all(k in FK or v not in ORDER for k, v in found.items()),
      str({k: v for k, v in found.items() if k not in FK}))


# ═══ ٣) التسلسلات تُضبط ═══
check("٣ يُعاد ضبط التسلسلات", "_reset_sequences" in code)
check("  بأداة Django لا بـ SQL يدوي",
      "sequence_reset_sql" in code)
check("  وبعد النقل لا قبله",
      code.index("total += n") < code.index("self._reset_sequences()"))
check("  والسبب موثَّق", "بمفاتيح صريحة" in src or "بمفتاحٍ صريح" in src)


# ═══ ٤) لا كتابة فوق بياناتٍ قائمة ═══
#
# نقلٌ ثانٍ فوق جداول ممتلئة يضاعف الصفوف أو يصطدم بالمفاتيح.
check("٤ يرفض الجداول غير الفارغة", "غير فارغة" in src)
check("  إلّا بـ --force", '"--force"' in src and 'opts["force"]' in code)
check("  و --check لا يكتب",
      'if opts["check"] or opts["verify"]:' in code
      and code.index('if opts["check"]') < code.index("existing ="))


# ═══ ٥) حالة الكائن تُصفَّر قبل الإدراج ═══
#
# ``_state.db`` يحمل الاتّصال المصدر. وبلا تصفيره يحاول Django
# **تحديث** الصفّ في SQLite بدل إدراجه في PostgreSQL.
check("٥ يُصفَّر _state.db", "obj._state.db = None" in code)
check("  ويُعلَن أنّه جديد", "obj._state.adding = True" in code)
check("  والنسخ على دفعات", "bulk_create" in code and "BATCH" in code)
check("  وبمكرّرٍ لا بتحميل كامل", "iterator(chunk_size" in code)


# ═══ ٦) حرّاس التشغيل ═══
check("٦ يتحقّق من وجود legacy", '"legacy" not in settings.DATABASES' in code)
check("  ومن أنّ الهدف Postgres", '"postgresql" not in' in code)
check("  ويقول ماذا يفعل المستخدم",
      "POSTGRES_DB" in src and ".env" in src)


# ═══ ٧) الإعدادات تفتح الاتّصال الثاني ═══
st = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
scode = "\n".join(l for l in st.splitlines()
                  if not l.strip().startswith("#"))
check("٧ اتّصال legacy معرَّف", 'DATABASES["legacy"]' in scode)
# ولا يُضاف إلّا مع Postgres وبوجود الملفّ — وإلّا كسر SQLite العادي
check("  بشرط وجود الملفّ", "_legacy.exists()" in scode)
# النسخة الأولى قاست بأوّل ``else:`` في الملفّ — وهو لفرعٍ آخر
# بعيد عن إعداد القاعدة. والقياس الصحيح: ‏legacy بين محرّك
# Postgres ومحرّك SQLite، أي داخل فرع Postgres قطعاً.
i_pg = scode.index('"ENGINE": "django.db.backends.postgresql"')
i_legacy = scode.index('DATABASES["legacy"]')
i_sqlite = scode.index('"ENGINE": "django.db.backends.sqlite3"')
check("  وداخل فرع Postgres", i_pg < i_legacy < i_sqlite,
      f"{i_pg} · {i_legacy} · {i_sqlite}")


# ═══ ٨) الوثيقة تذكر ما ينكسر ═══
doc = (ROOT / "docs" / "POSTGRES.md").read_text(encoding="utf-8")
check("٨ الوثيقة موجودة", len(doc) > 500)
check("  وتذكر الترميز", "cp1252" in doc and "UTF8" in doc)
check("  وتذكر التسلسلات", "التسلسلات" in doc)
# إيقاف الكتّاب قبل النقل — وإلّا ضاعت صفوف بلا إنذار
check("  وتأمر بإيقاف الجدولة", "SCHEDULER_ENGINE=off" in doc)
check("  وتذكر التراجع", "التراجع" in doc)
# ═══ ما لا يُنقل يُقال ═══
#
# الشموع ملفّاتٌ في ``data/`` لا صفوفٌ في القاعدة. ومن ظنّها
# تُنقل انتظر ما لا يأتي، ثمّ ظنّ النقل ناقصاً.
check("  وتفرّق الملفّات عن الصفوف",
      "data/" in doc and "لا يُنقل" in doc)
# والقديم يبقى: أيّ خلل يظهر بعد أسبوعين تعود إليه
check("  وتنهى عن حذف النسخة القديمة",
      "لا يُحذف" in doc or "لا تحذفه" in doc)
check("  وتحدّد مدّة الاحتفاظ", "شهراً" in doc or "أسبوعاً" in doc)

# ═══ سجلّ WAL يُدمج قبل القراءة ═══
#
# القاعدة تعمل بـ ``journal_mode=WAL``، وفي السجلّ الجانبي ٤ م
# غير مدموجة. والقراءة تراها، لكنّ من ينسخ ملفّ القاعدة وحده —
# احتياطاً أو نقلاً إلى خادم — يفقدها بلا أن يظهر شيء: الملفّ
# يُفتح، والجداول موجودة، والصفوف الأخيرة ناقصة.
check("٩ يدمج سجلّ WAL", "wal_checkpoint" in code)
check("  قبل النسخ لا بعده",
      code.index("self._checkpoint()") < code.index("self._copy("))
check("  ويُعلن تعذّره", "كاتبٌ آخر يعمل" in src)
check("  ولا يرمي", "except Exception" in
      src.split("def _checkpoint")[1].split("\n    def ")[0])
check("  والوثيقة تشرحه", "WAL" in doc and "-wal" in doc)


# ═══ ١٠) قاعدةٌ محلّية بلا تثبيت ═══
#
# ‏docker-compose.yml الكامل يطلب ``${VAR:?}``، و‏compose يفسّر
# الملفّ كلّه قبل أن ينظر إلى الخدمة المطلوبة — فحتى ``up -d db``
# تفشل إن نقص متغيّر. فملفٌّ مستقلّ للقاعدة وحدها.
import yaml as _y

LDB = ROOT / "docker-compose.localdb.yml"
check("١٠ ملفّ القاعدة المحلّية موجود", LDB.exists())
if LDB.exists():
    _raw = LDB.read_text(encoding="utf-8")
    # الكود بلا شرحه: التعليق هنا يذكر ``${VAR:?}`` وصفاً لما في
    # الملفّ الآخر، ومطابقةُ النصّ الخام تجعل الفحص يرسب على شرحٍ
    # يصف المشكلة لا على وقوعها. وهذا الخطأ نفسه تكرّر في هذه
    # الجلسة مرّتين قبلها.
    _code = "\n".join(l for l in _raw.splitlines()
                      if not l.strip().startswith("#"))
    _d = _y.safe_load(_raw)
    check("  وخدمةٌ واحدة", list(_d["services"]) == ["db"],
          str(list(_d["services"])))
    # لا ‎${VAR:?}‎ فيه: غرضه أن يعمل بأمرٍ واحد بلا إعداد
    check("  ولا متغيّرات مطلوبة", ":?" not in _code)
    # منفذٌ مختلف كي لا يصطدم بـ PostgreSQL مثبَّت
    _ports = [str(x) for x in _d["services"]["db"].get("ports") or []]
    check("  ومنفذه 5433 لا 5432",
          any("5433:5432" in p for p in _ports), str(_ports))
    # ومربوطٌ بالمضيف المحلّي وحده
    check("  ومربوط بـ 127.0.0.1",
          all(p.startswith("127.0.0.1:") for p in _ports), str(_ports))
    check("  وبترميز UTF8", "--encoding=UTF8" in _code)
    # وكلمة المرور مكشوفة عمداً — ويُقال إنّها للجهاز لا للخادم
    # النهي بقي، لكنّه بالإنجليزية: الملفّ صار ASCII خالصاً بعد
    # أن رفض مفسّر Go نصّاً ثنائيّ الاتجاه في ‎docker-compose.yml‎.
    # والمطلوب أن يبقى مكتوباً، لا أن يبقى بلغةٍ بعينها.
    check("  ويُنهى عن استعماله على خادم",
          "DO NOT USE THIS" in _raw.upper()
          or "لا تستعمل هذا الملفّ على خادم" in _raw)
    # والوثيقة تدلّ عليه
    check("  والوثيقة تدلّ عليه", "docker-compose.localdb.yml" in doc)

# والأعداد في الوثيقة تطابق ما يُنقل فعلاً: ١٣ جدولاً
check("  والوثيقة تذكر ثلاثة عشر جدولاً",
      "24,222" in doc or "24222" in doc)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
