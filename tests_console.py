# -*- coding: utf-8 -*-
"""ترميز المخرَج — الفحص الذي يموت وهو ناجح.

═══ العطب ═══

على ويندوز يختار Python ترميز ``sys.stdout`` من **نوع** المخرَج لا
من محتواه: طرفيةً فـ UTF-8، وأنبوباً فصفحة النظام (cp1252 عربيّاً
كانت أو لاتينية). و``run_checks`` يشغّل كل فحص تحت
``capture_output=True`` — أي أنبوب.

فالسطر الأخير في كل اختبار — ``print("✓ ٤٢ اختباراً")`` — ينهار
بـ ``UnicodeEncodeError``. والانهيار يقع **بعد** أن يمرّ الاختبار
كلّه: النتيجة كانت نجاحاً، والموت وقع في الإبلاغ عنها. فيخرج
بالرمز 1 ويُحسَب فاشلاً.

وهذا أخبث من فشل حقيقي: الرسالة تشير إلى ``encodings/cp1252.py``
لا إلى المنطق المفحوص، والقائمة كلّها حمراء دفعةً واحدة — فيظنّ
القارئ أنّ النظام انهار، والنظام سليم تماماً.

ولم يظهر إلا حين رُقّي المفسّر: الطرفية كانت تخفيه.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# نصّ فيه ما ينهار على cp1252: علامة الصحّ، وعربية، ومدّة الطول
PROBE = '✓ الرموز — ٤٢ اختباراً'
PROBE_CMD = [sys.executable, "-c", f'print({PROBE!r})']
HOSTILE = {**os.environ, "PYTHONIOENCODING": "cp1252"}
GUARDED = {**os.environ, "PYTHONIOENCODING": "utf-8"}


# ── ١) العطب حقيقيّ لا متوهَّم ──
#
# اختبارٌ لا يُثبت أنّ العطب يقع دون العلاج لا يُثبت أنّ العلاج علاج.
bad = subprocess.run(PROBE_CMD, capture_output=True, text=True,
                     env=HOSTILE, errors="replace")
check("١ الترميز المعادي يُسقط الابن فعلاً", bad.returncode != 0,
      f"خرج بـ {bad.returncode}")
check("  وسببه الترميز لا المنطق",
      "UnicodeEncodeError" in (bad.stderr or ""), (bad.stderr or "")[-120:])


# ── ٢) والحارس يمسكه ──
good = subprocess.run(PROBE_CMD, capture_output=True, text=True,
                      env=GUARDED, encoding="utf-8", errors="replace")
check("٢ فرض UTF-8 يُنجي الابن", good.returncode == 0,
      (good.stderr or "")[-120:])
check("  والنصّ يصل سليماً بلا تشويه",
      good.stdout.strip() == PROBE, repr(good.stdout))


# ── ٣) والحارس مكتوب في المشغّل فعلاً ──
#
# لا يكفي أن يعمل هنا: المقصود أنّ ``run_checks`` يفعله.
runner = (ROOT / "run_checks.py").read_text(encoding="utf-8")
code = "\n".join(ln for ln in runner.splitlines()
                 if not ln.lstrip().startswith("#"))
check("٣ المشغّل يفرض ترميز الأبناء", "PYTHONIOENCODING" in code)
check("  ويقرأ مخرجاتهم بـ UTF-8 صراحةً",
      re.search(r'encoding\s*=\s*["\']utf-8["\']', code) is not None)
check("  ولا يتّكل على ترميز النظام", "text=True" in code and "env=" in code)
check("  ويحمي مخرَجه هو أيضاً", "reconfigure" in code)


# ── ٤) وكل من يلتقط مخرَج ابن يفعل الشيء نفسه ──
#
# العلاج في مكان واحد ليس علاجاً: أي ملفّ آخر يشغّل عملية ويلتقط
# مخرجها يحمل العطب ذاته كامناً.
spawners: list[tuple[str, str]] = []
for p in sorted(ROOT.glob("*.py")):
    src = p.read_text(encoding="utf-8", errors="replace")
    if "capture_output=True" in src:
        spawners.append((p.name, src))

check("٤ وُجد من يلتقط مخرَج ابن", len(spawners) >= 2,
      str([n for n, _ in spawners]))
for name, src in spawners:
    check(f"  {name} يفرض الترميز", "PYTHONIOENCODING" in src)


# ── ٥) والمشغّل لا يعلّق إلى الأبد ──
#
# فحصٌ بلا مهلة يوقف الجولة كلّها بلا بيان — وهو ما وقع مع
# الفواحص التي تنتظر Ollama.
check("٥ لكل فحص مهلة", "timeout=TIMEOUT" in code)
check("  والتجاوز يُبلَّغ لا يُبتلع", "TimeoutExpired" in code)


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
