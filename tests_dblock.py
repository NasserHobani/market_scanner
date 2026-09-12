# -*- coding: utf-8 -*-
"""قفل قاعدة البيانات — تمييزه عن العطب، وإعداد SQLite للكتّاب المتزامنين.

═══ لماذا ═══

النظام فيه ثلاثة كتّاب: خيوط الخادم، وحلقة الحسم، وحلقة المراقبة.
و SQLite في وضعه الافتراضي يقفل الملف كاملاً عند الكتابة.

كان القفل يُجهض دورة الحسم كلّها — أي أن صفقات بلغت هدفها أو وقفها لا
تُسجَّل، لسبب لا علاقة له بالسوق. وهذا يفسد القياس نفسه، وهو غرض
المشروع.

اختبارات القفل هنا تعمل على SQLite حقيقي بلا Django: نفتح اتصالين،
نقفل الأول، ونتحقّق أن الثاني ينتظر بدل أن يسقط.
"""
from __future__ import annotations

import re
import sqlite3
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── تمييز القفل عن غيره ──
#
# ‏dbretry يستورد Django داخل الدالة فقط، فالتمييز نفسه قابل للاختبار
# بلا تثبيت Django.
sys.modules.setdefault("django", type(sys)("django"))
from dashboard import dbretry  # noqa: E402

check("قفل SQLite يُعرَف",
      dbretry.is_lock_error(Exception("database is locked")))
check("قفل الجدول يُعرَف",
      dbretry.is_lock_error(Exception("database table is locked")))
check("جمود PostgreSQL يُعرَف",
      dbretry.is_lock_error(Exception("deadlock detected")))
check("الحالة تُتجاهل", dbretry.is_lock_error(Exception("DATABASE IS LOCKED")))

# ما ليس قفلاً يجب ألّا يُعاد المحاولة عليه — إعادة محاولة جدول مفقود
# تضيّع الوقت ولا تغيّر النتيجة، وتخفي عطباً يستحقّ الظهور
for other in ("no such table: dashboard_trade",
              "disk I/O error",
              "database disk image is malformed",
              "UNIQUE constraint failed"):
    check(f"ليس قفلاً: {other[:28]}", not dbretry.is_lock_error(Exception(other)))


# ── سلوك إعادة المحاولة ──
class FakeDBError(Exception):
    pass


class _FakeDjangoDB:
    DatabaseError = FakeDBError


sys.modules["django.db"] = _FakeDjangoDB  # type: ignore[assignment]

dbretry.BASE_DELAY = 0.001
dbretry.MAX_DELAY = 0.004

calls = {"n": 0}


def flaky():
    calls["n"] += 1
    if calls["n"] < 3:
        raise FakeDBError("database is locked")
    return "تمّت"


check("ينجح بعد محاولات", dbretry.retry_on_lock(flaky, what="اختبار") == "تمّت")
check("وعدد المحاولات ثلاث", calls["n"] == 3, str(calls["n"]))

# خطأ غير القفل يُرفَع من أول محاولة بلا انتظار
hard = {"n": 0}


def broken():
    hard["n"] += 1
    raise FakeDBError("no such table: dashboard_trade")


try:
    dbretry.retry_on_lock(broken, what="اختبار")
    check("العطب البنيوي يُرفَع", False, "لم يُرفَع")
except FakeDBError:
    check("العطب البنيوي يُرفَع", True)
check("ولا يُعاد المحاولة عليه", hard["n"] == 1, str(hard["n"]))

# القفل المستمرّ: try_on_lock تعيد البديل بدل الرفع
stuck = {"n": 0}


def always_locked():
    stuck["n"] += 1
    raise FakeDBError("database is locked")


check("القفل المستمرّ يعيد البديل",
      dbretry.try_on_lock(always_locked, default="تُخطّيت", what="اختبار")
      == "تُخطّيت")
check("بعد استنفاد المحاولات", stuck["n"] == dbretry.DEFAULT_ATTEMPTS,
      str(stuck["n"]))

# لكن العطب البنيوي يُرفَع حتى عبر try_on_lock — الابتلاع يجعل النظام
# يعمل على بيانات ناقصة وهو يظنّ نفسه سليماً
try:
    dbretry.try_on_lock(broken, default="ابتُلع", what="اختبار")
    check("try_on_lock لا تبتلع العطب", False, "ابتُلع")
except FakeDBError:
    check("try_on_lock لا تبتلع العطب", True)

# الحارس يعمل و Django غائب أو صوريّ.
#
# أوّل نسخة استوردت ``DatabaseError`` استيراداً صارماً، فصار **كل**
# حسم يفشل تحت الاختبار برسالة استيراد لا علاقة لها بالقفل — أي أن
# الحارس نفسه صار هو العطب. أمسكته اختبارات الحسم، وهذا يمنع عودته.
import importlib  # noqa: E402

_saved = sys.modules.get("django.db")
try:
    sys.modules["django.db"] = type(sys)("django.db")   # بلا DatabaseError
    importlib.reload(dbretry)
    dbretry.BASE_DELAY = 0.001
    check("يعمل بلا DatabaseError",
          dbretry.try_on_lock(lambda: "تمّت", what="اختبار") == "تمّت")
    check("ويميّز القفل رغم ذلك",
          dbretry.try_on_lock(
              lambda: (_ for _ in ()).throw(Exception("database is locked")),
              default="تُخطّيت", what="اختبار") == "تُخطّيت")
finally:
    if _saved is not None:
        sys.modules["django.db"] = _saved
    importlib.reload(dbretry)
    dbretry.BASE_DELAY = 0.001
    dbretry.MAX_DELAY = 0.004

# التشويش موجود: خيطان ينتظران المدّة نفسها يصطدمان ثانيةً
src_retry = (ROOT / "web" / "dashboard" / "dbretry.py").read_text(encoding="utf-8")
check("الانتظار مشوَّش", "random.random()" in src_retry)


# ── القفل الحقيقي: هل تنفع المهلة و WAL؟ ──
def _sqlite_contention(journal: str, timeout: float) -> bool:
    """يعيد True إن نجحت الكتابة الثانية أثناء انشغال الأولى."""
    with tempfile.TemporaryDirectory() as tmp:
        path = str(Path(tmp) / "t.sqlite3")
        setup = sqlite3.connect(path)
        setup.execute(f"PRAGMA journal_mode={journal};")
        setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);")
        setup.commit()
        setup.close()

        started = threading.Event()
        release = threading.Event()
        held = {"ok": False}

        def hold():
            # الاتصال يُنشأ **داخل** الخيط: كائن sqlite3 لا يُستعمل عبر
            # الخيوط. إنشاؤه خارجه كان يُسقط الخيط صامتاً فلا يُقفل شيء،
            # فيمرّ اختبار «تنتظر وتنجح» بلا قفل أصلاً — أي يقيس لا شيء.
            conn = sqlite3.connect(path, timeout=timeout, isolation_level=None)
            try:
                conn.execute(f"PRAGMA journal_mode={journal};")
                conn.execute("BEGIN IMMEDIATE;")
                conn.execute("INSERT INTO t (v) VALUES ('أ');")
                held["ok"] = True
                started.set()
                release.wait(2.0)
                conn.execute("COMMIT;")
            finally:
                started.set()
                conn.close()

        th = threading.Thread(target=hold, daemon=True)
        th.start()
        started.wait(2.0)
        if not held["ok"]:
            raise AssertionError("لم يُمسك القفل — المحاكاة لا تقيس شيئاً")

        other = sqlite3.connect(path, timeout=timeout, isolation_level=None)
        other.execute(f"PRAGMA journal_mode={journal};")
        ok = True
        # نحرّر القفل بعد نصف ثانية: المهلة الطويلة يجب أن تصمد
        threading.Timer(0.5, release.set).start()
        try:
            other.execute("BEGIN IMMEDIATE;")
            other.execute("INSERT INTO t (v) VALUES ('ب');")
            other.execute("COMMIT;")
        except sqlite3.OperationalError:
            ok = False
        finally:
            other.close()
            release.set()
            th.join(3.0)
        return ok


check("بمهلة قصيرة تسقط الكتابة الثانية",
      _sqlite_contention("wal", timeout=0.05) is False)
check("وبمهلة كافية تنتظر وتنجح",
      _sqlite_contention("wal", timeout=5.0) is True)


# ── الإعداد نفسه ──
settings_src = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
code = "\n".join(
    ln for ln in settings_src.splitlines() if not ln.strip().startswith("#")
)

check("‏WAL مضبوط", "journal_mode=WAL" in code)
check("والمهلة مضبوطة", re.search(r'"timeout":\s*(\d+)', code) is not None)
timeout_val = int(re.search(r'"timeout":\s*(\d+)', code).group(1))
check("والمهلة كافية للازدحام", timeout_val >= 20, f"{timeout_val}s")

# ‏IMMEDIATE هو الفرق الحاسم: المعاملة المؤجَّلة التي تبدأ بقراءة ثم
# تكتب تسقط بـ SQLITE_BUSY دون أن تحترم المهلة أصلاً
check("والمعاملة IMMEDIATE", '"transaction_mode": "IMMEDIATE"' in code)
check("‏synchronous=NORMAL مع WAL", "synchronous=NORMAL" in code)

# الخيارات الحديثة تحتاج Django 5.1 — تمريرها إلى 5.0 يرفع TypeError
# عند أول اتصال، أي تعطُّل كامل لا تدهور لطيف
check("نسخة Django محروسة", "VERSION >= (5, 1)" in code)
check("وللأقدم بديل عبر الإشارة", "connection_created" in code)


# ── الحلقات لا تسقط بسبب صفّ واحد ──
for fname, label in (("settlement.py", "الحسم"), ("monitor.py", "المراقبة")):
    src = (ROOT / "web" / "dashboard" / fname).read_text(encoding="utf-8")
    body = "\n".join(
        ln for ln in src.splitlines() if not ln.strip().startswith("#")
    )
    check(f"حلقة {label} تستعمل dbretry", "dbretry." in body)

# الترتيب في المراقبة: الحفظ قبل الإرسال.
#
# كان معكوساً، فكل فشل حفظ يعني إعادة إرسال التنبيه نفسه كل دورة —
# سيل تنبيهات عن فرصة واحدة.
mon = (ROOT / "web" / "dashboard" / "monitor.py").read_text(encoding="utf-8")
mon_code = "\n".join(
    ln for ln in mon.splitlines() if not ln.strip().startswith("#")
)
i_save = mon_code.find("تسجيل تحقّق")
i_send = mon_code.find("telegram.send(_alert_text")
check("الحفظ قبل الإرسال", 0 <= i_save < i_send, f"save@{i_save} send@{i_send}")
check("وتعذّر الحفظ يمنع الإرسال", "يُؤجَّل التنبيه" in mon)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
