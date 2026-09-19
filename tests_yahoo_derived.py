# -*- coding: utf-8 -*-
"""‏4h من ياهو — الفريم الذي لا وجود له، والسوق الذي غاب بسببه.

═══ العطب ═══

قائمة ``INTERVAL`` في محوّل ياهو لا تحوي ‎4h‎، ولن تحويها: ياهو لا
يعطي هذا الفاصل. فكان ``fetch(sym, "4h")`` يرمي «فريم غير مدعوم»،
وتفشل مزامنة كل رمزٍ سعوديّ على ‎4h‎ في كل دورة.

وأثرُه لم يكن رسالة خطأ بل **غياباً كاملاً**:

    الماسحات تقرأ  stored_symbols(market, "4h")
    السعودي عنده   صفر ملفّ 4h
    فالنتيجة       صفر صفّ — بلا خطأ ولا سبب

٣٢٥ شركة سعودية لم تدخل تقييم PES ولا مرّة. والشاشة سليمة المظهر
تماماً: سوقٌ بلا فرص، لا سوقٌ لم يُقرأ.

وقيس على الخادم: ``saudi مكتشَف 325 · على القرص 0 (0%)`` — بينما
الكريبتو والأمريكي ١٠٠٪.

═══ والاشتقاق من الساعيّ لا من اليوميّ ═══

ياهو يعطي ٧٣٠ يوماً من الساعيّ — أي أكثر من ألف شمعة أربع‑ساعية.
والاشتقاق من اليوميّ مستحيل: لا يُبنى الأصغر من الأكبر.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.adapters import yahoo as Y  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


class _Stub(Y.YahooAdapter):
    """محوّلٌ لا يلمس الشبكة — يعيد ساعيّاً مصنوعاً."""

    def __init__(self, hourly: pd.DataFrame):
        super().__init__()
        self._hourly = hourly
        self.asked: list[tuple[str, int]] = []

    def fetch(self, symbol, timeframe, limit=1500):
        d = Y.DERIVED.get(timeframe)
        if d:
            return super().fetch(symbol, timeframe, limit)
        self.asked.append((timeframe, limit))
        return self._hourly.tail(limit)


def _hourly(n=600, *, start="2025-01-01 07:00", session=None):
    """ساعيٌّ متّصل، أو بجلسةٍ قصيرة كالسوق السعودي."""
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    if session:
        idx = pd.DatetimeIndex([t for t in idx if t.hour in session])
    c = np.linspace(100, 160, len(idx))
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99,
                         "close": c, "volume": np.full(len(idx), 1e5)},
                        index=idx)


# ═══════════ ١) الخريطة ═══════════
check("١ ‎4h‎ ليست في INTERVAL", "4h" not in Y.INTERVAL)
check("  لكنّها في DERIVED", "4h" in Y.DERIVED)
check("  ومصدرها الساعيّ", Y.DERIVED["4h"][0] == "1h",
      str(Y.DERIVED.get("4h")))
check("  ومعاملها ٤", Y.DERIVED["4h"][1] == 4)
# اليوميّ يبقى مباشراً — اشتقاقُه من الساعيّ هدرٌ ويخسر التاريخ
check("  واليوميّ مباشر", "1d" in Y.INTERVAL and "1d" not in Y.DERIVED)


# ═══════════ ٢) الاشتقاق ═══════════
a = _Stub(_hourly(600))
out = a.fetch("2222.SR", "4h", limit=100)
check("٢ يعيد إطاراً غير فارغ", not out.empty)
check("  وأعمدته موحّدة",
      set(out.columns) >= {"open", "high", "low", "close", "volume"},
      str(list(out.columns)))
check("  وعدده نحو ربع الساعيّ",
      120 <= len(out) * 4 <= 700 or len(out) <= 100, str(len(out)))
# ═══ الفاصل أربع ساعات ═══
_deltas = set(pd.Series(out.index).diff().dropna().dt.total_seconds() / 3600)
check("  والفواصل من مضاعفات ٤",
      all(float(d) % 4 == 0 for d in _deltas), str(sorted(_deltas)[:5]))

# ═══ التجميع صحيح ═══
#
# أعلى الشمعة الأربع‑ساعية = أعلى ساعاتها. وخطأٌ هنا يعطي شمعاتٍ
# تبدو سليمة وقيمُها لأوقاتٍ أخرى — ولا شيء يقول ذلك.
h = _hourly(600)
first_t = out.index[0]
window = h[(h.index >= first_t) & (h.index < first_t + pd.Timedelta("4h"))]
if len(window):
    check("  والأعلى = أعلى ساعاته",
          abs(float(out["high"].iloc[0]) - float(window["high"].max())) < 1e-6,
          f"{float(out['high'].iloc[0]):.4f} مقابل {float(window['high'].max()):.4f}")
    check("  والافتتاح = افتتاح أوّلها",
          abs(float(out["open"].iloc[0]) - float(window["open"].iloc[0])) < 1e-6)
    check("  والإغلاق = إغلاق آخرها",
          abs(float(out["close"].iloc[0]) - float(window["close"].iloc[-1])) < 1e-6)
    check("  والحجم مجموعٌ",
          abs(float(out["volume"].iloc[0]) - float(window["volume"].sum())) < 1,
          f"{float(out['volume'].iloc[0])} مقابل {float(window['volume'].sum())}")

# ═══ النسبة إلى البداية ═══
#
# شمعة ‎12:00‎ تحمل ما بين ‎12:00‎ و‎16:00‎. والنسبةُ إلى النهاية
# تزيح التاريخ أربع ساعات، فينزلق كل مؤشّرٍ يُقارَن بفريمٍ آخر.
check("  والشمعة تُنسَب إلى بدايتها",
      out.index[0] <= h.index[0] + pd.Timedelta("4h"),
      f"{out.index[0]} مقابل أوّل ساعيّ {h.index[0]}")


# ═══════════ ٣) جلسةٌ قصيرة — السوق السعودي ═══════════
#
# السوق يعمل نحو خمس ساعات، فأغلب دلاء اليوم فارغة. و‎NaN‎ فيها
# يُفسد كل حسابٍ بعدها بصمت.
sess = _Stub(_hourly(1200, session={7, 8, 9, 10, 11, 12}))
out_s = sess.fetch("1120.SR", "4h", limit=200)
check("٣ الجلسة القصيرة تُشتقّ", not out_s.empty, str(len(out_s)))
check("  ولا NaN في الأسعار",
      not out_s[["open", "high", "low", "close"]].isna().any().any())
check("  ولا شمعة مقلوبة",
      bool((out_s["high"] >= out_s["low"]).all()))
check("  والأعلى ≥ الإغلاق",
      bool((out_s["high"] >= out_s["close"]).all()))


# ═══════════ ٤) الطلب يكفي ═══════════
#
# طلبُ ١٠٠ شمعة أربع‑ساعية يحتاج ٤٠٠ ساعية على الأقلّ — وأكثر،
# لأنّ الجلسة القصيرة لا تملأ الدلاء. وطلبُ ١٠٠ ساعية يعطي ٢٥
# شمعة، فتسقط كل الحسابات التي تطلب ٦٠.
a2 = _Stub(_hourly(2000))
a2.fetch("X", "4h", limit=100)
check("٤ يطلب ساعيّاً أكثر من المطلوب",
      a2.asked and a2.asked[0][1] >= 400,
      str(a2.asked))
check("  وبهامشٍ فوق القسمة", a2.asked and a2.asked[0][1] > 400,
      str(a2.asked))


# ═══════════ ٥) الفشل معلَن لا صامت ═══════════
empty = _Stub(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))
try:
    empty.fetch("X", "4h")
    check("٥ الفارغ يرمي بوضوح", False, "لم يرمِ")
except Exception as exc:  # noqa: BLE001
    check("٥ الفارغ يرمي بوضوح", True)
    check("  والرسالة تذكر الرمز والفريم",
          "X" in str(exc) and "4h" in str(exc), str(exc)[:90])

# وفريمٌ لا يُدعم ولا يُشتقّ يبقى خطأً صريحاً
try:
    _Stub(_hourly(100)).fetch("X", "3s")
    check("  والمجهول يرمي", False, "لم يرمِ")
except Exception as exc:  # noqa: BLE001
    check("  والمجهول يرمي", "غير مدعوم" in str(exc), str(exc)[:80])


# ═══════════ ٦) السوق السعودي يستعمل ياهو ═══════════
_cfg = (ROOT / "config" / "saudi.yaml").read_text(encoding="utf-8")
_code = "\n".join(l for l in _cfg.splitlines()
                  if not l.strip().startswith("#"))
check("٦ السعودي يجلب من ياهو", "adapter: yahoo" in _code, "")
# والماسحات تقرأ 4h — فبلا اشتقاقها لا يُقرأ السوق أصلاً
_scan = (ROOT / "scanner" / "strategies" / "pes_scan.py").read_text(
    encoding="utf-8")
check("  والمسح يقرأ 4h", 'stored_symbols(market, "4h")' in _scan)


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name
          + (f"   [{extra}]" if extra and not ok else ""))
bad = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad)}/{len(results)} "
      + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
sys.exit(1 if bad else 0)
