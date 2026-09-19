# -*- coding: utf-8 -*-
"""نظام البتكوين سياقٌ للسوق الرقميّ — لا لأرامكو ولا لآبل.

═══ ما كان يقع ═══

``btc_regime`` عاملٌ وزنه ١٠ من ١٠٠، وكان يُحسب ويُضاف **لكل
سوق**. فدرجة سهمٍ سعوديّ تتحرّك عشر نقاطٍ بحركة عملةٍ لا تربطه
بها رابطة. وأسوأ منه مُضاعِف الثقة:

    if btc["label"] == "هابط":  confidence = 0.4

فبتكوينٌ هابط يضرب ثقة **كل** رمزٍ سعوديّ وأمريكيّ بـ٠٫٤ — وهي
تدخل التصنيف، فتُسقِط إشاراتٍ سليمة.

ولم يكن الأثر مرئياً: الرقم يتغيّر ولا شيء يقول لماذا.

═══ ولماذا الحذف لا التصفير ═══

``_na`` يُبقي الوزن في المقام، وهو الصواب لعاملٍ **تعذّر حسابه** —
غيابُ الدليل ليس دليلاً إيجابياً. أمّا غير المنطبق فيُحذَف ويُعاد
وزنه على الباقي، وإلّا خسر السعوديُّ عشر نقاطٍ في كل تقييم وصارت
عتبة ٧٥ عنده ٨٥ فعلياً.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.strategies import pes  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ═══════════ إطارٌ صناعيّ ═══════════
#
# اتّجاهٌ صاعد هادئ ثمّ انضغاط: يعطي درجةً متوسّطة، فتظهر آثار
# التغيير بدل أن تُبتلع في صفرٍ أو مئة.
def _frames(n: int = 320, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="4h", tz="UTC")
    drift = np.linspace(0, 0.35, n)
    noise = rng.normal(0, 0.004, n).cumsum()
    close = 100 * np.exp(drift + noise)
    high = close * (1 + rng.uniform(0.001, 0.01, n))
    low = close * (1 - rng.uniform(0.001, 0.01, n))
    vol = rng.uniform(1e6, 3e6, n)
    vol[-10:] *= 2.5                      # تمدّد حجمٍ قرب النهاية
    h4 = pd.DataFrame({"open": close, "high": high, "low": low,
                       "close": close, "volume": vol}, index=idx)
    d1 = h4.resample("1D").agg({"open": "first", "high": "max", "low": "min",
                                "close": "last", "volume": "sum"}).dropna()
    return {"4h": h4, "1d": d1}


FR = _frames()

BULL = {"usable": True, "score": 9.0, "label": "صاعد"}
BEAR = {"usable": True, "score": 1.0, "label": "هابط"}


def ev(market: str, btc: dict | None):
    return pes.evaluate(FR, btc=btc, params=pes.load_params(), market=market)


# ═══════════ ١) السعوديّ والأمريكيّ لا يتأثّران ═══════════
for mkt in ("saudi", "us"):
    a, b, c = ev(mkt, BULL), ev(mkt, BEAR), ev(mkt, None)
    check(f"١ درجة {mkt} لا تتغيّر بنظام BTC",
          a["score"] == b["score"] == c["score"],
          f"صاعد={a['score']} هابط={b['score']} بلا={c['score']}")
    # ═══ الثقة أخطر من الدرجة ═══
    #
    # ٠٫٤ تضرب كل رمزٍ في السوق دفعةً واحدة، وتدخل التصنيف.
    check(f"  وثقة {mkt} لا تتأثّر",
          a["confidence"] == b["confidence"] == 1.0,
          f"{a['confidence']} / {b['confidence']}")
    check(f"  ولا عامل btc_regime في {mkt}",
          not any(f["key"] == "btc_regime" for f in a["factors"]))
    check(f"  ولا عائلة context في {mkt}", "context" not in a["families"])
    check(f"  والراية تقول: لا ينطبق", a["btc_applies"] is False)
    check(f"  و‎btc‎ فارغ", a["btc"] == {})


# ═══════════ ٢) الكريبتو كما كان ═══════════
cb, cr = ev("crypto", BULL), ev("crypto", BEAR)
check("٢ درجة الكريبتو تتغيّر بنظام BTC", cb["score"] != cr["score"],
      f"{cb['score']} مقابل {cr['score']}")
check("  والصاعد أعلى", cb["score"] > cr["score"])
check("  والثقة تهبط في الهابط", cr["confidence"] == 0.4, str(cr["confidence"]))
check("  وتبقى كاملة في الصاعد", cb["confidence"] == 1.0)
check("  والعامل موجود", any(f["key"] == "btc_regime" for f in cb["factors"]))
check("  والعائلة موجودة", "context" in cb["families"])
check("  والراية تقول: ينطبق", cb["btc_applies"] is True)
# وبلا نظامٍ محسوب يبقى العامل حاضراً بصفرٍ معلَّل — لا يُحذف
cn = ev("crypto", None)
na = [f for f in cn["factors"] if f["key"] == "btc_regime"]
check("  وتعذّر الحساب يُصفَّر لا يُحذَف",
      len(na) == 1 and na[0].get("unavailable") is True)


# ═══════════ ٣) الوزن يُعاد توزيعه ═══════════
#
# بلا إعادة توزيع يصير سقف السعوديّ ٩٠، فتصير عتبة ٧٥ عنده ٨٣٪
# من المتاح — أي أصعب، بلا أن يُعلَن ذلك في أيّ مكان.
def _maxsum(res) -> float:
    return round(sum(f["max"] for f in res["factors"]), 2)


check("٣ سقف السعوديّ = سقف الكريبتو",
      abs(_maxsum(ev("saudi", None)) - _maxsum(cb)) < 0.01,
      f"سعودي={_maxsum(ev('saudi', None))} كريبتو={_maxsum(cb)}")
check("  والسقف مئة", abs(_maxsum(cb) - 100.0) < 0.51, str(_maxsum(cb)))

# وكل عامل باقٍ كبُر بالنسبة نفسها
_c = {f["key"]: f["max"] for f in cb["factors"]}
_s = {f["key"]: f["max"] for f in ev("saudi", None)["factors"]}
_shared = [k for k in _s if k in _c and _c[k] > 0]
_ratios = sorted({round(_s[k] / _c[k], 4) for k in _shared})
check("  والنسبة واحدة لكل العوامل", len(_ratios) == 1, str(_ratios))
check("  والنسبة أكبر من واحد", _ratios and _ratios[0] > 1.0, str(_ratios))


# ═══════════ ٤) المصدر: لا تُقرأ شموع BTC أصلاً ═══════════
#
# القطع في ``evaluate`` وحدها يترك القرص يُقرأ بلا فائدة لكل سوق.
# وما لا يُقرأ لا يُسرَّب.
_scan_src = (ROOT / "scanner" / "strategies" / "pes_scan.py").read_text(
    encoding="utf-8")
_tree = ast.parse(_scan_src)
_fn = next(n for n in ast.walk(_tree)
           if isinstance(n, ast.FunctionDef) and n.name == "scan")
_body = ast.get_source_segment(_scan_src, _fn) or ""
_code = "\n".join(l for l in _body.splitlines()
                  if not l.strip().startswith("#"))
check("٤ المسح يشترط السوق قبل قراءة BTC",
      "BTC_MARKETS" in _code and _code.find("BTC_MARKETS") < _code.find("BTCUSDT"))
check("  ويمرّر السوق إلى evaluate", "market=market" in _code)

# وأداة القياس كذلك — وإلّا قِيست درجاتٌ مشوبة وبُني عليها حكم
_meas = (ROOT / "tools_pes_measure.py").read_text(encoding="utf-8")
_mcode = "\n".join(l for l in _meas.splitlines()
                   if not l.strip().startswith("#"))
check("  وأداة القياس تشترطه", "BTC_MARKETS" in _mcode)
check("  وتمرّر السوق", "market=market" in _mcode)

# والقائمة تُقرأ ولا تُخمَّن
check("  و‎BTC_MARKETS‎ معرّفة", isinstance(pes.BTC_MARKETS, frozenset))
check("  والكريبتو فيها", "crypto" in pes.BTC_MARKETS)
check("  والسعوديّ ليس فيها", "saudi" not in pes.BTC_MARKETS)
# سوقٌ مجهول لا يُحسب له BTC — الافتراض الآمن
check("  والمجهول خارجها", "nasdaq" not in pes.BTC_MARKETS)
check("  وسوقٌ مجهول لا يتأثّر",
      ev("nasdaq", BULL)["score"] == ev("nasdaq", BEAR)["score"])


# ═══════════ ٥) الشاشة لا تعرض ما لا ينطبق ═══════════
_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "pes-page.js").read_text(encoding="utf-8")
_jscode = "\n".join(l for l in _js.splitlines()
                    if not l.strip().startswith("//"))
check("٥ شارة BTC مشروطة", "btcChip" in _jscode and "btc.label" in _jscode)
# ═══ وليست ‎groups[0]‎ ═══
#
# كان رأس الصفحة يأخذ أوّل مجموعة أيّاً كانت — فإن جاء السعوديّ
# أوّلاً عُرض نظام BTC كأنّه سياق تلك الصفحة.
check("  ورأس الصفحة يختار مجموعة الكريبتو",
      "groups || []).filter" in _jscode or ".filter(function (g)" in _jscode)
check("  ولا groups[0] مباشرةً", "d.groups || [])[0]" not in _jscode)


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
