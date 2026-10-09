# -*- coding: utf-8 -*-
"""من قتل المسح؟ — الذاكرة، والملفّات التي تُحمَّل كاملةً فيها.

    docker exec <web> python tools_doctor_memory.py

═══ لماذا ═══

المسح طبع «… الحفظ (لقطات + نتائج + مراقبات) — قد يطول» ثمّ:

    Killed

و``Killed`` بلا سطر خطأ ليست استثناءً بايثونيّاً — بل إشارة
‎SIGKILL‎ من النواة. وأشيع مُرسِليها **قاتل الذاكرة** (OOM killer):
العملية تجاوزت ما يسمح به الجهاز أو حدُّ الحاوية، فتُقتل بلا إنذار
ولا ``finally`` ولا سجلّ.

وفي مرحلة الحفظ تُقرأ مخازن ‎JSONL‎ إلحاقيّة **كاملةً** في الذاكرة —
قاعدة المعرفة، ولقطات الميزات، والتجارب. وهي تنمو مع كل مسحٍ ولا
تُقصّ. فما كان يمرّ قبل شهر يتجاوز الحدّ اليوم.

هذه الأداة تقيس الثلاثة: حدّ الذاكرة، وأثقل الملفّات، وهل زار
القاتل فعلاً.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"


def _read(p: str) -> str:
    try:
        return Path(p).read_text().strip()
    except OSError:
        return ""


def _mb(n: float) -> str:
    return f"{n / 1e6:,.1f} م.ب" if n < 1e9 else f"{n / 1e9:,.2f} غ.ب"


def main() -> int:
    print(__doc__.strip().splitlines()[0])
    print()

    # ── ١) حدّ الحاوية والذاكرة المتاحة ──
    print("═══ الذاكرة ═══")
    lim = _read("/sys/fs/cgroup/memory.max") or _read(
        "/sys/fs/cgroup/memory/memory.limit_in_bytes")
    cur = _read("/sys/fs/cgroup/memory.current") or _read(
        "/sys/fs/cgroup/memory/memory.usage_in_bytes")
    peak = _read("/sys/fs/cgroup/memory.peak") or _read(
        "/sys/fs/cgroup/memory/memory.max_usage_in_bytes")
    if lim and lim != "max" and int(lim) < 1 << 60:
        print(f"  حدّ الحاوية     {_mb(int(lim))}")
    else:
        print("  حدّ الحاوية     بلا حدّ — الحدّ هو ذاكرة الجهاز كلّها")
    if cur:
        print(f"  المستعمل الآن   {_mb(int(cur))}")
    if peak:
        print(f"  الذروة          {_mb(int(peak))}")
    mem = {}
    for line in _read("/proc/meminfo").splitlines():
        k, _, v = line.partition(":")
        try:
            mem[k] = int(v.split()[0]) * 1024
        except (ValueError, IndexError):
            pass
    if mem:
        print(f"  ذاكرة الجهاز    {_mb(mem.get('MemTotal', 0))} · "
              f"متاح {_mb(mem.get('MemAvailable', 0))} · "
              f"swap {_mb(mem.get('SwapTotal', 0))}")

    # ── ٢) سجلّ القتل ──
    #
    # يُقرأ من داخل الحاوية إن سمح النظام؛ وإلّا يُطلب من المضيف.
    print("\n═══ هل زار قاتل الذاكرة؟ ═══")
    ev = _read("/sys/fs/cgroup/memory.events")
    if ev:
        for line in ev.splitlines():
            if line.startswith(("oom ", "oom_kill ")):
                k, v = line.split()
                mark = "⚠" if int(v) else "✓"
                print(f"  {mark} {k:10s} {v}")
    try:
        out = subprocess.run(["dmesg"], capture_output=True, text=True,
                             timeout=5).stdout
        kills = [l for l in out.splitlines() if "Killed process" in l
                 or "out of memory" in l.lower()]
        for l in kills[-5:]:
            print(f"  {l.strip()[:150]}")
        if not kills and out:
            print("  لا أثر في dmesg")
    except Exception:  # noqa: BLE001
        print("  dmesg غير متاح داخل الحاوية — على المضيف:")
        print("    dmesg -T | grep -iE 'killed process|out of memory' | tail")

    # ── ٣) أثقل الملفّات ──
    #
    # ‏‎JSONL‎ وحدها: هي ما يُقرأ كاملاً. والذاكرة التي تحتاجها
    # أضعاف حجمها على القرص — النصّ، ثمّ قائمة الأسطر، ثمّ كائنات
    # بايثون لكل سجلّ (عشرة أضعاف تقريباً).
    print("\n═══ مخازن JSONL الإلحاقية (الأثقل أوّلاً) ═══")
    rows = []
    for p in DATA.rglob("*.jsonl"):
        try:
            rows.append((p.stat().st_size, p))
        except OSError:
            pass
    rows.sort(reverse=True)
    total = sum(s for s, _ in rows)
    for s, p in rows[:15]:
        print(f"  {_mb(s):>12s}   {p.relative_to(ROOT)}")
    print(f"  {'─' * 12}")
    print(f"  {_mb(total):>12s}   المجموع ({len(rows)} ملفّاً)")

    print("\n═══ الحكم ═══")
    big = [(s, p) for s, p in rows if s > 50e6]
    if big:
        print(f"  {len(big)} ملفّاً فوق ٥٠ م.ب. وكلٌّ منها يحتاج في")
        print("  الذاكرة نحو عشرة أضعاف حجمه حين يُحمَّل كاملاً.")
        for s, p in big[:5]:
            print(f"    {p.name}: ~{_mb(s * 10)} في الذاكرة")
    else:
        print("  لا ملفّ JSONL كبير — فالذاكرة تذهب لغير هذا.")
        print("  أرسل الإخراج كاملاً.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
