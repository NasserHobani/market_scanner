# -*- coding: utf-8 -*-
"""‏Supertrend عاملاً وخطّاً — وما الذي يضيفه فعلاً.

═══ القاعدة ١٧ أوّلاً ═══

‏EMA و‏ADX و‏Supertrend ثلاثتها تقيس **الاتجاه**. واجتماعها ليس
ثلاث إشارات بل إشارةٌ واحدة بثلاثة أسماء — وهذا نصّ القاعدة ١٧
في هذا المشروع.

فإدخال Supertrend عاملاً مستقلّاً بوزنٍ **مضاف** كان سيرفع عائلة
«الاتجاه» من ٢٥ إلى ٢٩، فتصوّت أكثر من الحجم والتقلّب — وهو
بالضبط ما وُضعت القاعدة لمنعه.

فالوزن اقتُطع لا أُضيف:

    قبل:  daily 10 + h4 10 + adx 5            = 25
    بعد:  daily  8 + h4  8 + adx 5 + st 4     = 25

═══ وما الذي يضيفه إن كان مكرّراً؟ ═══

«صاعد» مكرّرة، نعم. لكنّ **متى انقلب** معلومةٌ لا يعطيها EMA ولا
ADX. فأكثر وزن العامل على حداثة الانقلاب لا على اتّجاهه:

    ٠٫٢٥ اتجاه · ٠٫٢٠ اتّفاق الفريمين · ٠٫٣٥ حداثة · ٠٫٢٠ قرب الخطّ

═══ والشمعة الجارية ═══

‏Supertrend يعيد رسم حدّه مع كل تكّة. فالقرار من آخر شمعة
**مغلقة**، والخطّ المرسوم وحده يشمل الجارية — لأنّ المستخدم
يقارنه بشارته.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.analysis import supertrend_layer as SL  # noqa: E402
from scanner.indicators.trend import (  # noqa: E402
    supertrend, supertrend_state)
from scanner.strategies import pes  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def _df(closes, *, start="2025-01-01", freq="4h") -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    idx = pd.date_range(start, periods=len(c), freq=freq, tz="UTC")
    return pd.DataFrame({"open": c, "high": c * 1.004, "low": c * 0.996,
                         "close": c, "volume": np.full(len(c), 1e6)},
                        index=idx)


# ═══════════ ١) الحساب ═══════════
_up = np.linspace(100, 160, 120)
st = supertrend(_df(_up))
check("١ الاتجاه ‎±1‎ لا غير",
      set(np.unique(st["direction"].to_numpy())) <= {1.0, -1.0})
check("  وصعودٌ مطّرد يعطي اتجاهاً صاعداً",
      float(st["direction"].iloc[-1]) > 0)
# والخطّ تحت السعر في الصعود — وإلّا فالحدّان مقلوبان
check("  والخطّ تحت السعر",
      float(st["supertrend"].iloc[-1]) < float(_up[-1]))

_down = np.linspace(160, 100, 120)
st_d = supertrend(_df(_down))
check("  وهبوطٌ مطّرد يعطي هابطاً", float(st_d["direction"].iloc[-1]) < 0)
check("  والخطّ فوق السعر", float(st_d["supertrend"].iloc[-1]) > float(_down[-1]))


# ═══════════ ٢) الحالة من الشمعة المغلقة ═══════════
#
# الفحص الحاسم: شمعةٌ أخيرة ضخمة يجب ألّا تغيّر الحالة، لأنّها
# جارية. وبلا هذا يظهر انقلابٌ ويختفي مع كل تحديث.
base = list(np.linspace(100, 140, 120))
s_calm = supertrend_state(_df(base))
s_spike = supertrend_state(_df(base + [40.0]))
check("٢ الشمعة الجارية لا تغيّر الحالة",
      s_calm["direction"] == s_spike["direction"],
      f"{s_calm['direction']} ← {s_spike['direction']}")
check("  والحالة صالحة", s_calm["usable"] is True)
check("  والخطّ رقمٌ لا NaN",
      s_calm["line"] is not None and np.isfinite(float(s_calm["line"])))

src = (ROOT / "scanner" / "indicators" / "trend.py").read_text(encoding="utf-8")
_tree = ast.parse(src)
_fn = next(n for n in ast.walk(_tree)
           if isinstance(n, ast.FunctionDef) and n.name == "supertrend_state")
_body = ast.get_source_segment(src, _fn) or ""

# ═══ سلسلة التوثيق تُحذف قبل المطابقة ═══
#
# سقط هذا الفحص لأنّ سلسلة توثيق ``supertrend_state`` تشرح **لماذا
# لا نقرأ** من ``iloc[-1]`` — فوجد الفحصُ العبارة في الشرح وأعلن
# العطب موجوداً، والكود سليم.
#
# وهو الخطأ نفسه الذي وقع في ``tests_pes_history`` و‏``tests_ship``
# و‏``tests_docker`` — ثلاث مرّات قبل هذه. والدرس واحد: كل مطابقةٍ
# على نصّ المصدر تُسبق بتجريده من التعليق **والتوثيق**، وإلّا
# فُحص الشرحُ لا الفعل.
_doc = ast.get_docstring(_fn, clean=False)
if _doc:
    _body = _body.replace(_doc, "", 1)
_code = "\n".join(l for l in _body.splitlines()
                  if not l.strip().startswith("#"))
check("  والقصّ صريح في الكود", "[:-1]" in _code)
check("  ولا قراءة من ‎iloc[-1]‎", "iloc[-1]" not in _code)

# وعمر الانقلاب: هبوطٌ ثمّ صعود ⇒ عمرٌ صغير عند الانقلاب
flip = list(np.linspace(160, 110, 90)) + list(np.linspace(110, 150, 12))
sf = supertrend_state(_df(flip))
check("  وعمر الانقلاب يُحسب",
      sf["bars_since_flip"] is not None and sf["bars_since_flip"] >= 0,
      str(sf["bars_since_flip"]))
# اتّجاهٌ طويل ⇒ عمرٌ كبير
check("  والاتّجاه الطويل عمرُه كبير",
      (supertrend_state(_df(_up))["bars_since_flip"] or 0) > 20,
      str(supertrend_state(_df(_up))["bars_since_flip"]))
check("  و‎flipped_up‎ للحديث وحده",
      supertrend_state(_df(_up))["flipped_up"] is False)


# ═══════════ ٣) العائلة لم تكبر ═══════════
p = pes.load_params()
w = p.get("weights") or {}
check("٣ الأوزان مجموعها ١٠٠", abs(sum(w.values()) - 100) < 1e-9,
      str(sum(w.values())))
check("  و‎supertrend‎ عائلته trend", pes.FAMILY.get("supertrend") == "trend")
trend_total = sum(float(v) for k, v in w.items()
                  if pes.FAMILY.get(k) == "trend")
# ═══ الرقم ٢٥ ليس تعسّفاً ═══
#
# هو مجموع العائلة قبل التغيير. وأيُّ ارتفاعٍ فيه يجعل «الاتجاه»
# يصوّت أكثر من الحجم والتقلّب — وهو ما تمنعه القاعدة ١٧.
check("  ومجموع عائلة الاتجاه ٢٥", abs(trend_total - 25.0) < 1e-9,
      str(trend_total))
check("  و‎supertrend‎ له وزن", float(w.get("supertrend", 0)) > 0)
check("  والعائلات ستّ كما كانت", len(set(pes.FAMILY.values())) == 6)


# ═══════════ ٤) لا عدّ مزدوج ═══════════
#
# بقاؤه فحصاً داخل ``daily_trend`` **مع** كونه عاملاً مستقلّاً
# يحسب الشيء نفسه مرّتين — وهو ما يُفسد الدرجة بهدوء.
psrc = (ROOT / "scanner" / "strategies" / "pes.py").read_text(encoding="utf-8")
ptree = ast.parse(psrc)


def _fnsrc(name: str) -> str:
    fn = next(n for n in ast.walk(ptree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    seg = ast.get_source_segment(psrc, fn) or ""
    doc = ast.get_docstring(fn, clean=False)
    if doc:
        seg = seg.replace(doc, "", 1)
    return "\n".join(l for l in seg.splitlines()
                     if not l.strip().startswith("#"))


dt = _fnsrc("_f_daily_trend")
check("٤ ‎daily_trend‎ بلا Supertrend", "supertrend" not in dt.lower())
# والحصص تجمع واحداً — وإلّا فقد العامل جزءاً من وزنه بصمت
_fracs = [float(m) for m in
          __import__("re").findall(r",\s*(0\.\d+)\)", dt)]
check("  وحصصه تجمع ١٫٠",
      _fracs and abs(sum(_fracs) - 1.0) < 1e-9, str((_fracs, sum(_fracs))))

sf_src = _fnsrc("_f_supertrend")
check("  والعامل يقرأ فريم المسح", '"4h"' in sf_src and "scan_tf" in sf_src)
check("  ويقرأ اليوميّ للاتّفاق", '"1d"' in sf_src)
check("  وأكبر حصّة لحداثة الانقلاب", "0.35" in sf_src)
check("  ويعيد تفصيلاً للشاشة", '"supertrend": {' in sf_src)
check("  ويتدرّج إلى ‎_na‎ لا يرمي", "_na(" in sf_src)


# ═══════════ ٥) الطبقة على الشارت ═══════════
seg_df = _df(list(np.linspace(160, 110, 90)) + list(np.linspace(110, 165, 60)))
lay = SL.build(seg_df)
check("٥ الطبقة تُبنى", lay["ok"] is True, lay.get("reason", ""))
check("  ومقاطعها أكثر من واحد (انقلاب)",
      len(lay["segments"]) >= 2, str(len(lay["segments"])))
# ═══ القطع عند الانقلاب ═══
#
# سلسلةٌ واحدة تصل القفزة بخطٍّ مائل عبر الشارت — يُقرأ اتّجاهاً
# حادّاً وهو لا شيء.
check("  وكل مقطع اتّجاهٌ واحد",
      all(s["direction"] in (1, -1) for s in lay["segments"]))
check("  والاتّجاه يتبدّل بين المقاطع",
      all(lay["segments"][i]["direction"] != lay["segments"][i + 1]["direction"]
          for i in range(len(lay["segments"]) - 1)))
_all_pts = [pt for s in lay["segments"] for pt in s["points"]]
check("  ولا NaN في أيّ نقطة",
      all(np.isfinite(pt["value"]) for pt in _all_pts))
check("  والأزمنة أعدادٌ صحيحة",
      all(isinstance(pt["time"], int) for pt in _all_pts))
check("  والخطوط ملوّنة بالاتجاه",
      all((ln["color"] == SL.UP) == (s["direction"] > 0)
          for ln, s in zip(lay["lines"], lay["segments"])))
check("  وطبقتها مستقلّة",
      all(ln["layer"] == "supertrend" for ln in lay["lines"]))
check("  والحالة من الشمعة المغلقة", lay["state"]["usable"] is True)

# والقصّ على نافذة العرض لا يغيّر الحساب — الإحماء قبلها
_mid = int(seg_df.index[100].timestamp())
lay_cut = SL.build(seg_df, since_ts=_mid)
_full_at = {pt["time"]: pt["value"] for s in lay["segments"]
            for pt in s["points"]}
_cut_at = {pt["time"]: pt["value"] for s in lay_cut["segments"]
           for pt in s["points"]}
_common = set(_full_at) & set(_cut_at)
check("  والقصّ لا يغيّر القيم",
      bool(_common) and all(abs(_full_at[t] - _cut_at[t]) < 1e-9
                            for t in _common),
      f"{len(_common)} نقطة مشتركة")
check("  ولا نقطة قبل النافذة",
      all(t >= _mid for t in _cut_at), "")

# وشموعٌ قليلة لا ترمي
check("  والقليل يعيد ok=False",
      SL.build(_df([100, 101, 102]))["ok"] is False)
check("  والفارغ كذلك", SL.build(None)["ok"] is False)


# ═══════════ ٦) الشاشات ═══════════
_tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "symbol.html").read_text(encoding="utf-8")
check("٦ زرّ الطبقة موجود", 'data-layer="supertrend"' in _tpl)

_views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
check("  و‎api_chart‎ يبني الطبقة", "supertrend_layer" in _views)
check("  ويضيف خطوطها", 'payload.setdefault("lines"' in _views)
check("  وفشلها لا يُسقط الصفحة",
      "تعذّر رسم Supertrend" in _views)

_scan = (ROOT / "scanner" / "strategies" / "pes_scan.py").read_text(
    encoding="utf-8")
check("  والمسح يمرّر التفصيل للصفوف", '"supertrend": next(' in _scan)

_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "pes-page.js").read_text(encoding="utf-8")
_jsc = "\n".join(l for l in _js.splitlines()
                 if not l.strip().startswith("//"))
check("  وصفحة PES فيها عمود", "stCell" in _jsc)
check("  ويُستدعى في الصفّ", "stCell(r)" in _jsc)
check("  والعنوان في الرأس", "Supertrend</th>" in _jsc)
# العمر معروض: «صاعد» وحدها لا تميّز البداية من النضج
check("  والعمر معروض", "bars_since_flip" in _jsc)


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
