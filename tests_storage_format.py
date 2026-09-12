# -*- coding: utf-8 -*-
"""صيغة الشموع الثنائية وذاكرة الإطارات.

═══ لماذا تغيّرت الصيغة ═══

قياس على ملفّات المشروع (1578 شمعة، 96KB):

    CSV → DataFrame      16.21 ms
    ثنائي → DataFrame     0.63 ms      أسرع ×25.6
    الحجم                71KB مقابل 96KB

ولـ500 رمز: 8.1 ثانية تصير 0.3. وهذا سرّ سرعة المنصّات الكبيرة رغم
تاريخها الضخم — تخزين عمودي بأنواع محدَّدة، لا نصّ يُعاد تحليله.

═══ الخطران اللذان تحرسهما هذه الاختبارات ═══

  ١. **تغيير قيمة بصمت.** صيغة أسرع تعطي رقماً مختلفاً أسوأ من صيغة
     بطيئة. فالمقارنة هنا **بلا تسامح**: ``array_equal`` لا
     ``allclose``.

     وقد كدتُ أقع فيه: وضعتُ الطابع الزمني داخل مصفوفة ``float64``
     مع الأسعار، ونجح الاختبار — بالصدفة. الطابع بالنانوثانية 1.79e18
     بينما ``float64`` يضمن الدقّة حتى 9.0e15، ومرّ لأن طوابع الشموع
     مضاعفات الثانية فتترك بتّات صفرية تتّسع بالكاد. وأي مصدر بدقّة
     الميلي كان سيُزيح الوقت بلا أثر.

  ٢. **ذاكرة تُعيد شموعاً قديمة.** أسوأ من بطء: قرارٌ يُبنى على سعر
     لم يعد قائماً. فالإبطال بزمن التعديل لا بمهلة زمنية.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scanner import storage  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def make_frame(n: int = 200, *, tz: str | None = "UTC",
               odd_seconds: bool = False) -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01 00:00:07" if odd_seconds
                         else "2026-01-01 00:00:00", tz=tz)
    idx = pd.date_range(start, periods=n, freq="4h")
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "open": base,
        "high": base + rng.random(n),
        "low": base - rng.random(n),
        "close": base + rng.normal(0, 0.3, n),
        "volume": rng.random(n) * 1e6,
    }, index=idx)


def exact(a: pd.DataFrame, b: pd.DataFrame) -> str:
    """مقارنة بلا تسامح. تعيد سبب الاختلاف أو نصّاً فارغاً."""
    if b is None:
        return "لا إطار"
    if len(a) != len(b):
        return f"الصفوف {len(a)} ≠ {len(b)}"
    ia, ib = pd.DatetimeIndex(a.index), pd.DatetimeIndex(b.index)
    ia = ia.tz_localize("UTC") if ia.tz is None else ia.tz_convert("UTC")
    ib = ib.tz_localize("UTC") if ib.tz is None else ib.tz_convert("UTC")
    if not np.array_equal(ia.view("int64"), ib.view("int64")):
        return "الطوابع"
    for c in storage.OHLCV:
        if c not in a.columns:
            continue
        if not np.array_equal(a[c].to_numpy(np.float64),
                              b[c].to_numpy(np.float64), equal_nan=True):
            return f"العمود {c}"
    return ""


tmp = Path(tempfile.mkdtemp())
_orig_dir = storage.DATA_DIR
storage.DATA_DIR = tmp


# ── ١) دورة كتابة/قراءة بلا فقدان ──
storage.clear_frame_cache()
df = make_frame()
storage.save("crypto", "TESTUSDT", "4h", df)
back = storage.load("crypto", "TESTUSDT", "4h")
check("١ الدورة بلا فقدان", exact(df, back) == "", exact(df, back))
check("  والصيغة ثنائية", storage.storage_format() == "npz")
check("  والملف موجود",
      storage._path("crypto", "TESTUSDT", "4h", "npz").exists())

# الطوابع بثوانٍ فردية — الحالة التي كانت ستكسر float64
storage.clear_frame_cache()
odd = make_frame(odd_seconds=True)
storage.save("crypto", "ODDUSDT", "4h", odd)
storage.clear_frame_cache()
check("  وثوانٍ فردية تُحفظ بدقّة",
      exact(odd, storage.load("crypto", "ODDUSDT", "4h")) == "",
      exact(odd, storage.load("crypto", "ODDUSDT", "4h")))

# الحدّ الفاصل: طابع بدقّة الميلّي — هنا كان الفخّ
storage.clear_frame_cache()
milli = make_frame(50)
milli.index = pd.DatetimeIndex(
    [pd.Timestamp("2026-03-01", tz="UTC") + pd.Timedelta(milliseconds=i * 1237)
     for i in range(50)])
storage.save("crypto", "MSUSDT", "4h", milli)
storage.clear_frame_cache()
check("  ودقّة الميلّي كذلك",
      exact(milli, storage.load("crypto", "MSUSDT", "4h")) == "",
      exact(milli, storage.load("crypto", "MSUSDT", "4h")))


# ── الوحدة الزمنية: العطب الذي فاتني ──
#
# ═══ ماذا وقع ═══
#
# النسخة الأولى كتبت ``idx.view("int64")`` وقرأت
# ``ts.view("datetime64[ns]")`` — أي افترضت النانوثانية.
#
# و‏pandas 2.x لا تفرضها: الفهرس قد يكون ``[us]`` أو ``[ms]`` أو
# ``[s]`` حسب مصدره. فملفّ NVDA على 4h كُتب بالميكروثانية وقُرئ
# نانوثانيةً، فصار تاريخه **1970-01-21** بدل 2025 — بلا استثناء ولا
# تحذير.
#
# ولم تمسكه اختباراتي لأنها كلّها تبني الفهرس بـ``date_range`` الذي
# يعطي نانوثانية. فاختبارٌ يستعمل مصدراً واحداً لا يكشف اختلاف
# المصادر — وهو درسٌ أوسع من هذا العطب.
for _unit in ("s", "ms", "us", "ns"):
    storage.clear_frame_cache()
    _idx = pd.date_range("2026-05-01", periods=40, freq="4h", tz="UTC")
    try:
        _idx = _idx.as_unit(_unit)
    except AttributeError:
        pass
    _df = make_frame(40)
    _df.index = _idx
    storage.save("crypto", f"UNIT{_unit.upper()}", "4h", _df)
    storage.clear_frame_cache()
    _back = storage.load("crypto", f"UNIT{_unit.upper()}", "4h")
    check(f"  وحدة {_unit} تُحفظ وتُقرأ صحيحة",
          _back is not None and str(_back.index[0]) == str(_idx[0]),
          f"{_idx[0]} → {_back.index[0] if _back is not None else None}")

# وملفّ بلا وحدة معلَنة (كُتب بالنسخة المعطوبة) يُرفض ولا يُخمَّن
storage.clear_frame_cache()
_legacy_npz = storage._path("crypto", "NOUNIT", "4h", "npz")
_legacy_npz.parent.mkdir(parents=True, exist_ok=True)
np.savez(_legacy_npz, ts=np.array([1752523200000000], dtype=np.int64),
         ohlcv=np.zeros((1, 5)))
check("  والملفّ بلا وحدة يُرفض",
      storage.load("crypto", "NOUNIT", "4h") is None)

# ويسقط إلى CSV إن وُجد — لا يُخفي بيانات سليمة
storage.clear_frame_cache()
_csv_twin = storage._path("crypto", "NOUNIT", "4h", "csv")
make_frame(12).to_csv(_csv_twin)
_fallback = storage.load("crypto", "NOUNIT", "4h")
check("  ويسقط إلى النصّ السليم",
      _fallback is not None and len(_fallback) == 12)


# ── ٢) أسرع فعلاً ──
storage.clear_frame_cache()
big = make_frame(1500)
storage.save("crypto", "BIGUSDT", "4h", big)
csv_path = storage._path("crypto", "BIGCSV", "4h", "csv")
csv_path.parent.mkdir(parents=True, exist_ok=True)
big.to_csv(csv_path)

t0 = time.time()
for _ in range(20):
    storage.clear_frame_cache()
    storage.load("crypto", "BIGUSDT", "4h")
npz_ms = (time.time() - t0) * 1000 / 20
t0 = time.time()
for _ in range(20):
    storage.clear_frame_cache()
    storage.load("crypto", "BIGCSV", "4h")
csv_ms = (time.time() - t0) * 1000 / 20
check("٢ الثنائي أسرع من النصّ", npz_ms < csv_ms,
      f"{npz_ms:.2f}ms مقابل {csv_ms:.2f}ms")
check("  وبفارق معتبر", csv_ms / max(npz_ms, 1e-9) > 3.0,
      f"×{csv_ms / max(npz_ms, 1e-9):.1f}")


# ── ٣) التوافق للخلف ──
#
# آلاف ملفّات CSV عند المستخدم. كسرُها يعني فقدان تاريخ لا يُشترى.
storage.clear_frame_cache()
legacy = storage._path("crypto", "LEGACY", "1h", "csv")
legacy.parent.mkdir(parents=True, exist_ok=True)
old_df = make_frame(80)
old_df.to_csv(legacy)
loaded = storage.load("crypto", "LEGACY", "1h")
check("٣ ملفّ CSV قديم يُقرأ", loaded is not None and len(loaded) == 80)

# ═══ اكتشاف جانبي: CSV نفسه ليس بلا فقدان ═══
#
# دورة ``to_csv`` ثمّ ``read_csv`` غيّرت **آخر بتّ** في 14 قيمة من
# 200 (أكبر فرق 1.4e-14). فالنصّ يفقد دقّة حيث لا يفقدها الثنائي.
#
# والفرق مهمل على الأسعار، لكنه يقلب معنى التغيير: الانتقال إلى
# الثنائي ليس مقايضةً بين سرعة ودقّة — بل مكسبٌ في الاثنين.
#
# فالمقارنة هنا بتسامح آخر بتّ، وفي الثنائي بلا تسامح إطلاقاً.
diff = np.abs(old_df["open"].to_numpy(np.float64)
              - loaded["open"].to_numpy(np.float64)).max()
check("  بقيمه ضمن دقّة النصّ", diff < 1e-9, f"{diff:.2e}")
check("  والثنائي بلا فقدان أصلاً",
      exact(df, storage.load("crypto", "TESTUSDT", "4h")) == "")

# والحفظ يرحّله ويزيل القديم — وإلّا صار مصدرا حقيقة لبيانات واحدة
storage.save("crypto", "LEGACY", "1h", old_df)
check("  والحفظ يرحّله",
      storage._path("crypto", "LEGACY", "1h", "npz").exists())
check("  ويزيل النسخة القديمة", not legacy.exists())


# ── ٤) قراءة الطابع الأخير ──
storage.clear_frame_cache()
check("٤ الطابع الأخير من الثنائي",
      str(storage.last_time_on_disk("crypto", "BIGUSDT", "4h"))
      == str(pd.DatetimeIndex(big.index).tz_convert("UTC")[-1]),
      str(storage.last_time_on_disk("crypto", "BIGUSDT", "4h")))
check("  والمفقود يعطي None",
      storage.last_time_on_disk("crypto", "__غائب__", "4h") is None)

# وأسرع من تحميل الإطار كاملاً
storage.clear_frame_cache()
t0 = time.time()
for _ in range(30):
    storage.clear_frame_cache()
    storage.last_time_on_disk("crypto", "BIGUSDT", "4h")
tail_ms = (time.time() - t0) * 1000 / 30
check("  وأسرع من التحميل الكامل", tail_ms < npz_ms,
      f"{tail_ms:.3f}ms مقابل {npz_ms:.2f}ms")


# ── ٥) ذاكرة الإطارات ──
storage.clear_frame_cache()
t0 = time.time(); storage.load("crypto", "BIGUSDT", "4h"); cold = time.time() - t0
t0 = time.time(); storage.load("crypto", "BIGUSDT", "4h"); warm = time.time() - t0
check("٥ الذاكرة تُصيب", warm < cold, f"{warm*1000:.3f}ms مقابل {cold*1000:.2f}ms")

# ── الخطر: هل تُعيد شموعاً قديمة بعد تغيّر الملف؟ ──
#
# هذا أهمّ اختبار في الملف. ذاكرة تُعيد سعراً قديماً تُنتج قراراً
# على سوق لم يعد قائماً — وهو أسوأ بكثير من البطء الذي جاءت لتحلّه.
first = storage.load("crypto", "BIGUSDT", "4h")
grown = pd.concat([big, make_frame(5).set_index(
    pd.date_range(pd.DatetimeIndex(big.index)[-1] + pd.Timedelta("4h"),
                  periods=5, freq="4h"))])
time.sleep(0.01)
storage.save("crypto", "BIGUSDT", "4h", grown)
after = storage.load("crypto", "BIGUSDT", "4h")
check("  ولا تُعيد شموعاً قديمة", len(after) == len(grown),
      f"{len(after)} بدل {len(grown)}")
check("  والطابع الأخير تحدَّث",
      str(pd.DatetimeIndex(after.index)[-1])
      != str(pd.DatetimeIndex(first.index)[-1]))

# والإبطال بزمن التعديل لا بمهلة: تعديل خارجي يُرصد أيضاً
storage.clear_frame_cache()
storage.load("crypto", "BIGUSDT", "4h")
p_npz = storage._path("crypto", "BIGUSDT", "4h", "npz")
time.sleep(0.01)
storage._write_npz(p_npz, make_frame(33))       # تعديل يتجاوز save()
check("  والتعديل الخارجي يُبطلها",
      len(storage.load("crypto", "BIGUSDT", "4h")) == 33,
      str(len(storage.load("crypto", "BIGUSDT", "4h"))))

check("  والتفريغ يعمل",
      (storage.clear_frame_cache() or True)
      and len(storage._FRAME_CACHE) == 0)


# ── ٦) الحدود ──
storage.clear_frame_cache()
check("٦ رمز غير موجود يعطي None",
      storage.load("crypto", "__لا_شيء__", "4h") is None)

empty = pd.DataFrame(columns=list(storage.OHLCV))
empty.index = pd.DatetimeIndex([], tz="UTC")
storage.save("crypto", "EMPTY", "4h", empty)
back_empty = storage.load("crypto", "EMPTY", "4h")
check("  وإطار فارغ لا ينهار", back_empty is not None and len(back_empty) == 0)
check("  وطابعه الأخير None",
      storage.last_time_on_disk("crypto", "EMPTY", "4h") is None)

# عمود ناقص يُملأ NaN لا ينهار — الصيغة الثنائية بأعمدة ثابتة
partial = make_frame(20).drop(columns=["volume"])
storage.save("crypto", "PARTIAL", "4h", partial)
storage.clear_frame_cache()
pb = storage.load("crypto", "PARTIAL", "4h")
check("  والعمود الناقص يصير NaN",
      pb is not None and pb["volume"].isna().all())
check("  وبقيّة الأعمدة سليمة",
      exact(partial[["open", "high", "low", "close"]],
            pb[["open", "high", "low", "close"]]) == "")


# ── ٧) أداة الترحيل تتحقّق قبل الحذف ──
tool = (ROOT / "tools_migrate_storage.py").read_text(encoding="utf-8")
code = "\n".join(l for l in tool.splitlines() if not l.strip().startswith("#"))
check("٧ الترحيل يتحقّق قبل الحذف",
      code.index("verify(") < code.index("f.unlink"))
check("  والمقارنة بلا تسامح",
      "array_equal" in code and "allclose" not in code)
check("  والفشل يُبقي الأصل", "target.unlink(missing_ok=True)" in code)


# ── ٨) تعداد ما على القرص يتبع FORMATS لا قائمةً يدويّة ──
#
# العلّة التي كُتب هذا لأجلها: بعد أن صار npz هو الافتراض، بقي في
# ``market_sync/service.py`` سطرٌ يصفّي على (".parquet", ".csv").
# فصار السوق الأمريكي يرى القرص فارغاً ويسقط إلى قائمة الرموز
# الاحتياطية — عشرة رموز ثابتة، لا تزيد أبداً.
_frame = make_frame(6)
for _s in ("NVDA", "AAPL", "MSFT"):
    storage.save("us", _s, "1h", _frame)
_u = tmp / "us" / "1h"

check("٨ كل لاحقة في FORMATS مسرودة",
      set(storage.SUFFIXES) == {f".{f}" for f in storage.FORMATS})
check("  والمكتوب فعلاً يُرى",
      sorted(storage.stored_symbols("us", "1h")) == ["AAPL", "MSFT", "NVDA"],
      str(sorted(p.name for p in _u.iterdir())))
check("  ولا يفوته الافتراضي npz",
      f".{storage.storage_format()}" in storage.SUFFIXES)
check("  وسوق غير موجود يعيد فارغاً بلا استثناء",
      storage.stored_symbols("لا_سوق", "1h") == [])
check("  والخدمة تستعمل المصدر الواحد",
      "storage.stored_symbols" in (ROOT / "scanner" / "market_sync" / "service.py")
      .read_text(encoding="utf-8"))
check("  ولا تبقى قائمة لواحق يدويّة في الخدمة",
      '(".parquet", ".csv")' not in (ROOT / "scanner" / "market_sync" / "service.py")
      .read_text(encoding="utf-8"))

storage.DATA_DIR = _orig_dir
storage.clear_frame_cache()
shutil.rmtree(tmp, ignore_errors=True)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
