# -*- coding: utf-8 -*-
"""اختبارات الاختبار الخلفي — أهمّها إثبات انعدام التسريب المستقبلي.

التسريب المستقبلي هو السبب الأول لاختبار خلفي مربح على الورق وخاسر في
السوق: يكفي أن يرى القرارُ شمعةً لم تُغلق بعد ليصير كل شيء جميلاً.
لذلك الاختبار هنا لا يكتفي بقراءة الكود — بل يشوّه المستقبل تشويهاً
متطرفاً ويتأكد أن القرارات لم تتغيّر بحرف.

    python tests_recobt.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.backtest import recobt
from scanner.config import load_market
from scanner.tracking import LOST, OPEN, PENDING, WON

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


CFG = load_market(ROOT / "config" / "crypto.yaml")


def synth(n=700, seed=7):
    """سوق اصطناعي بتذبذب معقول — يكفي لتوليد خطط."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0004, 0.012, n)
    close = 100 * np.exp(np.cumsum(steps))
    high = close * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.006, n)))
    open_ = np.concatenate([[close[0]], close[:-1]])
    vol = np.abs(rng.normal(1000, 300, n))
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": vol}, index=idx)


def real_frames(limit=3, min_signals=1, scan_at_most=14):
    """بيانات حقيقية مخزّنة — الاصطناعية لا تُخرج خططاً لأن محرّك
    التوصية صارم، فاختبار التسريب عليها بلا معنى.

    الأكبر ملفاً أولاً: أطول تاريخ يعني فرصة أعلى لوجود خطط، فنصل
    للعيّنة المطلوبة بأقل عدد تقييمات.
    """
    from scanner import storage

    # ═══ اللواحق من ``storage`` لا مكتوبة ═══
    #
    # كان ``base.glob("*.csv")`` — قائمةٌ يدويّة كُتبت يوم كانت
    # الصيغة نصّاً. ولمّا صار ``npz`` هو الافتراض وتحوّلت الملفّات
    # واحداً واحداً عند الحفظ، صار هذا يجد **صفر** رموز، فيُعلن
    # الاختبار فشلاً وهو لم يفحص شيئاً.
    #
    # وهي العلّة نفسها التي أوقفت اكتشاف السوق الأمريكي. والدرس
    # واحد: من أراد تعداد ما على القرص فليسأل ``storage``.
    syms = storage.stored_symbols("crypto", "4h")

    def _size(sym: str) -> int:
        for sfx in storage.SUFFIXES:
            f = ROOT / "data" / "crypto" / "4h" / f"{sym}{sfx}"
            if f.exists():
                return f.stat().st_size
        return 0

    syms.sort(key=lambda s: -_size(s))
    out = []
    for sym in syms[:scan_at_most]:
        df = storage.load("crypto", sym, "4h")
        if df is None or len(df) < 900:
            continue
        sig = recobt.scan_symbol(df, sym, "4h", CFG, step=STEP, warmup=WARM)
        print(f"  · {sym:<14} {len(sig)} خطة", flush=True)
        if len(sig) >= min_signals:
            out.append((sym, df, sig))
        if len(out) >= limit:
            break
    return out


STEP, WARM = 45, 500
print("جمع عيّنة حقيقية…", flush=True)
REAL = real_frames()
SIGS = [s for _, _, sig in REAL for s in sig]
check("المحرّك يولّد خططاً من تاريخ حقيقي",
      len(SIGS) > 0, f"{len(REAL)} رمز · {len(SIGS)} خطة")

# ═══════════ التسريب المستقبلي ═══════════
# نشوّه النصف الثاني تشويهاً لا يمكن تجاهله. القرارات المتخذة في النصف
# الأول يجب ألا تتغيّر — لا عدداً ولا سعر دخول ولا تصنيفاً.
print("اختبار التسريب…", flush=True)
base, after = [], []
CUT = 0
for name, df, sig in REAL:
    cut = len(df) - 200            # نشوّه آخر مئتي شمعة
    warped = df.copy()
    for col in ("open", "high", "low", "close"):
        warped.iloc[cut:, warped.columns.get_loc(col)] *= 5
    warped.iloc[cut:, warped.columns.get_loc("volume")] *= 50
    base += [s for s in sig if s.index < cut]
    after += [s for s in recobt.scan_symbol(warped, name, "4h", CFG,
                                            step=STEP, warmup=WARM)
              if s.index < cut]
    CUT = cut

check("عدد القرارات قبل نقطة التشويه لم يتغيّر",
      len(base) == len(after), f"{len(base)} ← {len(after)}")
same_plan = all(
    a.index == b.index and abs(a.entry - b.entry) < 1e-9
    and abs(a.stop - b.stop) < 1e-9 and a.grade == b.grade
    and abs(a.score - b.score) < 1e-9
    for a, b in zip(base, after)
)
check("وكل خطة مطابقة تماماً (دخول ووقف وتصنيف ودرجة)", same_plan)
check("أي أن القرار لا يرى المستقبل إطلاقاً", len(base) > 0 and same_plan,
      "بلا قرارات لا معنى للاختبار" if not base else "")

# ═══════════ الحسم يستعمل المستقبل — وهذا صحيح ═══════════
# القرار لا يرى ما بعده، لكن الحسم يجب أن يراه وإلا لم تُحسم صفقة.
# التشويه هنا يبدأ من الشمعة التالية للإشارة مباشرة: تشويه بعيد لا
# تصله الصفقة (تُحسم خلال 30–100 شمعة) لا يثبت شيئاً — وهذا خطأ وقعت
# فيه صياغة الاختبار أولاً.
def _ramp(df, at, target_mult, over=12):
    """يغيّر المستقبل تدريجياً بلا فجوة.

    الضرب المفاجئ يصنع فجوة تُلغي الخطة قبل الدخول (بحق)، فيصير
    الاختبار يقيس مسار الفجوة لا مسار الحسم العادي. التدرّج يحاكي
    هبوطاً أو صعوداً حقيقياً.
    """
    import numpy as np

    w = df.copy()
    n = len(w) - at
    if n <= 0:
        return w
    ramp = np.concatenate([
        np.linspace(1.0, target_mult, min(over, n)),
        np.full(max(0, n - over), target_mult),
    ])[:n]
    for col in ("open", "high", "low", "close"):
        j = w.columns.get_loc(col)
        w.iloc[at:, j] = w.iloc[at:, j].to_numpy() * ramp
    return w


def resolution_follows_future() -> bool:
    """مستقبلان مختلفان بعد الإشارة نفسها يجب أن يعطيا نتيجتين."""
    for name, df, sig in REAL:
        for one in sig:
            if one.status not in (WON, LOST):
                continue
            got = {}
            for label, mult in (("crash", 0.75), ("rally", 1.5)):
                w = _ramp(df, one.index + 1, mult)
                again = recobt.scan_symbol(w, name, "4h", CFG, step=STEP,
                                           warmup=WARM, start=one.index,
                                           end=one.index)
                got[label] = (again[0].status, again[0].r_multiple) if again else None
            if got["crash"] and got["rally"] and got["crash"] != got["rally"]:
                return True
    return False


check("الحسم يقرأ ما بعد الإشارة (مستقبلان ← نتيجتان)",
      resolution_follows_future(),
      "لا صفقة محسومة في العيّنة" if not [s for s in SIGS
                                          if s.status in (WON, LOST)] else "")

# ═══════════ سلامة المخرجات ═══════════
check("كل خطة صالحة: وقف < دخول < هدف",
      all(s.stop < s.entry < s.target for s in SIGS),
      [(s.stop, s.entry, s.target) for s in SIGS[:2]])
check("الحالات من المجموعة المعروفة",
      all(s.status in (WON, LOST, OPEN, PENDING, "expired") for s in SIGS),
      sorted({s.status for s in SIGS}))
closed = [s for s in SIGS if s.status in (WON, LOST)]
check("المحسومة لها مضاعف R",
      all(s.r_multiple is not None for s in closed), len(closed))
check("الرابحة موجبة والخاسرة سالبة",
      all(s.r_multiple > 0 for s in closed if s.status == WON)
      and all(s.r_multiple < 0 for s in closed if s.status == LOST))

# ═══════════ منع تضخيم العيّنة ═══════════
entries = [round(s.entry, 8) for s in SIGS]
dupes = len(entries) - len(set(entries))
check("الخطة المتكرّرة على شموع متتالية لا تُسجَّل مراراً",
      dupes == 0, f"{dupes} مكرّرة")

# ═══════════ حدود المدى ═══════════
_df = REAL[0][1] if REAL else synth()
check("start/end يحصران المدى",
      all(500 <= s.index <= 600
          for s in recobt.scan_symbol(_df, "X", "4h", CFG, step=10,
                                      warmup=WARM, start=500, end=600)))
check("تاريخ أقصر من الإحماء ← لا قرارات",
      recobt.scan_symbol(_df.iloc[:100], "X", "4h", CFG) == [])
check("جدول فارغ ← لا انهيار",
      recobt.scan_symbol(pd.DataFrame(), "X", "4h", CFG) == [])

# ═══════════ التقرير ═══════════
rep = recobt.report(SIGS, min_n=1)
check("التقرير يحمل المفاتيح المتوقّعة",
      {"overall", "by_grade", "by_timeframe", "by_factor"} <= set(rep),
      sorted(rep))
o = rep["overall"]
check("المجموع = محسومة + مفتوحة + منتظرة + منتهية",
      o["total"] == len(SIGS)
      and o["closed"] + o["open"] + o["pending"] + o["expired"] == o["total"],
      f"{o['total']} vs {o['closed']}+{o['open']}+{o['pending']}+{o['expired']}")
check("التقرير الفارغ لا ينهار", recobt.report([])["overall"]["total"] == 0)

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
