# -*- coding: utf-8 -*-
"""تطابق المحوّرات المتّجهة مع النسخة المرجعية — بلا Django ولا شبكة.

هذا الاختبار يحرس تسريعاً، والتسريع أخطر من الميزة الجديدة: العطب فيه
لا يظهر كانهيار بل كإشارات **مختلفة بصمت**. إزاحة نافذة بشمعة واحدة
تحرّك كل محوَّر، ومعه الهيكل وفيبوناتشي والقناة والدايفرجنس — فتتغيّر
التوصيات كلها دون أن يفشل شيء.

فالنسخة البطيئة الأصلية محفوظة هنا كمرجع، والاختبار يقارن الاثنتين على
حالات عشوائية وحدّية. لا يكفي أن تعمل السريعة؛ يجب أن تعطي **نفس**
النتيجة بالضبط.

    python tests_pivots.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.indicators.pine import pivot_high, pivot_low

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ─────────────────── النسخة المرجعية (الأصلية، حرفياً)

def ref_pivot_high(src: pd.Series, left: int, right: int) -> pd.Series:
    n = len(src)
    out = pd.Series(np.nan, index=src.index, dtype="float64")
    vals = src.to_numpy(dtype="float64")
    for i in range(left, n - right):
        v = vals[i]
        if np.isnan(v):
            continue
        left_win = vals[i - left:i]
        right_win = vals[i + 1:i + right + 1]
        with np.errstate(invalid="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                lm = np.nanmax(left_win) if left_win.size else np.nan
                rm = np.nanmax(right_win) if right_win.size else np.nan
        if v > lm and v >= rm:
            out.iloc[i] = v
    return out


def ref_pivot_low(src: pd.Series, left: int, right: int) -> pd.Series:
    n = len(src)
    out = pd.Series(np.nan, index=src.index, dtype="float64")
    vals = src.to_numpy(dtype="float64")
    for i in range(left, n - right):
        v = vals[i]
        if np.isnan(v):
            continue
        left_win = vals[i - left:i]
        right_win = vals[i + 1:i + right + 1]
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            lm = np.nanmin(left_win) if left_win.size else np.nan
            rm = np.nanmin(right_win) if right_win.size else np.nan
        if v < lm and v <= rm:
            out.iloc[i] = v
    return out


def same(a: pd.Series, b: pd.Series) -> bool:
    x, y = a.to_numpy(), b.to_numpy()
    if x.shape != y.shape:
        return False
    both_nan = np.isnan(x) & np.isnan(y)
    close = np.isclose(x, y, equal_nan=False, rtol=0, atol=0)
    return bool(np.all(both_nan | close))


# ─────────────────── مقارنة على بيانات عشوائية

rng = np.random.default_rng(20260813)
mismatch_h = mismatch_l = 0
cases = 0
for trial in range(40):
    n = int(rng.integers(30, 400))
    vals = np.cumsum(rng.normal(0, 1, n)) + 100
    # تساوي قيم متجاورة: الحالة التي بُني عليها شرط «>=» المتساهل
    if trial % 3 == 0 and n > 10:
        idx = rng.integers(5, n - 5)
        vals[idx:idx + 2] = vals[idx]
    s = pd.Series(vals, index=pd.RangeIndex(n), dtype="float64")
    for left, right in ((5, 5), (10, 10), (3, 7), (1, 1), (20, 2)):
        if n <= left + right:
            continue
        cases += 1
        if not same(pivot_high(s, left, right), ref_pivot_high(s, left, right)):
            mismatch_h += 1
        if not same(pivot_low(s, left, right), ref_pivot_low(s, left, right)):
            mismatch_l += 1

check(f"القمم تطابق المرجع على {cases} حالة عشوائية", mismatch_h == 0,
      f"{mismatch_h} اختلاف")
check(f"والقيعان كذلك", mismatch_l == 0, f"{mismatch_l} اختلاف")


# ─────────────────── حالات حدّية

def one(vals, left, right, label):
    s = pd.Series(np.asarray(vals, dtype="float64"))
    ok_h = same(pivot_high(s, left, right), ref_pivot_high(s, left, right))
    ok_l = same(pivot_low(s, left, right), ref_pivot_low(s, left, right))
    check(label, ok_h and ok_l)


one([], 5, 5, "سلسلة فارغة")
one([1.0], 5, 5, "قيمة واحدة")
one([1, 2, 3], 5, 5, "أقصر من النافذة")
one([1, 2, 3, 2, 1], 2, 2, "قمة واحدة في المنتصف")
one([5, 5, 5, 5, 5, 5, 5], 2, 2, "قيم متساوية كلها")
one([1, 2, np.nan, 4, 1, 2, 3], 2, 2, "فجوة NaN في المنتصف")
one([np.nan] * 8, 2, 2, "كلها NaN")
one([np.nan, np.nan, 3, 1, 2, np.nan, np.nan], 2, 2, "NaN على الطرفين")
one(list(range(20)), 3, 3, "متزايدة تماماً (لا قمم داخلية)")
one(list(range(20))[::-1], 3, 3, "متناقصة تماماً")
one([1, 3, 3, 1, 5, 5, 1], 1, 1, "قمم متساوية متجاورة")

# النافذة صفر: يجب ألّا تنهار
s = pd.Series([1.0, 5.0, 2.0, 8.0, 3.0])
try:
    pivot_high(s, 0, 2)
    check("نافذة يسار صفر لا تنهار", True)
except Exception as exc:  # noqa: BLE001
    check("نافذة يسار صفر لا تنهار", False, str(exc)[:60])

# النتيجة تحتفظ بالفهرس الأصلي — الهيكل يعتمد عليه
idx = pd.date_range("2026-01-01", periods=50, freq="h", tz="UTC")
s = pd.Series(np.cumsum(rng.normal(0, 1, 50)) + 50, index=idx)
out = pivot_high(s, 5, 5)
check("الفهرس الزمني محفوظ", out.index.equals(idx))
check("والنوع عشري", str(out.dtype) == "float64")


# ─────────────────── التسريع فعليّ لا نظري

n = 1600
big = pd.Series(np.cumsum(rng.normal(0, 1, n)) + 100)
t = time.perf_counter()
for _ in range(3):
    ref_pivot_high(big, 10, 10)
slow = (time.perf_counter() - t) / 3
t = time.perf_counter()
for _ in range(3):
    pivot_high(big, 10, 10)
fast = (time.perf_counter() - t) / 3
speedup = slow / fast if fast > 0 else 0
check(f"أسرع من المرجع بـ {speedup:.0f}×", speedup > 3,
      f"{slow * 1000:.1f} م.ث ← {fast * 1000:.1f} م.ث")


# ─────────────────── بناء البنية لا يستعمل .iloc في حلقة

# الفحص على شجرة الكود لا على النصّ: التعليق الذي يشرح العطب القديم
# يذكره حرفياً، ومطابقة النصّ كانت تعدّه عطباً قائماً. المدقّق الذي
# يخلط الشرح بالكود يُصمَّت أول مرة يصرخ فيها بلا سبب.
import ast

src = (ROOT / "scanner" / "indicators" / "structure.py").read_text("utf-8")
tree = ast.parse(src)
fn = next(n for n in ast.walk(tree)
          if isinstance(n, ast.FunctionDef) and n.name == "build_structure")
loops = [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.While))]
in_loop_attrs = {a.attr for lp in loops for a in ast.walk(lp)
                 if isinstance(a, ast.Attribute)}
check("‏build_structure بلا فهرسة pandas داخل حلقة",
      "iloc" not in in_loop_attrs and "loc" not in in_loop_attrs,
      "الفهرسة بالموضع داخل حلقة كانت 21,117 نداءً لكل تحليل")
check("والقيم تُحوَّل إلى مصفوفات مرّة واحدة",
      sum(1 for a in ast.walk(fn) if isinstance(a, ast.Attribute)
          and a.attr == "to_numpy") >= 3)


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
