# -*- coding: utf-8 -*-
"""محوّل سهمك — السوق السعودي، بلا شبكة.

المرجع: https://www.sahmk.sa/developers/docs

═══ ما تحرسه ═══

  ١. **الفريم المفقود يُرفَض ولا يُستبدَل.** سهمك أصغر فريم لديها 30m،
     والمنصّة تعرض 15m. وإعطاء شموع ساعة لمن طلب ربع ساعة يُنتج
     إشارات على زمن غير الذي ظنّه — خطأ صامت أسوأ من رسالة واضحة.

  ٢. **التاريخ المخزَّن لا يُهجَر.** ملفّاتك تحت ``2222.SR`` وسهمك
     تستعمل ``2222``. وبلا مطابقة يصير كل ما جُمع يتيماً.

  ٣. **الشمعة الناقصة لا تدخل.** التجميع من 60m إلى 4h يُنتج شمعة
     أخيرة «مفتوحة» تتغيّر بعد قليل — والقرار عليها إعادة رسم.

  ٤. **الخطأ يقول ما يُفعَل.** «403» وحدها لا تفرّق بين مفتاح خاطئ
     وباقة لا تكفي، وعلاجهما مختلف تماماً.
"""
from __future__ import annotations

import sys
import urllib.error
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from scanner.adapters.sahmk import (  # noqa: E402
    TIMEFRAME, SahmkAdapter, SahmkError, api_symbol,
)

# ═══ عزل ذاكرة الكون عن قرص المشروع ═══
#
# صار ``usdt_universe`` يحفظ الكون في ``data/universe/`` ويقرأه
# قبل الشبكة. وبلا عزل يقع أمران: تكتب الاختبارات في بيانات
# التشغيل الحقيقية، ويتسرّب كونٌ من قسمٍ إلى قسم فيقرأ الأخير
# رمزين محفوظين بدل أن يبني كونه — وهو ما وقع فعلاً وأسقط أربعة
# فحوص بأرقام لا معنى لها.
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402

from scanner import storage as _storage  # noqa: E402

_TMP_DATA = Path(_tempfile.mkdtemp())
_ORIG_DATA_DIR = _storage.DATA_DIR
_storage.DATA_DIR = _TMP_DATA

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def hourly(n: int, start: str = "2026-03-01 07:00:00") -> list[dict]:
    """صفوف بصيغة سهمك — ساعة بساعة."""
    idx = pd.date_range(start, periods=n, freq="1h", tz="UTC")
    return [{
        "datetime": ts.isoformat(),
        "open": 100.0 + i, "high": 101.0 + i,
        "low": 99.0 + i, "close": 100.5 + i, "volume": 1000 + i,
    } for i, ts in enumerate(idx)]


def daily(n: int) -> list[dict]:
    idx = pd.date_range("2026-01-01", periods=n, freq="1D")
    return [{
        "date": ts.strftime("%Y-%m-%d"),
        "open": 50.0 + i, "high": 52.0 + i,
        "low": 49.0 + i, "close": 51.0 + i, "volume": 5000 + i,
    } for i, ts in enumerate(idx)]


class Fake(SahmkAdapter):
    """محوّل بشبكة مزيّفة — يسجّل ما طُلب."""

    def __init__(self, routes: dict, **kw) -> None:
        super().__init__(api_key="shmk_test_x", **kw)
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []

    def _get(self, path, params=None):  # noqa: ANN001
        self.calls.append((path, dict(params or {})))
        for pattern, value in self.routes.items():
            if pattern in path:
                if isinstance(value, Exception):
                    raise value
                return value(params) if callable(value) else value
        raise SahmkError(f"مسار غير معرَّف في الاختبار: {path}")


# ── ١) مطابقة الرموز ──
check("١ لاحقة ياهو تُجرَّد", api_symbol("2222.SR") == "2222")
check("  والمجرَّد يبقى", api_symbol("1120") == "1120")
check("  والمؤشّر يبقى", api_symbol("tasi") == "TASI")
check("  ولواحق أخرى", api_symbol("7010.TADAWUL") == "7010")
check("  والفارغ لا ينهار", api_symbol("") == "")

# ويصل الرمز المجرَّد إلى الواجهة فعلاً
a = Fake({"/historical/": {"data": daily(300), "has_more": False}})
a.fetch("2222.SR", "1d", 100)
check("  والمسار يحمل المجرَّد", "/historical/2222/" in a.calls[0][0],
      a.calls[0][0])


# ── ٢) الفريم المفقود يُرفَض ──
check("٢ خريطة الفريمات تُعلن 15m مفقوداً", TIMEFRAME["15m"] is None)
try:
    Fake({"/historical/": {"data": hourly(50), "has_more": False}}).fetch(
        "2222", "15m", 10)
    check("  و15m تُرفَض", False, "مرّت بلا خطأ")
except SahmkError as exc:
    check("  و15m تُرفَض", True)
    check("  برسالة تقول البديل", "1h" in str(exc) and "30m" in str(exc),
          str(exc)[:80])

try:
    Fake({}).fetch("2222", "3d", 10)
    check("  والفريم المجهول يُرفَض", False)
except SahmkError:
    check("  والفريم المجهول يُرفَض", True)


# ── ٣) التحويل إلى إطار المنصّة ──
a = Fake({"/historical/": {"data": daily(400), "has_more": False}})
df = a.fetch("2222", "1d", 120)
check("٣ يعيد إطاراً", isinstance(df, pd.DataFrame))
check("  بالعدد المطلوب", len(df) == 120, str(len(df)))
check("  وأعمدة المنصّة",
      list(df.columns) == ["open", "high", "low", "close", "volume"],
      str(list(df.columns)))
check("  وفهرس زمني مرتّب",
      isinstance(df.index, pd.DatetimeIndex) and df.index.is_monotonic_increasing)
check("  بتوقيت UTC", str(df.index.tz) == "UTC", str(df.index.tz))
check("  وقيم عشرية", str(df.dtypes.iloc[0]) == "float64")

# الترتيب المقلوب من المصدر يُصحَّح — لا يُفترض أنه مرتَّب
rev = list(reversed(daily(200)))
df_rev = Fake({"/historical/": {"data": rev, "has_more": False}}).fetch(
    "2222", "1d", 50)
check("  والمصدر المقلوب يُرتَّب", df_rev.index.is_monotonic_increasing)

# التكرار يُزال بإبقاء الأحدث
dup = daily(100) + daily(100)
df_dup = Fake({"/historical/": {"data": dup, "has_more": False}}).fetch(
    "2222", "1d", 200)
check("  والمكرّر يُزال", len(df_dup) == 100, str(len(df_dup)))


# ── ٤) التجميع إلى 4h ──
#
# ‏سهمك لا تعطي 4h، فتُبنى من 60m. والشمعة الأخيرة الناقصة تُحذف.
rows = hourly(4 * 30)            # ثلاثون شمعة أربع ساعات، مكتملة
a4 = Fake({"/historical/": {"data": rows, "has_more": False}})
d4 = a4.fetch("2222", "4h", 20)
check("٤ يجمّع 60m إلى 4h", len(d4) > 0)
check("  ويطلب الفريم الساعي", a4.calls[0][1].get("interval") == "60m",
      str(a4.calls[0][1]))
if len(d4) >= 2:
    gap = d4.index[1] - d4.index[0]
    check("  والمسافة أربع ساعات", gap == pd.Timedelta("4h"), str(gap))

# القيم المجمَّعة صحيحة.
#
# ‏``fetch`` يعيد **ذيل** القائمة لا رأسها، فالمقارنة تكون بنافذة
# المصدر المقابلة لا بالأربع الأولى — وهذا خطأ وقعتُ فيه أوّلاً:
# قارنتُ شمعة مجمَّعة من منتصف المدى بأوّل أربع ساعات.
_all4 = Fake({"/historical/": {"data": rows, "has_more": False}}).fetch(
    "2222", "4h", 999)
_start = _all4.index[0]
_win = [r for r in rows
        if _start <= pd.Timestamp(r["datetime"]) < _start + pd.Timedelta("4h")]
check("  والافتتاح من أوّل ساعة في السلّة",
      abs(_all4.iloc[0]["open"] - _win[0]["open"]) < 1e-9,
      f"{_all4.iloc[0]['open']} مقابل {_win[0]['open']}")
check("  والأعلى أعلى ساعات السلّة",
      abs(_all4.iloc[0]["high"] - max(r["high"] for r in _win)) < 1e-9)
check("  والحجم مجموعها",
      abs(_all4.iloc[0]["volume"] - sum(r["volume"] for r in _win)) < 1e-9)
check("  والسلّة ممتلئة أربع ساعات", len(_win) == 4, str(len(_win)))

# ── الشمعة الناقصة لا تدخل ──
partial = hourly(4 * 10 + 2)     # عشر شموع كاملة + ساعتان
dp = Fake({"/historical/": {"data": partial, "has_more": False}}).fetch(
    "2222", "4h", 50)
last_start = dp.index[-1]
last_src = pd.Timestamp(partial[-1]["datetime"])
check("  والشمعة الناقصة تُستبعَد",
      last_src < last_start + pd.Timedelta("4h") - pd.Timedelta(seconds=1)
      or last_start + pd.Timedelta("4h") <= last_src + pd.Timedelta("1h"),
      f"آخر مجمَّعة {last_start} · آخر مصدر {last_src}")
# الطرفان محذوفان: أوّل سلّة ناقصة (الجلسة تبدأ 07:00 والسلال على
# منتصف الليل) وآخر سلّة جارية.
check("  والسلّة الأولى الناقصة كذلك",
      dp.index[0] >= pd.Timestamp(partial[0]["datetime"]),
      f"{dp.index[0]} مقابل {partial[0]['datetime']}")
_full = [t for t in dp.index
         if sum(1 for r in partial
                if t <= pd.Timestamp(r["datetime"]) < t + pd.Timedelta("4h")) == 4]
check("  فلا قرار على شمعة تتغيّر", len(_full) == len(dp),
      f"{len(_full)} كاملة من {len(dp)}")


# ── ٥) الترقيم ──
pages = {"n": 0}


def paged(params):
    pages["n"] += 1
    off = int(params.get("offset") or 0)
    return {"data": daily(500)[off:off + 500] or daily(500),
            "has_more": pages["n"] < 2}


ap = Fake({"/historical/": paged})
ap.fetch("2222", "1d", 800)
check("٥ يطلب صفحات متتالية", pages["n"] >= 2, str(pages["n"]))
check("  ويمرّر offset", any(c[1].get("offset") for c in ap.calls))
# حدّ الصفحات يمنع دوراناً بلا نهاية إن كذب has_more
loop = Fake({"/historical/": lambda p: {"data": daily(10), "has_more": True}})
loop.fetch("2222", "1d", 5)
check("  وحدّ للصفحات يمنع الدوران", len(loop.calls) <= 13, str(len(loop.calls)))


# ── ٦) الكون ──
companies = {
    "results": [
        {"symbol": "2222", "name_ar": "أرامكو", "market": "TASI",
         "status": "active", "security_type": "Equity", "is_etf": False},
        {"symbol": "1120", "name_ar": "الراجحي", "market": "TASI",
         "status": "active", "security_type": "Equity", "is_etf": False},
        {"symbol": "9999", "name_ar": "صكوك", "market": "TASI",
         "status": "active", "security_type": "Sukuk", "is_etf": False},
        {"symbol": "8888", "name_ar": "صندوق", "market": "TASI",
         "status": "active", "security_type": "Equity", "is_etf": True},
        {"symbol": "7777", "name_ar": "معلَّق", "market": "TASI",
         "status": "suspended", "security_type": "Equity", "is_etf": False},
    ],
    "count": 5,
}
au = Fake({"/companies/": companies,
           "/quotes/": {"results": [
               {"symbol": "2222", "price": 30.0, "volume": 1_000_000},
               {"symbol": "1120", "price": 90.0, "volume": 100_000},
           ]}})
rows = au.companies("TASI")
syms = {r["symbol"] for r in rows}
# الرموز تعود بالصيغة المحلّية ``NNNN.SR`` لا بصيغة المنصّة
# المجرّدة: هي ما على القرص وما يفهمه ياهو. إعادتها خاماً كانت
# ستجعل كل شمعة محفوظة يتيمة.
check("٦ الأسهم النشطة تُقبَل", syms == {"2222.SR", "1120.SR"}, str(syms))
check("  والصكوك تُستبعَد", "9999.SR" not in syms)
check("  والصناديق كذلك", "8888.SR" not in syms)
check("  والمعلَّق كذلك", "7777.SR" not in syms)

SahmkAdapter._universe_cache = None
uni = au.usdt_universe(min_quote_volume=0)
check("  والترتيب بحجم التداول", uni == ["2222.SR", "1120.SR"], str(uni))
SahmkAdapter._universe_cache = None
check("  والعتبة تُطبَّق",
      au.usdt_universe(min_quote_volume=20_000_000) == ["2222.SR"],
      str(au.usdt_universe(min_quote_volume=20_000_000)))
SahmkAdapter._universe_cache = None
check("  و top_n يقصّ", len(au.usdt_universe(0, top_n=1)) == 1)
SahmkAdapter._universe_cache = None


# ── ٧) الأخطاء تقول ما يُفعَل ──
def http_error(code: str, body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError("u", int(code), "e", {}, BytesIO(body))


tr = SahmkAdapter._translate
check("٧ خطأ 401 يذكر المفتاح", "مفتاح" in str(tr(http_error("401"), "/x")))
plan = tr(http_error("403", b'{"code":"PLAN_LIMIT","detail":"60m"}'), "/x")
check("  و403 PLAN_LIMIT يذكر الباقة",
      "Pro" in str(plan) and "PLAN_LIMIT" in str(plan), str(plan)[:90])
check("  و403 عادي لا يخلط بالباقة",
      "Pro" not in str(tr(http_error("403", b'{"detail":"nope"}'), "/x")))
check("  و429 يذكر حدّ الطلبات", "429" in str(tr(http_error("429"), "/x")))
check("  و404 يذكر المسار", "/xyz" in str(tr(http_error("404"), "/xyz")))

# بلا مفتاح: رسالة تقول أين يوضع
import os  # noqa: E402

_saved = os.environ.pop("SAHMK_API_KEY", None)
try:
    SahmkAdapter(api_key="")._headers()
    check("  وبلا مفتاح رسالة واضحة", False, "لم يرفع")
except SahmkError as exc:
    check("  وبلا مفتاح رسالة واضحة",
          "الإعدادات" in str(exc) and "SAHMK_API_KEY" in str(exc))
finally:
    if _saved is not None:
        os.environ["SAHMK_API_KEY"] = _saved


# ── ٨) الحدود ──
try:
    Fake({"/historical/": {"data": [], "has_more": False}}).fetch("X", "1d", 10)
    check("٨ لا بيانات → خطأ واضح", False, "مرّت")
except SahmkError as exc:
    check("٨ لا بيانات → خطأ واضح", "لا بيانات" in str(exc), str(exc)[:60])

bad = [{"date": "ليس تاريخاً", "open": 1, "high": 1, "low": 1, "close": 1}]
try:
    Fake({"/historical/": {"data": bad, "has_more": False}}).fetch("X", "1d", 5)
    check("  والطابع التالف يُرفَض", False, "مرّت")
except SahmkError:
    check("  والطابع التالف يُرفَض", True)

# صفّ بلا طابع يُتخطّى ولا يُسقط الباقي
mixed = daily(60) + [{"open": 1, "high": 1, "low": 1, "close": 1}]
dm = Fake({"/historical/": {"data": mixed, "has_more": False}}).fetch(
    "X", "1d", 100)
check("  والصفّ بلا طابع يُتخطّى", len(dm) == 60, str(len(dm)))


# ── ٩) التسجيل والإعداد ──
from scanner.adapters import ADAPTERS, get_adapter  # noqa: E402

check("٩ المحوّل مسجَّل", "sahmk" in ADAPTERS)
check("  ويُنشأ", type(get_adapter("sahmk")).__name__ == "SahmkAdapter")

import yaml  # noqa: E402

cfg = yaml.safe_load((ROOT / "config" / "saudi.yaml").read_text(encoding="utf-8"))
# سهمك مصدر **الاكتشاف** لا الشموع بالضرورة: ‎/companies/‎ مجاني
# والشموع تحتاج Starter. فالسوق السعودي يكتشف بسهمك ويجلب بياهو.
_uni_ad = cfg.get("universe_adapter") or cfg.get("adapter")
check("  والسوق السعودي يكتشف بسهمك", _uni_ad == "sahmk", str(_uni_ad))
check("  وكونه تلقائي", cfg.get("universe") == "auto")
check("  وبلا سقف يقصّ السوق", cfg.get("top_n") in (None, 0),
      f"top_n={cfg.get('top_n')} — يقصّ السوق قبل أن يُقاس")

# الفريم المضبوط يجب أن يكون متاحاً عند **محوّل الشموع** — وإلّا
# فشل المسح صامتاً. وهو سهمك فقط إن كان هو الجالب.
if cfg.get("adapter") == "sahmk":
    for tf in (cfg.get("timeframes") or []):
        check(f"  والفريم المضبوط {tf} متاح", TIMEFRAME.get(tf) is not None,
              "سهمك لا توفّره")
else:
    _fetcher = cfg.get("adapter")
    check(f"  ومحوّل الشموع «{_fetcher}» مسجَّل", _fetcher in ADAPTERS)
    check("  ولا يُطلب من سهمك ما لا تعطيه",
          all(TIMEFRAME.get(tf) is not None or _fetcher != "sahmk"
              for tf in (cfg.get("timeframes") or [])))

# ── ١٠) فشل الترتيب لا يمحو السوق ──
#
# ‏/companies/‎ مجاني و‎/quotes/‎ يحتاج Starter. وكانا في مسار واحد
# بلا حاجز: الحساب المجاني يجلب الشركات كاملةً ثمّ يفقدها عند سطر
# الترتيب، فيرتدّ النظام إلى عشرة رموز من ملف الإعداد.
from scanner import universe_cache as _uc  # noqa: E402
_uc.path_for("sahmk").unlink(missing_ok=True)

_many = [{"symbol": f"{1000 + i}.SR", "name": f"ش{i}", "market": "TASI"}
         for i in range(287)]


def _mk(quotes_impl):
    # القرص والرام معاً: تركُ أحدهما يجعل الحالة التالية
    # تقرأ كون سابقتها بدل أن تبني كونها.
    SahmkAdapter._universe_cache = None
    _uc.path_for("sahmk").unlink(missing_ok=True)
    a = SahmkAdapter(api_key="x")
    a.companies = lambda market="": _many
    a.quotes = quotes_impl
    return a


def _refuse(_symbols):
    raise SahmkError("403 PLAN_LIMIT: /quotes/ يحتاج Starter")


_free = _mk(_refuse)
_out = _free.usdt_universe(0.0, top_n=None)
check("١٠ رفض /quotes/ لا يُسقط الاكتشاف", len(_out) == 287, str(len(_out)))
check("  ويُعلَن السبب لا يُبتلع",
      "Starter" in _free.last_universe_note, _free.last_universe_note)
check("  والرموز بالصيغة المحلّية", _out[0].endswith(".SR"), _out[0])

# عتبةُ حجمٍ على أحجام غائبة ليست تصفية بل محو.
_free2 = _mk(_refuse)
check("  والعتبة لا تُطبَّق على أحجام غائبة",
      len(_free2.usdt_universe(20_000_000, top_n=None)) == 287)

_paid = _mk(lambda syms: {s: {"price": 10.0, "volume": 1000 * (i + 1)}
                          for i, s in enumerate(syms)})
_ranked = _paid.usdt_universe(0.0, top_n=None)
check("  ومع Starter يُرتَّب بالحجم فعلاً",
      _ranked[0] == "1286.SR" and len(_ranked) == 287, str(_ranked[:2]))
SahmkAdapter._universe_cache = None

_storage.DATA_DIR = _ORIG_DATA_DIR
_shutil.rmtree(_TMP_DATA, ignore_errors=True)

failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
