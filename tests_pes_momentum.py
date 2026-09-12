# -*- coding: utf-8 -*-
"""دمج ‏MACD و StochRSI في PES — وحدود ما يدّعيه الدمج.

═══ الخطر الأوّل: العدّ المزدوج ═══

المؤشّران كلاهما **زخم**. ومقياسان لشيءٍ واحد ليسا شاهدين
مستقلّين بل شاهداً واحداً بصوتين. فلو أُضيف كلٌّ عاملاً لصار
وزن عائلة الزخم ٢٥ من ١٠٠ بدل ١٥ — أي أنّ الزخم يصوّت مرّتين.

وهذا هو العطب الذي تحرسه المادّة ١٧ نفسها، والذي وقع في وحدة
الأدلّة من قبل: ثلاثة «أسباب» بأرقامٍ متطابقة كانت الصفقات
الثمانية عشر نفسها.

فيُطلَب هنا: مجموع الأوزان ١٠٠، وحصّة الزخم ١٥ — كما كانت.

═══ والخطر الثاني: إشارةٌ من مؤشّرٍ وحده ═══

المادّة ٣ صريحة: تقاطع StochRSI وحده لا يُنتج إشارة. فتُبنى
تركيبات المادّة ١٦ الأربع ويُطلَب أن يفرّق بينها.

═══ والثالث: إعادة الرسم ═══

تقاطع ‎%K/%D‎ يظهر ويختفي داخل الشمعة الواحدة مرّاتٍ قبل إغلاقها.
فتُغيَّر الشمعة الجارية ويُطلَب ألّا يتغيّر شيء.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.strategies import momentum_confluence as mc   # noqa: E402
from scanner.strategies import pes                          # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


P = pes.load_params()


# ═══════════ أدوات بناء سلاسل مقصودة ═══════════

def _frame(close: np.ndarray, vol=None) -> pd.DataFrame:
    n = len(close)
    idx = pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC")
    v = np.full(n, 1000.0) if vol is None else vol
    return pd.DataFrame({
        "open": close, "high": close * 1.004, "low": close * 0.996,
        "close": close, "volume": v}, index=idx)


# ═══ لماذا قاعٌ مستدير لا خطٌّ مائل ═══
#
# النسخة الأولى بنت الاختبار على هبوطٍ خطّيّ ثمّ صعودٍ خطّيّ —
# ورسبت. والسبب ليس في الكود: المدرَّج على انحدارٍ **ثابت** يستقرّ
# عند الصفر، فما إن يستوي الخطّ حتى يقفز موجباً. فلا يمرّ بحالة
# «سالبٌ وصاعد» أصلاً.
#
# وتلك الحالة — أنفع ما في MACD — تحتاج هبوطاً **يتباطأ**: قاعاً
# مستديراً يُقطع عند نقطة انعطافه. وهذا ما يقع في السوق فعلاً،
# والخطّ المائل تجريدٌ لا يقع.
#
# والقيم أدناه وُجدت بمسحٍ على السلسلة لا بالتخمين.

def _cosine(stop: float, n: int = 300, amp: float = 18.0,
            invert: bool = False) -> np.ndarray:
    """قوسٌ من جيب التمام — يهبط ويتباطأ (أو العكس بـ ``invert``)."""
    t = np.linspace(0, np.pi * stop, n)
    return 100 + (-amp if invert else amp) * np.cos(t)


# سالبٌ وصاعد: التحوّل المبكّر — قبل التقاطع بشمعات
EARLY = _cosine(0.52)
# موجبٌ وصاعد وفوق الإشارة: تحوّلٌ تأكّد
BULL = _cosine(0.70)
# قمّةٌ مستديرة: المدرَّج موجبٌ يهبط
BEAR = _cosine(0.52, invert=True)


# ═══ ١) عائلة الزخم لم تكبر ═══
w = P["weights"]
check("١ مجموع الأوزان ١٠٠", sum(w.values()) == 100, str(sum(w.values())))
fam: dict[str, float] = {}
for k, v in w.items():
    fam[pes.FAMILY[k]] = fam.get(pes.FAMILY[k], 0) + v
check("  وحصّة الزخم ١٥ كما كانت", fam.get("momentum") == 15,
      str(fam.get("momentum")))
# ‏10 + 3 + 2: الالتقاء أخذ وزن macd وجزءاً من rsi/divergence
check("  والالتقاء ١٠", w.get("momentum_confluence") == 10)
check("  و macd لم يعد عاملاً مستقلّاً", not w.get("macd"))
check("  والالتقاء في عائلة الزخم",
      pes.FAMILY["momentum_confluence"] == "momentum")


# ═══ ٢) السلّم يقيس ما يدّعيه ═══
early_df = _frame(EARLY)
up_df = _frame(BULL)
dn_df = _frame(BEAR)

m_up = mc.macd_reading(up_df, P)
m_dn = mc.macd_reading(dn_df, P)
check("٢ المدرَّج صاعد في السلسلة الصاعدة", m_up.get("rising") is True,
      str(m_up.get("hist")))
check("  وهابط في الهابطة", m_dn.get("rising") is False)
# الحالة الأنفع: سالبٌ يصعد — تحسّنٌ قبل التقاطع
# والحالة الأنفع: سالبٌ يصعد — تحسّنٌ قبل التقاطع بشمعات
m_early = mc.macd_reading(early_df, P)
check("  والتحوّل المبكّر يُرصد",
      m_early.get("early_turn") is True and m_early["hist"] < 0,
      f"hist={m_early.get('hist'):.4g} rising={m_early.get('rising')}")
# وهو **قبل** أن يعبر الصفر — وهذا كل الفرق عن التقاطع المتأخّر
check("  وهو قبل عبور الصفر",
      m_early["hist"] < 0 < m_up["hist"])


# ═══ ٣) تقاطع StochRSI وحده لا يعطي شيئاً (المادّة ٣) ═══
#
# ‏MACD هابط + تقاطع صاعد = ارتداد قصير لا إشارة شراء.
stoch_cross = {"ok": True, "cross_up": True, "timing": True,
               "from_low": True, "k_above_d": True, "k": 35, "d": 30,
               "stale_overbought": False, "very_high": False}
c_alone = mc.evaluate_confluence(m_dn, stoch_cross)
check("٣ تقاطع StochRSI مع MACD هابط ≤ ٤",
      c_alone["score"] <= 4, str(c_alone["score"]))
check("  ويُقال السبب", any("لا يتحسّن" in r or "بدأ" in r
                            for r in c_alone["reasons"]))


# ═══ ٤) حالات المادّة ١٦ الأربع تُفرَّق ═══
no_stoch = {"ok": True, "cross_up": False, "timing": False,
            "from_low": True, "k_above_d": False, "k": 45, "d": 50,
            "stale_overbought": False, "very_high": False}
high_stoch = {"ok": True, "cross_up": True, "timing": False,
              "from_low": False, "k_above_d": True, "k": 93, "d": 88,
              "stale_overbought": True, "very_high": True}

case1 = mc.evaluate_confluence(m_up, stoch_cross, rsi_ok=True,
                               external_confirm=True)
case2 = mc.evaluate_confluence(m_up, stoch_cross)      # بلا تأكيد خارجي
case3 = c_alone                                         # MACD هابط
case4 = mc.evaluate_confluence(m_up, high_stoch)        # متشبّع مزمن

check("٤ الحالة ١ (التقاء كامل) ≥ ٩", case1["score"] >= 9,
      str(case1["score"]))
check("  الحالة ٢ (زخم بلا تأكيد) بين ٧ و٩",
      7 <= case2["score"] <= 9, str(case2["score"]))
check("  الحالة ٣ (ارتداد قصير) ≤ ٤", case3["score"] <= 4)
check("  الحالة ٤ (متشبّع مزمن) ≤ ٤", case4["score"] <= 4,
      str(case4["score"]))
# والترتيب بينها صحيح لا الأرقام وحدها
check("  والترتيب ١ > ٢ > ٣",
      case1["score"] > case2["score"] > case3["score"])
check("  والتشبّع المزمن يُذكر",
      any("متشبّع" in r for r in case4["reasons"]))


# ═══ ٥) التوقيت لا يُشترى بمزيدٍ من MACD ═══
#
# القفزة من ٦ إلى ٧ هي دخول StochRSI. فـ MACD مهما قوي بلا
# تقاطعٍ يبقى عند ٦ — ثلاثة مقاييس للزخم لا تصنع توقيتاً.
ceiling = mc.evaluate_confluence(m_up, no_stoch, rsi_ok=True)
check("٥ ‏MACD وحده يبلغ ٦ لا أكثر", ceiling["score"] <= 6,
      str(ceiling["score"]))
check("  ويُقال أنّ التوقيت لم يحن",
      any("التوقيت لم يحن" in r for r in ceiling["reasons"]))


# ═══ ٦) لا إعادة رسم ═══
alt = up_df.copy()
alt.iloc[-1, alt.columns.get_loc("close")] *= 1.25
check("٦ ‏MACD لا يتأثّر بالشمعة الجارية",
      mc.macd_reading(alt, P)["hist"] == m_up["hist"])
s_a = mc.stoch_reading(up_df, P)
s_b = mc.stoch_reading(alt, P)
check("  و StochRSI كذلك",
      (s_a.get("k"), s_a.get("cross_up")) == (s_b.get("k"), s_b.get("cross_up")))
src = (ROOT / "scanner" / "strategies"
       / "momentum_confluence.py").read_text(encoding="utf-8")
check("  والشمعة الجارية تُسقَط", "def _closed" in src
      and "iloc[:-1]" in src)


# ═══ ٧) الحالات الجديدة معرَّفة ومرتّبة ═══
for st in ("EARLY_MOMENTUM", "STRONG_PRE_BREAKOUT", "LATE_MOMENTUM"):
    check(f"٧ {st} معرَّفة",
          st in pes.STATES and st in pes.STATE_LABELS)
# الإنذار المبكّر ليس دخولاً — والتسمية وحدها لا تكفي
check("  والإنذار المبكّر ليس دخولاً",
      "EARLY_MOMENTUM" in pes.NON_ENTRY_STATES)
check("  والمتأخّر ليس دخولاً",
      "LATE_MOMENTUM" in pes.NON_ENTRY_STATES)
check("  و‏STRONG_PRE_BREAKOUT ليست في المستبعَد",
      "STRONG_PRE_BREAKOUT" not in pes.NON_ENTRY_STATES)

pes_src = (ROOT / "scanner" / "strategies" / "pes.py").read_text(
    encoding="utf-8")
code = "\n".join(l for l in pes_src.splitlines()
                 if not l.strip().startswith("#"))
# المتأخّر يُفحص قبل العتبات: نقاطه قد تكون عالية جدّاً، فلو
# فُحص بعدها لخرج «قبل الاختراق» وهو في قمّته
check("  والمتأخّر يُفحص قبل العتبات",
      code.index("LATE_MOMENTUM") < code.index('cfg.get("pre_breakout_min"'))


# ═══ ٨) كل حدٍّ في الملفّ لا في الكود (المادّة ١٥) ═══
raw = (ROOT / "config" / "pes.yaml").read_text(encoding="utf-8")
cfgy = yaml.safe_load(raw)
mom = cfgy.get("momentum") or {}
for key in ("low_zone", "high_zone", "max_overbought_bars", "late_level"):
    check(f"٨ {key} في الملفّ", key in (mom.get("stoch_rsi") or {}))
for key in ("rising_bars", "strong_slope", "slope_bars"):
    check(f"  {key} في الملفّ", key in (mom.get("macd") or {}))
cls = cfgy.get("classification") or {}
for key in ("early_momentum_confluence", "strong_pre_breakout_confluence",
            "strong_pre_breakout_min_rvol"):
    check(f"  {key} في الملفّ", key in cls)
# والتجاوز يسري فعلاً — لا يُقرأ الملفّ ثمّ يُهمَل
custom = {"momentum": {"stoch_rsi": {"high_zone": 55}}}
check("  والتجاوز يسري", mc._cfg(custom, "stoch_rsi", "high_zone") == 55)
check("  وما لم يُذكر يرتدّ للافتراضي",
      mc._cfg(custom, "stoch_rsi", "low_zone") == 30.0)


# ═══ ٩) الإطار الغائب لا يُعاقِب ═══
#
# رمزٌ لم يُزامَن فريمه ليس رمزاً سيّئاً. وصفرٌ صامتٌ لغياب
# بيانات يُقرأ «ضعيف» وهو «مجهول».
only_h4 = mc.measure({"4h": up_df}, P)
check("٩ يعمل بـ 4h وحده", only_h4.get("usable") is True)
check("  ويُعلن مصدر التوقيت",
      only_h4.get("timing_source") == "4h")
check("  ويقول أنّ 1h غائب",
      only_h4["timeframes"]["1h"]["available"] is False)
scan_src = (ROOT / "scanner" / "strategies" / "pes_scan.py").read_text(
    encoding="utf-8")
check("  والمسح لا يشترطها", "OPTIONAL = " in scan_src
      and 'REQUIRED = ("1d", "4h")' in scan_src)


# ═══ ١٠) الزخم يرفع ثقة الاختراق ولا يصنعه (المادّة ٨) ═══
check("١٠ الزخم يرفع الثقة", "confidence_boost" in code)
# ولا يدخل في قرار الاختراق نفسه: ذاك إغلاقٌ وحجمٌ وجسم
bo_fn = code.split("def breakout_check")[1].split("\ndef ")[0]
check("  ولا يدخل قرار الاختراق",
      "momentum" not in bo_fn and "stoch" not in bo_fn)
check("  ويُقال حين لا يدعمه", "لكنّ الزخم لا يدعمه" in pes_src)


bad = 0
for ok, name, extra in results:
    if not ok:
        bad += 1
    print(("✓ " if ok else "✗ ") + name
          + ("" if ok or not extra else "  ← " + extra))
print()
print(f"✗ فشل {bad} من {len(results)}" if bad else f"✓ {len(results)} اختباراً")
sys.exit(1 if bad else 0)
