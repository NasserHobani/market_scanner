# -*- coding: utf-8 -*-
"""تسلسل JSON وأنواع numpy — الرسالة التي تكذب عليك.

═══ العطب ═══

انهار ``/api/btc/refresh/`` بـ::

    TypeError: Object of type bool is not JSON serializable
    when serializing dict item 'beats_baseline'

و``bool`` من أبسط ما يُرمَّز في JSON. فالرسالة تبدو مستحيلة.

والقيمة لم تكن ``bool`` بل ``numpy.bool_``: في NumPy 2 صار
``np.bool_.__name__`` يساوي ``"bool"`` حرفيّاً، و``json`` يبني
رسالته من ``__class__.__name__``. فالمكتبة صادقة والاسم كاذب.

ومصدره سطر بريء: ``lo > best`` بين عددَي ``np.float64``. مقارنة
numpy لا تعيد ``bool``. والقيمة تعبر الطبقات كلّها بلا شكوى —
``if`` يعمل، والطباعة تعمل، و``assert`` يعمل — حتى حدّ التسلسل.

═══ لماذا يُختبر الطرفان ═══

أُصلح المصدر (``btc/direction.py``) والحدّ (``jsonsafe``). واختبار
المصدر وحده لا يكفي: أي ``mean()`` جديدة تُعيد العطب في مكان آخر.
واختبار الحدّ وحده لا يكفي: شبكة الأمان تُخفي أن البيانات وسخة.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

results: list[tuple[bool, str, str]] = []
notes: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── ١) العطب حقيقيّ: numpy تُنتجه من مقارنة بريئة ──
_lo, _best = np.float64(0.55), np.float64(0.50)
_verdict = _lo > _best
check("١ مقارنة numpy لا تعيد bool أصيلاً",
      type(_verdict) is not bool, type(_verdict).__name__)
check("  واسمها يقول bool فيضلّل",
      type(_verdict).__name__ == "bool", type(_verdict).__name__)
try:
    json.dumps({"beats_baseline": _verdict})
    _raised = ""
except TypeError as exc:
    _raised = str(exc)
check("  و json يرفضها", bool(_raised), "لم تُرفَض!")
check("  برسالة تذكر bool", "bool" in _raised, _raised[:90])


# ── ٢) المصدر نظيف بلا شبكة أمان ──
#
# يُرمَّز بمرمِّز المكتبة القياسي عمداً: إن مرّ فالبيانات نفسها
# سليمة، لا أنّ أحداً أنقذها عند الخروج.
from scanner.btc import direction  # noqa: E402

rng = np.random.default_rng(0)
_n = 900
_x = rng.normal(0, 1, (_n, 3))
_y = (rng.random(_n) > 0.5).astype("float64")
res = direction.walk_forward(_x, _y, min_train=400, step=100, seed=1)

for _f, _t in (("accuracy", float), ("edge", float), ("ci_low", float),
               ("ci_high", float), ("n_test", int),
               ("beats_baseline", bool)):
    _v = getattr(res, _f)
    check(f"٢ {_f} نوعه {_t.__name__} أصيل", type(_v) is _t,
          type(_v).__name__)

import pandas as pd  # noqa: E402

from scanner.btc import report as btc_report  # noqa: E402

# إطار شموع حقيقيّ الشكل — ``direction_report`` يبني خصائصه بنفسه.
_bars = 1200
_idx = pd.date_range("2024-01-01", periods=_bars, freq="4h", tz="UTC")
_close = 30000 * np.exp(np.cumsum(rng.normal(0, 0.01, _bars)))
_df = pd.DataFrame({
    "open": _close * (1 + rng.normal(0, 0.001, _bars)),
    "high": _close * (1 + abs(rng.normal(0, 0.004, _bars))),
    "low": _close * (1 - abs(rng.normal(0, 0.004, _bars))),
    "close": _close,
    "volume": abs(rng.normal(1e6, 2e5, _bars)),
}, index=_idx)
rep = btc_report.direction_report(_df, min_train=400, step=100)
try:
    json.dumps(rep)          # المرمِّز القياسي — بلا أي شبكة
    _rep_err = ""
except TypeError as exc:
    _rep_err = str(exc)
check("  والتقرير كلّه يُرمَّز بالمرمِّز القياسي", not _rep_err, _rep_err[:110])


# ── ٣) الحدّ يحتمل ما يفلت من المصدر ──
#
# Django غير مثبَّت في كل بيئة. والمنطق المفحوص هنا هو ``default()``
# — وهو منطقنا نحن لا منطق Django. فيُركَّب بديل صغير عند غيابه كي
# **يُفحص المنطق فعلاً** بدل أن يُتخطّى الفحص ويُظنّ ناجحاً.
if "django" not in sys.modules:
    try:
        import django  # noqa: F401
    except ModuleNotFoundError:
        _dj = types.ModuleType("django")
        _core = types.ModuleType("django.core")
        _ser = types.ModuleType("django.core.serializers")
        _sjson = types.ModuleType("django.core.serializers.json")
        _http = types.ModuleType("django.http")

        class _Enc(json.JSONEncoder):
            pass

        class _Resp:
            def __init__(self, data, encoder=None, safe=True,
                         json_dumps_params=None, **kw):
                self.content = json.dumps(
                    data, cls=encoder, **(json_dumps_params or {}))

        _sjson.DjangoJSONEncoder = _Enc
        _http.JsonResponse = _Resp
        _ser.json = _sjson
        _core.serializers = _ser
        _dj.core = _core
        _dj.http = _http
        for _name, _mod in (("django", _dj), ("django.core", _core),
                            ("django.core.serializers", _ser),
                            ("django.core.serializers.json", _sjson),
                            ("django.http", _http)):
            sys.modules[_name] = _mod
        notes.append("Django غير مثبَّت — فُحص منطق المرمِّز ببديل صغير")

sys.path.insert(0, str(ROOT / "web"))
sys.modules.setdefault("dashboard", types.ModuleType("dashboard"))
sys.modules["dashboard"].__path__ = [str(ROOT / "web" / "dashboard")]
from dashboard.jsonsafe import SafeJSONEncoder, dumps, sanitize  # noqa: E402

CASES = [
    ("np.bool_", np.bool_(True), True),
    ("np.float64", np.float64(1.5), 1.5),
    ("np.int64", np.int64(7), 7),
    ("np.float32", np.float32(0.5), 0.5),
    ("مصفوفة", np.array([1, 2, 3]), [1, 2, 3]),
    ("مصفوفة ثنائية", np.array([[1, 2]]), [[1, 2]]),
    ("مجموعة", {"ب", "أ"}, ["أ", "ب"]),
]
for label, value, expected in CASES:
    try:
        got = json.loads(json.dumps({"v": value}, cls=SafeJSONEncoder))["v"]
        check(f"٣ يحتمل {label}", got == expected, f"{got!r} ≠ {expected!r}")
    except TypeError as exc:
        check(f"٣ يحتمل {label}", False, str(exc)[:80])

# NaN و Infinity: صالحان في Python وغير صالحين في JSON — يكسران
# ``JSON.parse`` في المتصفّح لا في السجلّ، فالعطب يظهر بعيداً عن سببه.
#
# و``np.float64`` يرث من ``float`` فلا يستدعي ``default()`` أصلاً —
# أي أنّ حارس المرمِّز لا يراه. لذلك يقع التطهير **قبل** الترميز.
for label, value in (("NaN", np.float64("nan")),
                     ("Infinity", np.float64("inf")),
                     ("-Infinity", np.float64("-inf")),
                     ("NaN من Python", float("nan"))):
    txt = dumps({"v": value})
    check(f"  و{label} يصير null", txt == '{"v": null}', txt)

_arr = dumps({"v": np.array([1.0, np.nan, 3.0])})
check("  و NaN داخل مصفوفة كذلك", _arr == '{"v": [1.0, null, 3.0]}', _arr)
_deep = dumps({"a": [{"b": (1.0, float("inf"))}]})
check("  ومهما غاص في البنية", _deep == '{"a": [{"b": [1.0, null]}]}', _deep)

# التطهير لا ينسخ ما لم يتغيّر: الاستجابة الشائعة بلا NaN، ونسخ
# آلاف الشموع في كل طلب ثمنٌ لا مبرّر له.
_clean_payload = {"candles": [[1, 2.0, 3.0] for _ in range(2000)]}
check("  ولا يُنسخ ما لم يتغيّر",
      sanitize(_clean_payload) is _clean_payload)

import time as _time  # noqa: E402

_t0 = _time.perf_counter()
for _ in range(20):
    sanitize(_clean_payload)
_ms = (_time.perf_counter() - _t0) * 1000 / 20
check(f"  وكلفة المرور ضئيلة ({_ms:.2f}ms لـ 6000 قيمة)", _ms < 5.0,
      f"{_ms:.2f}ms")


# ── ٤) والاستجابات كلّها تمرّ من الحدّ ──
#
# مرمِّزٌ آمن لا يستعمله أحد ليس علاجاً.
stragglers = []
for p in sorted((ROOT / "web").rglob("*.py")):
    if p.name == "jsonsafe.py":
        continue
    src = p.read_text(encoding="utf-8", errors="replace")
    if "from django.http import" in src and "JsonResponse" in src:
        for line in src.splitlines():
            ls = line.strip()
            if ls.startswith("from django.http import") and "JsonResponse" in ls:
                stragglers.append(f"{p.name}: {ls}")
check("٤ لا استجابة تتجاوز الحدّ", not stragglers, " · ".join(stragglers))
check("  والحدّ مستعمَل فعلاً",
      sum(1 for p in (ROOT / "web").rglob("*.py")
          if "from .jsonsafe import JsonResponse" in
          p.read_text(encoding="utf-8", errors="replace")) >= 10)


for n in notes:
    print(f"⊘ {n}")
failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
