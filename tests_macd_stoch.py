# -*- coding: utf-8 -*-
"""MACD صاعد + StochRSI موجب — الحالة تُحسب كما وُصفت، وعلى المغلق.

الوصف: «أنجح الصفقات عندما يتقاطع MACD إيجابياً تحت أو فوق الصفر،
مع تقاطع أو استمرارٍ في إيجابية StochRSI». وهذه الفواحص **تشغّل**
الحساب على سلاسل مصنوعة، ثمّ تقارنه بحسابٍ مستقلّ مباشر من
المؤشّرين على مئات السلاسل العشوائية.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.analysis import macd_stoch as M  # noqa: E402
from scanner.indicators.momentum import stoch_rsi  # noqa: E402
from scanner.indicators.trend import macd  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


def series(vals):
    idx = pd.date_range("2026-01-01", periods=len(vals), freq="4h", tz="UTC")
    return pd.Series(np.asarray(vals, dtype=float), index=idx)


# ═══════════ ١) القصير مجهول لا «لا» ═══════════
r = M.evaluate(series(range(30)))
c("١ الشموع القليلة مجهولة", r["state"] == "unknown" and not r["ok"])


# ═══════════ ٢) مرجعٌ مستقلّ على سلاسل عشوائية ═══════════
#
# الحساب نفسه يُكتب هنا ثانيةً بأبسط صورة — حلقةٌ صريحة على
# الأعمدة — ويُقارن بالوحدة على ٤٠٠ سلسلة. اختلافٌ واحد = خلل.
def reference(close: pd.Series) -> str:
    m = macd(close).iloc[:-1]
    s = stoch_rsi(close).iloc[:-1]
    up = False
    for back in range(M.WINDOW):
        i, j = len(m) - 1 - back, len(m) - 2 - back
        if m["macd"].iloc[j] <= m["signal"].iloc[j] and \
                m["macd"].iloc[i] > m["signal"].iloc[i]:
            up = True
            break
    up = up and m["macd"].iloc[-1] > m["signal"].iloc[-1]
    st = s["k"].iloc[-1] > s["d"].iloc[-1]
    return ("aligned" if up and st else "macd_only" if up
            else "stoch_only" if st else "none")


rng = np.random.default_rng(7)
mismatch, seen = [], set()
for n in range(400):
    walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 220)))
    s_ = series(walk)
    got = M.evaluate(s_)
    if not got["ok"]:
        continue
    seen.add(got["state"])
    if got["state"] != reference(s_):
        mismatch.append(n)
c("٢ يطابق المرجع المستقلّ على ٤٠٠ سلسلة", not mismatch,
  f"اختلف في {len(mismatch)}: {mismatch[:5]}")
c("  والحالات الأربع كلّها ظهرت", seen >= {"aligned", "macd_only",
                                          "stoch_only", "none"},
  str(sorted(seen)))


# ═══════════ ٣) الشمعة الجارية لا تغيّر الحكم ═══════════
#
# نُغيّر آخر قيمة تغييراً عنيفاً: الحكم يجب أن يبقى كما هو.
changed = []
for n in range(200):
    walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 220)))
    a = M.evaluate(series(walk))
    walk2 = walk.copy()
    walk2[-1] *= 1.5
    b = M.evaluate(series(walk2))
    if a["state"] != b["state"]:
        changed.append(n)
c("٣ الشمعة الجارية لا تغيّر الحالة", not changed, str(changed[:5]))


# ═══════════ ٤) موضع التقاطع: تحت الصفر أو فوقه ═══════════
#
# «تحت الصفر أو فوقه» حالتان مختلفتان: انعكاسٌ مبكّر واستمرار. ويُفحص
# الموضع بإشارة MACD نفسه في شمعة التقاطع — محسوبةً هنا مستقلّةً.
zones, wrong = set(), []
for n in range(600):
    walk = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 220)))
    s_ = series(walk)
    r = M.evaluate(s_)
    if r.get("state") != "aligned":
        continue
    m = macd(s_).iloc[:-1]
    at = m["macd"].iloc[len(m) - 1 - r["macd_bars_since"]]
    expect = "below" if at < 0 else "above"
    zones.add(r["macd_zone"])
    if r["macd_zone"] != expect or not (0 <= r["macd_bars_since"] < M.WINDOW):
        wrong.append(n)
    want = "تحت الصفر" if expect == "below" else "فوق الصفر"
    if want not in r["text"]:
        wrong.append(n)
c("٤ الموضع يطابق إشارة MACD عند التقاطع", not wrong, str(wrong[:5]))
c("  والموضعان كلاهما ظهرا", zones == {"below", "above"}, str(zones))


# ═══════════ ٥) لا يُضاف إلى التقييم ═══════════
#
# المؤشّران من عائلة الزخم كلاهما (المادّة ١٧): اتّفاقهما شاهدٌ
# واحد. فإن دخل الدرجة ضاعف وزن الزخم بلا معلومةٍ جديدة.
for f in (ROOT / "scanner" / "scoring").rglob("*.py"):
    c(f"٥ ليس في التقييم: {f.name}", "macd_stoch" not in code_of(f))
src = source_of(ROOT / "scanner" / "analysis" / "macd_stoch.py")
c("  وسببه مكتوب", "شاهدٌ واحد يتكلّم" in src)


# ═══════════ ٦) موصولٌ بالشاشة وبالقياس ═══════════
views = code_of(ROOT / "web" / "dashboard" / "views.py")
c("٦ الفلتر في الخادم", 'request.GET.get("combo")' in views)
c("  والمجهول لا يمرّ", 'cb.get("state") != f["combo"]' in views)
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "watches-page.js").read_text(encoding="utf-8")
c("  والمفتاح يُمرَّر للنداء", '"stoch", "combo"]' in js)
c("  والرقائق تُرسَم", "renderComboChips();" in js)
tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "watches.html").read_text(encoding="utf-8")
c("  ومكانها في القالب", 'id="combo-chips"' in tpl)
meas = code_of(ROOT / "tools_osc_measure.py")
c("  وتُقاس على الصفقات المحسومة", "combo_eval(past[\"close\"])" in meas)

sys.exit(c.report())
