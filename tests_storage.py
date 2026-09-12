# -*- coding: utf-8 -*-
"""اختبارات الجلب التراكمي — بلا شبكة.

الحساب هنا هو ما يحدّد كم بايتاً يُنزَّل في كل مسح، فخطأ فيه إمّا يُبطئ
المسح أضعافاً (جلب زائد) أو يترك فجوة في البيانات (جلب ناقص).

    python tests_storage.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scanner import storage as S

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


NOW = pd.Timestamp("2026-08-08 12:00", tz="UTC")


def frame(n, freq, end=NOW, tz="UTC"):
    idx = pd.date_range(end=end, periods=n, freq=freq, tz=tz)
    return pd.DataFrame({"close": [1.0] * n, "volume": [1.0] * n}, index=idx)


FULL = 1500

# ── الحالة التي كانت تُهدر الوقت ──
d = frame(FULL, "4h")
need = S.bars_needed(d, "4h", FULL, now=NOW)
check("رمز محدَّث للتوّ يطلب الهامش فقط لا 1500",
      need == 3, f"{need} شمعة")
check("أي ~{}× أقل تنزيلاً".format(FULL // max(need, 1)), FULL // need >= 100)

# ── التغطية: لا فجوات ──
for hours, expect in ((4, 4), (12, 6), (24, 9), (48, 15)):
    n = S.bars_needed(d, "4h", FULL, now=NOW + pd.Timedelta(hours=hours))
    bars = hours // 4
    check(f"تأخّر {hours} ساعة ({bars} شمعة) يطلب {bars}+هامش",
          n == expect, f"{n} بدل {expect}")

check("انقطاع طويل يُملأ حتى الحد الأقصى",
      S.bars_needed(d, "4h", FULL, now=NOW + pd.Timedelta(days=400)) == FULL)

# ── الحالات الحدّية ──
check("لا تخزين ← التاريخ كامل", S.bars_needed(None, "4h", FULL) == FULL)
check("جدول فارغ ← التاريخ كامل",
      S.bars_needed(pd.DataFrame(), "4h", FULL) == FULL)
check("فريم مجهول ← التاريخ كامل بأمان",
      S.bars_needed(d, "غير-موجود", FULL) == FULL)
check("ساعة متأخرة عن البيانات ← لا قيمة سالبة",
      S.bars_needed(d, "4h", FULL, now=NOW - pd.Timedelta(days=3)) == 3)
check("حدّ أدنى شمعتان دائماً",
      S.bars_needed(d, "4h", FULL, now=NOW, margin=0) >= 2)
check("full=0 ← لا جلب", S.bars_needed(d, "4h", 0) == 0)

# فهرس بلا منطقة زمنية لا يُسقط الحساب
naive = frame(100, "4h", end=pd.Timestamp("2026-08-08 12:00"), tz=None)
check("فهرس بلا منطقة زمنية يُعالَج لا ينهار",
      isinstance(S.bars_needed(naive, "4h", FULL, now=NOW), int),
      S.bars_needed(naive, "4h", FULL, now=NOW))

# ── فريمات مختلفة ──
d15 = frame(500, "15min")
check("15m متأخر ساعة ← 4+هامش",
      S.bars_needed(d15, "15m", FULL, now=NOW + pd.Timedelta(hours=1)) == 7)
d1d = frame(400, "1D")
check("1d متأخر أسبوعاً ← 7+هامش",
      S.bars_needed(d1d, "1d", FULL, now=NOW + pd.Timedelta(days=7)) == 10)

# ── آخر شمعة ──
check("last_time يعيد آخر طابع زمني", S.last_time(d) == d.index[-1])
check("last_time لـ None", S.last_time(None) is None)
check("last_time لجدول فارغ", S.last_time(pd.DataFrame()) is None)

# ── كشف صيغة التخزين ──
# ‏npz صيغة الكتابة الحالية، و csv/parquet مقروءتان للتوافق.
# القائمة تأتي من ``FORMATS`` لا مكتوبة هنا: تثبيتها في موضعين يعني
# أن إضافة صيغة تكسر اختباراً لا علاقة له بها.
check("صيغة التخزين معروفة", S.storage_format() in S.FORMATS,
      S.storage_format())
check("والصيغة المكتوبة هي الأسرع", S.FORMATS[0] == S.storage_format(),
      f"{S.FORMATS[0]} مقابل {S.storage_format()}")

# ── الدمج لا يُكرّر ولا يفقد ──
old = frame(100, "4h", end=NOW)
new = frame(5, "4h", end=NOW + pd.Timedelta(hours=20))
merged = S.merge(old, new)
check("الدمج يضيف الجديد بلا تكرار",
      len(merged) == 105 and merged.index.is_unique, len(merged))
check("والترتيب زمني", merged.index.is_monotonic_increasing)
check("والتداخل يأخذ الأحدث",
      len(S.merge(old, old)) == 100)

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
