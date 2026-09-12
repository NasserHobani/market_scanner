# -*- coding: utf-8 -*-
"""ترحيل ملفّات الشموع إلى الصيغة الثنائية.

    python tools_migrate_storage.py --check     # قياس بلا تعديل
    python tools_migrate_storage.py             # ترحيل فعلي

═══ لماذا ═══

قياس على ملفّاتك (1578 شمعة، 96KB):

    CSV → DataFrame      16.21 ms
    ثنائي → DataFrame     0.63 ms      أسرع ×25.6
    الحجم                71KB مقابل 96KB

ولـ500 رمز: **8.1 ثانية تصير 0.3**.

والترحيل ليس إجبارياً — كل رمز يُحدَّث يُكتب بالصيغة الجديدة تلقائياً،
والقديم يبقى مقروءاً. لكنّ الترحيل دفعةً واحدة يعطي المكسب فوراً بدل
انتظار دورة تحديث كاملة.

**كل ملف يُتحقّق منه قبل حذف أصله**: تُقرأ النسخة الجديدة وتُقارَن
بالأصل قيمةً بقيمة وطابعاً بطابع، بلا تسامح. والفشل يترك الأصل مكانه.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scanner import storage  # noqa: E402


def verify(original: pd.DataFrame, rebuilt: pd.DataFrame) -> str:
    """يقارن بلا تسامح. يعيد سبب الاختلاف أو نصّاً فارغاً."""
    if rebuilt is None:
        return "تعذّرت القراءة"
    if len(original) != len(rebuilt):
        return f"عدد الصفوف {len(original)} ≠ {len(rebuilt)}"
    a = pd.DatetimeIndex(original.index)
    b = pd.DatetimeIndex(rebuilt.index)
    a = a.tz_localize("UTC") if a.tz is None else a.tz_convert("UTC")
    b = b.tz_localize("UTC") if b.tz is None else b.tz_convert("UTC")
    if not np.array_equal(a.view("int64"), b.view("int64")):
        return "الطوابع الزمنية مختلفة"
    for col in storage.OHLCV:
        if col not in original.columns:
            continue
        x = original[col].to_numpy(dtype=np.float64)
        y = rebuilt[col].to_numpy(dtype=np.float64)
        if not np.array_equal(x, y, equal_nan=True):
            return f"العمود {col} مختلف"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser(description="ترحيل الشموع إلى الصيغة الثنائية")
    ap.add_argument("--check", action="store_true", help="قياس بلا تعديل")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    files = sorted(Path("data").rglob("*.csv"))
    files = [f for f in files if len(f.parts) >= 3 and f.parts[1] != "archive"]
    if a.limit:
        files = files[: a.limit]

    print("=" * 62)
    print("ترحيل الشموع إلى الصيغة الثنائية")
    print("=" * 62)
    print(f"ملفّات CSV: {len(files)}")
    if not files:
        print("لا شيء للترحيل — كل الشموع بالصيغة الجديدة.")
        return 0

    total_old = sum(f.stat().st_size for f in files)
    print(f"الحجم الحالي: {total_old / 1024 / 1024:.1f} MB")

    if a.check:
        sample = files[: min(30, len(files))]
        t0 = time.time()
        for f in sample:
            pd.read_csv(f, index_col=0, parse_dates=True)
        csv_ms = (time.time() - t0) * 1000 / len(sample)
        print(f"\nقراءة CSV: {csv_ms:.2f} ms/ملف")
        print(f"المتوقَّع بعد الترحيل: ~{csv_ms / 25:.2f} ms/ملف")
        print(f"لـ500 رمز: {csv_ms * 500 / 1000:.1f}s → "
              f"~{csv_ms / 25 * 500 / 1000:.1f}s")
        print("\nشغّل بلا --check للترحيل الفعلي.")
        return 0

    ok = failed = 0
    reasons: dict[str, int] = {}
    total_new = 0
    t0 = time.time()
    for i, f in enumerate(files, start=1):
        # ‏data/<سوق>/<فريم>/<رمز>.csv
        try:
            market, timeframe, name = f.parts[-3], f.parts[-2], f.stem
        except (IndexError, ValueError):
            continue
        try:
            original = pd.read_csv(f, index_col=0, parse_dates=True)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            reasons[f"قراءة: {type(exc).__name__}"] = \
                reasons.get(f"قراءة: {type(exc).__name__}", 0) + 1
            continue

        target = storage._path(market, name, timeframe, "npz")
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            storage._write_npz(target, original)
            rebuilt = storage._read_npz(target)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            reasons[f"كتابة: {type(exc).__name__}"] = \
                reasons.get(f"كتابة: {type(exc).__name__}", 0) + 1
            continue

        why = verify(original, rebuilt)
        if why:
            failed += 1
            reasons[why] = reasons.get(why, 0) + 1
            target.unlink(missing_ok=True)      # لا نترك نسخة مشكوكاً فيها
            continue

        total_new += target.stat().st_size
        f.unlink(missing_ok=True)               # بعد التحقّق وحده
        ok += 1
        if i % 250 == 0:
            print(f"  … {i}/{len(files)}")

    el = time.time() - t0
    storage.clear_frame_cache()
    print(f"\nرُحِّل: {ok} · فشل: {failed} · الزمن: {el:.1f}s")
    if total_new:
        print(f"الحجم: {total_old / 1024 / 1024:.1f} MB → "
              f"{total_new / 1024 / 1024:.1f} MB "
              f"(توفير {(1 - total_new / total_old) * 100:.0f}%)")
    for why, n in sorted(reasons.items(), key=lambda kv: -kv[1])[:5]:
        print(f"  ✗ {why}: {n}")
    if failed:
        print("\nالملفّات الفاشلة بقيت CSV كما هي — لا فقدان.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
