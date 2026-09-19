# -*- coding: utf-8 -*-
"""من الأعلى للأسفل — وأربعة أعطال تجعل الشاشة تلتقط السقوط.

═══ الأوّل: النظر إلى المستقبل ═══

«أغلق فوق المتوسّط» تُقال عن شمعةٍ **أغلقت**. والشمعة الجارية
تتغيّر حتى تُغلق، فقراءتها تعطي إشارةً تظهر وتختفي — اختبارٌ خلفيّ
ممتاز وتطبيقٌ عاجز.

═══ الثاني: الترتيب بلا ميل ═══

``EMA20 > EMA50`` تبقى صحيحة أسابيع بعد أن يلتفت الاتجاه. فاتّجاهٌ
انعكس للتوّ يمرّ الفحص وهو هابط — وهي صورة القمّة بالضبط. فالميل
شرطٌ ثالث، والثلاثة أو لا شيء.

═══ الثالث: اللمس وحده ═══

«السعر قرب المتوسّط» ليست ارتداداً — قد يكون **نازلاً إليه**.
والفرق بين الارتداد والسقوط أنّه لمس ثمّ **أغلق فوقه** ولم يكسر
القاع السابق. وإسقاط أيّ شرطٍ من الثلاثة يجعل الشاشة تشتري
الهبوط.

═══ الرابع: أسبوعيٌّ مجمَّع خطأً ═══

الأسبوعيّ يُبنى من اليوميّ بإعادة تجميع. وخطأٌ في القاعدة يعطي
شمعاتٍ تبدو سليمة وقيمُها لأسابيع أخرى — ولا شيء يقول ذلك.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.strategies import topdown as TD  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def _df(closes, *, freq="1D", start="2023-01-02", lows=None) -> pd.DataFrame:
    c = np.asarray(closes, dtype=float)
    lo = np.asarray(lows, dtype=float) if lows is not None else c * 0.99
    idx = pd.date_range(start, periods=len(c), freq=freq, tz="UTC")
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": lo,
                         "close": c, "volume": np.full(len(c), 1e6)},
                        index=idx)


PARAMS = {"topdown": {"max_ext_weekly_pct": 25.0, "max_ext_daily_pct": 12.0,
                      "pullback_lookback": 12, "touch_pct": 1.5}}


# ═══════════ ١) إعادة التجميع إلى الأسبوعيّ ═══════════
_days = _df(np.linspace(100, 200, 140))
_wk = TD.to_weekly(_days)
check("١ الأسبوعيّ أقصر من اليوميّ", 0 < len(_wk) < len(_days),
      f"{len(_wk)} من {len(_days)}")
check("  ونحو سُبع العدد", abs(len(_wk) - len(_days) / 7) <= 2,
      f"{len(_wk)} مقابل {len(_days)/7:.1f}")
# القيم تُجمَّع لا تُؤخذ عيّنة: أعلى الأسبوع = أعلى أيّامه
_first_week_high = float(_days["high"].iloc[:5].max())
check("  والأعلى = أعلى الأيّام",
      float(_wk["high"].iloc[0]) >= _first_week_high * 0.99,
      f"{float(_wk['high'].iloc[0]):.2f} مقابل {_first_week_high:.2f}")
check("  والحجم مجموعٌ لا متوسّط",
      float(_wk["volume"].iloc[0]) > 1e6,
      str(float(_wk["volume"].iloc[0])))
check("  والأعمدة كما هي",
      set(_wk.columns) == {"open", "high", "low", "close", "volume"},
      str(list(_wk.columns)))


# ═══════════ ٢) الانحياز: الثلاثة أو لا شيء ═══════════
up = TD._bias(_df(np.linspace(100, 220, 200)))
check("٢ صعودٌ مطّرد = صاعد", up["bias"] == TD.BIAS_UP, str(up["bias"]))
check("  وفحوصه ثلاثة", len(up["checks"]) == 3)
check("  وكلّها ناجحة", all(c["ok"] for c in up["checks"]))

down = TD._bias(_df(np.linspace(220, 100, 200)))
check("  وهبوطٌ مطّرد = هابط", down["bias"] == TD.BIAS_DOWN, str(down["bias"]))

# ═══ القمّة: الترتيب سليم والميل انعكس ═══
#
# هذا هو الفحص الذي يمنع الشاشة من شراء القمم. صعودٌ طويل ثمّ
# انعكاسٌ قصير: ``EMA20 > EMA50`` ما زالت صحيحة، لكنّ EMA20 نزل.
top = TD._bias(_df(list(np.linspace(100, 200, 180))
                   + list(np.linspace(200, 168, 25))))
check("  والقمّة ليست صاعدة", top["bias"] != TD.BIAS_UP,
      f"{top['bias']} · {[c['ok'] for c in top['checks']]}")
check("  والسبب أنّ الميل انعكس",
      any(not c["ok"] and "يرتفع" in c["name"] for c in top["checks"]),
      str([(c["name"], c["ok"]) for c in top["checks"]]))

check("  وشموعٌ قليلة لا ترمي",
      TD._bias(_df([100, 101, 102]))["bias"] == TD.BIAS_FLAT)


# ═══════════ ٣) الشمعة الجارية تُسقَط ═══════════
_base = list(np.linspace(100, 200, 200))
b_calm = TD._bias(TD._closed(_df(_base)))
b_spike = TD._bias(TD._closed(_df(_base + [60.0])))
check("٣ الشمعة الجارية لا تغيّر الانحياز",
      b_calm["bias"] == b_spike["bias"],
      f"{b_calm['bias']} ← {b_spike['bias']}")

src = (ROOT / "scanner" / "strategies" / "topdown.py").read_text(
    encoding="utf-8")
tree = ast.parse(src)


def _fnsrc(name: str) -> str:
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == name)
    seg = ast.get_source_segment(src, fn) or ""
    doc = ast.get_docstring(fn, clean=False)
    if doc:
        seg = seg.replace(doc, "", 1)
    return "\n".join(l for l in seg.splitlines()
                     if not l.strip().startswith("#"))


an = _fnsrc("analyze")
check("  و‎analyze‎ يقصّ الجارية", "_closed(" in an)
cl = _fnsrc("_closed")
check("  والقصّ ‎iloc[:-1]‎", "iloc[:-1]" in cl)


# ═══════════ ٤) الارتداد لا السقوط ═══════════
#
# صعودٌ ثمّ تصحيحٌ يلمس المتوسّط ثمّ استئناف.
_rise = list(np.linspace(100, 160, 140))
_dip = list(np.linspace(160, 146, 8))
_resume = list(np.linspace(146, 154, 5))
pb = TD._pullback_resume(_df(_rise + _dip + _resume, freq="4h"), PARAMS)
check("٤ الارتداد ثمّ الاستئناف يُلتقَط", pb["ok"] is True,
      pb.get("reason", "") or str([(c["name"], c["ok"])
                                   for c in pb["checks"]]))
check("  ويُذكر من أين ارتدّ", pb["zone"] in ("EMA20", "Supertrend"),
      str(pb["zone"]))
check("  ويُعطى وقفٌ مقترح", pb["stop_hint"] is not None)
# ═══ الوقف تحت الارتداد ═══
#
# وضعُه عند السعر أو فوقه يجعله بلا معنى، وبعيداً جداً يجعل
# الخسارة أكبر من الهدف.
check("  والوقف تحت السعر",
      pb["stop_hint"] < float(_resume[-1]), str(pb["stop_hint"]))
check("  والمخاطرة معقولة",
      pb["risk_pct"] is not None and 0 < pb["risk_pct"] < 40,
      str(pb["risk_pct"]))

# ═══ والسقوط لا يُلتقَط ═══
#
# هبوطٌ مستمرّ: يلمس المتوسّط كل شمعة، لكنّه لا يغلق فوقه ولا
# يستأنف. وهذا الفحص هو الفرق بين شاشةٍ تنفع وشاشةٍ تضرّ.
fall = TD._pullback_resume(
    _df(list(np.linspace(160, 100, 160)), freq="4h"), PARAMS)
check("  والسقوط لا يُلتقَط", fall["ok"] is False, str(fall.get("reason")))
check("  ويُذكر ما سقط", bool(fall.get("reason")))

# وقمّةٌ بلا ارتداد: لم يلمس المنطقة أصلاً
spike = TD._pullback_resume(
    _df(list(np.linspace(100, 150, 150)) + list(np.linspace(150, 190, 12)),
        freq="4h"), PARAMS)
check("  والقمّة بلا ارتداد تُرفَض", spike["ok"] is False,
      str(spike.get("reason")))

pbsrc = _fnsrc("_pullback_resume")
check("  والشروط الأربعة في الكود",
      pbsrc.count('"ok":') >= 4 or pbsrc.count("checks") >= 1)
check("  والبنية شرطٌ صريح", "structure_ok" in pbsrc)
check("  والإغلاق فوق المنطقة شرط", "above_zone" in pbsrc)


# ═══════════ ٥) المراحل ═══════════
#
# رمزٌ كلّ شيءٍ فيه صاعد ومرتدّ ⇒ جاهز. والمراحل تُعلَن مرتّبة
# كي يعرف المستخدم أين سقط — لا «لا يُطابق» وحدها.
d1 = _df(np.linspace(100, 190, 420))
h4 = _df(_rise + _dip + _resume, freq="4h")
res = TD.analyze({"1d": d1, "4h": h4}, params=PARAMS)
check("٥ التحليل يعيد مراحل", len(res.get("stages") or []) == 4,
      str(len(res.get("stages") or [])))
check("  ومفاتيحها معروفة",
      [s["key"] for s in res["stages"]] ==
      ["weekly", "daily", "not_extended", "entry"],
      str([s["key"] for s in res.get("stages", [])]))
check("  و‎stage‎ أوّل ما سقط أو ready",
      res["stage"] in ("ready", "weekly", "daily", "not_extended", "entry"),
      res["stage"])
check("  وسببٌ مكتوب عند السقوط",
      res["ok"] or bool(res["reason"]), res.get("reason", ""))

# هبوطٌ على اليوميّ ⇒ يسقط مبكّراً ولا يصل إلى الدخول
bad = TD.analyze({"1d": _df(np.linspace(200, 100, 420)),
                  "4h": h4}, params=PARAMS)
check("  والهابط يسقط قبل الدخول",
      bad["ok"] is False and bad["stage"] in ("weekly", "daily"),
      bad["stage"])

# ═══ الممتدّ يُستبعَد ═══
#
# «مكمل بالصعود» لا تعني «ارتفع كثيراً». والفلتر هنا هو ما يمنع
# الشاشة من أن تصير قائمة الأكثر ارتفاعاً.
far = TD.analyze({"1d": _df(list(np.linspace(100, 160, 380))
                            + list(np.linspace(160, 260, 40))),
                  "4h": h4},
                 params={"topdown": {**PARAMS["topdown"],
                                     "max_ext_daily_pct": 3.0}})
check("  والممتدّ يُستبعَد",
      far["stage"] == "not_extended" or far["extended"] is True,
      f"{far['stage']} · ext={far.get('ext_daily_pct')}")

check("  وشموع قليلة تُعلَن لا ترمي",
      TD.analyze({"1d": _df([100] * 10), "4h": h4},
                 params=PARAMS)["ok"] is False)


# ═══════════ ٦) الماسح والشاشة ═══════════
_scan = (ROOT / "scanner" / "strategies" / "topdown_scan.py").read_text(
    encoding="utf-8")
_sc = "\n".join(l for l in _scan.splitlines()
                if not l.strip().startswith("#"))
check("٦ الماسح يحفظ المستبعَد أيضاً", "by_stage" in _sc)
# الترتيب: الجاهز أوّلاً ثمّ الأقلّ مخاطرة — لا الأبجديّ
check("  ويرتّب بالمخاطرة", "risk_pct" in _sc and "rows.sort" in _sc)
check("  ويحترم قائمة الحظر", "blocklist" in _sc)
check("  ويكتب ملفّاً للسوق", "cache_path" in _sc and "write_text" in _sc)

_v = (ROOT / "web" / "dashboard" / "topdown_views.py").read_text(
    encoding="utf-8")
check("  والشاشة تقرأ ولا تحسب",
      "topdown_scan.load" in _v and "topdown.analyze" not in _v)

_urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for _p in ("topdown/", "api/topdown/", "api/topdown/refresh/"):
    check(f"  والمسار {_p}", f'"{_p}"' in _urls)

_cp = (ROOT / "web" / "dashboard" / "context_processors.py").read_text(
    encoding="utf-8")
check("  والرابط في القائمة", '"/topdown/"' in _cp)

_cron = (ROOT / "web" / "dashboard" / "cron.py").read_text(encoding="utf-8")
_cc = "\n".join(l for l in _cron.splitlines()
                if not l.strip().startswith("#"))
check("  والمهمّة مسجّلة", '"topdown": _h_topdown' in _cc)
check("  ولها اسمٌ معروض", '"topdown": "المسح من الأعلى للأسفل"' in _cc)
# ═══ أربع ساعات لا ساعة ═══
#
# الجدول مُشبَع أصلاً، والأسبوعيّ يتغيّر مرّةً في الأسبوع.
check("  وفترتها ٤ ساعات",
      '"code": "topdown"' in _cc and '"interval_number": 4' in
      _cc.split('"code": "topdown"')[1][:200],
      _cc.split('"code": "topdown"')[1][:120] if '"code": "topdown"' in _cc
      else "غائبة")

_tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
        / "topdown.html").read_text(encoding="utf-8")
check("  والقالب موجود", "td-body" in _tpl)
# التصريح بأنّها غير مقيسة — أصدق من تركه يُفهَم ضمناً
check("  ويُصرّح أنّها لم تُقَس", "لم تُقَس" in _tpl)

_js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
       / "topdown-page.js").read_text(encoding="utf-8")
check("  وصفحتها تعرض المخاطرة", "risk_pct" in _js)
check("  وتعرض أين سقط", "stage_label" in _js)
check("  وتعرض الانحيازين", "weekly_bias" in _js and "daily_bias" in _js)


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name
          + (f"   [{extra}]" if extra and not ok else ""))
bad_list = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad_list)}/{len(results)} "
      + ("✓" if not bad_list else "✗ فشل: " + " · ".join(bad_list[:5])))
sys.exit(1 if bad_list else 0)
