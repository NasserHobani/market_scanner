# -*- coding: utf-8 -*-
"""اختبارات الارتباط واختيار الصفقات المستقلّة — بلا Django ولا شبكة.

نشأت هذه الوحدة من ملاحظة بصرية: شارتات ENSO و ARB و KAITO بدت
متطابقة الحركة مع البتكوين. والقياس أعطى ‎+0.27‎ و‎+0.70‎ و‎+0.09‎ —
أي أن واحداً منها فقط مرتبط فعلاً.

فالنظر يبالغ في الارتباط: هبوطان متزامنان يبدوان حركة واحدة. ولهذا
يُقاس ولا يُقدَّر.

    python tests_correlation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import correlation as C

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


def frame(n=400, seed=0, base=None, rho=0.0):
    """سلسلة أسعار؛ ``rho`` نسبة الحركة المشتركة مع ``base``."""
    rng = np.random.default_rng(seed)
    own = rng.normal(0, 1, n)
    r = own if base is None else (rho * base + np.sqrt(max(0, 1 - rho ** 2)) * own)
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame({"close": 100 + np.cumsum(r)}, index=idx), r


btc_df, btc_r = frame(seed=1)
twin_df, _ = frame(seed=2, base=btc_r, rho=0.95)
mid_df, _ = frame(seed=3, base=btc_r, rho=0.50)
free_df, _ = frame(seed=4, base=btc_r, rho=0.02)

btc = C.returns(btc_df)
twin, mid, free = C.returns(twin_df), C.returns(mid_df), C.returns(free_df)

# ══════════════════ القياس نفسه

check("العوائد تُبنى بفهرس واعٍ بالمنطقة",
      btc is not None and str(btc.index.tz) == "UTC")
check("والسلسلة القصيرة تُرفض بدل أن تُقاس",
      C.returns(frame(n=50)[0]) is None,
      "ارتباط على خمسين شمعة ضجيج لا قياس")
check("وإطار بلا إغلاق يُرفض",
      C.returns(pd.DataFrame({"x": [1] * 300})) is None)

c_twin = C.pair_corr(btc, twin)
c_mid = C.pair_corr(btc, mid)
c_free = C.pair_corr(btc, free)
check("التوأم عالي الارتباط", c_twin > 0.9, f"{c_twin:+.2f}")
check("والمتوسط متوسط", 0.35 < c_mid < 0.65, f"{c_mid:+.2f}")
check("والمستقلّ قرب الصفر", abs(c_free) < 0.15, f"{c_free:+.2f}")
check("وارتباط سلسلة بنفسها يساوي واحداً",
      abs(C.pair_corr(btc, btc) - 1.0) < 1e-9)
check("وغياب أحد الطرفين يعطي None", C.pair_corr(btc, None) is None)

# فترتان لا تتقاطعان: يجب ألّا يُخترع رقم
far = pd.Series(np.random.default_rng(9).normal(0, 1, 400),
                index=pd.date_range("2030-01-01", periods=400, freq="h",
                                    tz="UTC"))
check("وفترتان بلا تقاطع تعطيان None", C.pair_corr(btc, far) is None,
      "المحاذاة بالأصفار تُنتج ارتباطاً زائفاً")

# ══════════════════ الرهانات المكافئة

check("رهان واحد يبقى واحداً", abs(C.effective_bets(1, 0.46) - 1) < 1e-9)
e10 = C.effective_bets(10, 0.46)
e20 = C.effective_bets(20, 0.46)
check("وعشرة مراكز بارتباط 0.46 ≈ رهانان", 1.8 < e10 < 2.1, f"{e10:.2f}")
check("وعشرون لا تضيف شيئاً يُذكر", e20 - e10 < 0.2,
      f"{e10:.2f} ← {e20:.2f}")
check("وبلا ارتباط تساوي العدد",
      abs(C.effective_bets(10, 0.0) - 10) < 1e-9)
check("والارتباط التامّ يجعلها رهاناً واحداً",
      C.effective_bets(10, 0.99) < 1.2)
check("والمخاطرة تتضخّم مع العدد لا تثبت",
      C.risk_multiple(20, 0.46) > C.risk_multiple(3, 0.46) > 1.0,
      f"{C.risk_multiple(3, 0.46):.2f} → {C.risk_multiple(20, 0.46):.2f}")
check("وصفر مراكز لا يقسم على صفر", C.effective_bets(0, 0.46) == 0.0)

# ══════════════════ الاختيار

series = {"BTC": btc, "TWIN": twin, "MID": mid, "FREE": free}
kept, dropped = C.select_uncorrelated(["BTC", "TWIN", "FREE"], series,
                                      max_pair=0.55)
check("التوأم يُسقط ويبقى المستقلّ", kept == ["BTC", "FREE"], kept)
check("ويُذكر بمن اصطدم", dropped and dropped[0][1] == "BTC",
      dropped[:1])
check("والترتيب محفوظ — الأول أفضل المرشّحين",
      kept[0] == "BTC", "الجشِعة تحفظ ترتيب الجودة")

kept2, _ = C.select_uncorrelated(["BTC", "TWIN", "FREE"], series,
                                 max_pair=0.99)
check("وحدّ متساهل يمرّر الجميع", len(kept2) == 3)

kept3, _ = C.select_uncorrelated(["BTC", "FREE", "MID"], series,
                                 max_pair=0.55, limit=2)
check("والسقف العددي يُحترم مع الترشيح", len(kept3) == 2, kept3)

# الرمز المجهول يُقبل — الرفض عقوبة على نقص بيانات لا على تشابه
kept4, _ = C.select_uncorrelated(["BTC", "UNKNOWN"], {"BTC": btc},
                                 max_pair=0.55)
check("والرمز الذي لا يُعرف ارتباطه يُقبل", "UNKNOWN" in kept4, kept4)

check("وقائمة فارغة لا تنهار",
      C.select_uncorrelated([], series)[0] == [])
check("ومرشّح واحد يمرّ دائماً",
      C.select_uncorrelated(["TWIN"], series, max_pair=0.0)[0] == ["TWIN"],
      "لا شيء يرتبط به بعد")

# الارتباط السالب يُعامل كالموجب: حركة معاكسة تامّة ليست تنويعاً
inv_df, _ = frame(seed=5, base=-btc_r, rho=0.95)
series["INV"] = C.returns(inv_df)
kept5, _ = C.select_uncorrelated(["BTC", "INV"], series, max_pair=0.55)
check("والارتباط السالب القوي يُسقَط أيضاً", len(kept5) == 1, kept5)

# ══════════════════ الاستخراج والمتوسط

class Row:
    def __init__(self, s): self.symbol = s


check("المفتاح يُستخرج من كائن", C._key(Row("ABC")) == "ABC")
check("ومن زوج (كائن، توصية)", C._key((Row("XYZ"), {})) == "XYZ")
check("ومن قاموس", C._key({"symbol": "QQQ"}) == "QQQ")
check("ومن نصّ", C._key("PLAIN") == "PLAIN")

avg = C.average_corr(["BTC", "TWIN"], series)
check("متوسط المجموعة يُحسب", avg is not None and avg > 0.9, avg)
check("ومجموعة بلا أزواج تعطي None",
      C.average_corr(["BTC"], series) is None)

# ══════════════════ الربط بالمسح

scan_src = (ROOT / "web" / "dashboard" / "management" / "commands"
            / "scan.py").read_text("utf-8")
check("المسح يرشّح بالارتباط بعد الترتيب بالجودة",
      "_drop_correlated" in scan_src
      and scan_src.index("_best_first(reco_candidates")
      < scan_src.index("_drop_correlated(picked"),
      "الترشيح قبل الترتيب يُسقط الأفضل لصالح الأسبق")
check("والعتبة من الإعدادات لا ثابتة", "_max_pair_corr" in scan_src)
check("وفشل الترشيح لا يمنع فتح الصفقات",
      "return picked, []" in scan_src,
      "الترشيح تحسين لا شرط تشغيل")

from scanner import settings_schema as S
check("والإعداد معرَّف بحدّيه", "max_pair_corr" in S.FIELDS
      and S.FIELDS["max_pair_corr"].minimum == 0
      and S.FIELDS["max_pair_corr"].maximum == 1)
check("ويمكن تعطيله بصفر", S.FIELDS["max_pair_corr"].minimum == 0)


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
