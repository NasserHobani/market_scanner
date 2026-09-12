# -*- coding: utf-8 -*-
"""اختبارات محوّل Alpaca — بلا شبكة وبلا مفاتيح.

الطبقة الشبكية (``_get``) وحدها هي المستبدَلة؛ كل ما فوقها يُنفَّذ
حقيقياً. فما يُختبر هنا هو المنطق الذي ينكسر فعلاً: تحليل الاستجابة،
حذف الشمعة الجارية، ترقيم الصفحات، تقسيم الدفعات، وكشف التغذية.

    python tests_alpaca.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.adapters import get_adapter
from scanner.adapters.alpaca import (SYMBOLS_PER_REQUEST, AlpacaAdapter,
                                     AlpacaError)
from scanner.adapters.base import MarketAdapter

# ═══ عزل ذاكرة الكون عن قرص المشروع ═══
#
# صار ``usdt_universe`` يحفظ الكون في ``data/universe/``. وبلا عزل
# يكتب الاختبار كوناً من رمزين في **بيانات التشغيل الحقيقية**، ثمّ
# يقرأه المسح فيمسح رمزين ويظنّ أنّه اكتشف السوق. وهذا أسوأ من
# فشل الاختبار: عطبٌ يصنعه الاختبار في الإنتاج.
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402

from scanner import storage as _storage  # noqa: E402

_TMP_DATA = Path(_tempfile.mkdtemp())
_ORIG_DATA_DIR = _storage.DATA_DIR
_storage.DATA_DIR = _TMP_DATA

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


NOW = pd.Timestamp("2026-08-07 20:00", tz="UTC")


def bar(t, o=10.0, h=11.0, low=9.0, c=10.5, v=1000.0):
    return {"t": t, "o": o, "h": h, "l": low, "c": c, "v": v, "n": 5,
            "vw": 10.2}


# ══════════════════════════════ تحليل الشموع

daily = [bar("2026-08-03T04:00:00Z"), bar("2026-08-04T04:00:00Z"),
         bar("2026-08-05T04:00:00Z")]
df = AlpacaAdapter.to_frame(daily, "1d", now=NOW)
check("الشموع تُقرأ", len(df) == 3, len(df))
check("والأعمدة بالعقد الموحّد",
      list(df.columns) == ["open", "high", "low", "close", "volume"],
      list(df.columns))
check("والفهرس زمني بتوقيت UTC",
      isinstance(df.index, pd.DatetimeIndex) and str(df.index.tz) == "UTC")
check("والقيم أرقام عشرية", str(df["close"].dtype) == "float64")
check("ومرتّب تصاعدياً", df.index.is_monotonic_increasing)

# الشمعة الجارية: قاعدة المشروع كلها. شمعة اليوم لم تُغلق بعد.
with_today = daily + [bar("2026-08-07T04:00:00Z")]
df2 = AlpacaAdapter.to_frame(with_today, "1d", now=NOW)
check("الشمعة الجارية تُحذف (لولاه لأعادت الإشارة رسم نفسها)",
      len(df2) == 3, len(df2))

closed_today = AlpacaAdapter.to_frame(
    with_today, "1d", now=pd.Timestamp("2026-08-08 05:00", tz="UTC"))
check("وتُقبل بعد إغلاقها", len(closed_today) == 4, len(closed_today))

# نفس القاعدة على فريم داخل اليوم
hours = [bar("2026-08-07T17:00:00Z"), bar("2026-08-07T18:00:00Z"),
         bar("2026-08-07T19:00:00Z")]
check("على 1h تُحذف الساعة الجارية وحدها",
      len(AlpacaAdapter.to_frame(
          hours, "1h", now=pd.Timestamp("2026-08-07 19:30", tz="UTC"))) == 2)

# مدخلات معطوبة لا تُسقط المسح
check("قائمة فارغة ← إطار فارغ", AlpacaAdapter.to_frame([], "1d").empty)
check("حقول ناقصة ← إطار فارغ",
      AlpacaAdapter.to_frame([{"t": "2026-08-03T04:00:00Z", "c": 1}],
                             "1d").empty)
dupes = [bar("2026-08-03T04:00:00Z", c=10.0),
         bar("2026-08-03T04:00:00Z", c=99.0)]
d = AlpacaAdapter.to_frame(dupes, "1d", now=NOW)
check("التكرار يُحلّ بآخر قيمة", len(d) == 1 and d["close"].iloc[0] == 99.0)

unsorted = [bar("2026-08-05T04:00:00Z"), bar("2026-08-03T04:00:00Z")]
check("الترتيب المقلوب يُصحَّح",
      AlpacaAdapter.to_frame(unsorted, "1d", now=NOW).index.is_monotonic_increasing)


# ══════════════════════════════ الطبقة الشبكية المستبدَلة

class Fake(AlpacaAdapter):
    """يستبدل ``_get`` وحده — كل ما فوقه كود الإنتاج."""

    def __init__(self, pages=None, assets=None, snapshots=None, fail=None,
                 feed="sip"):
        super().__init__(feed=feed)
        self.key, self.secret = "k", "s"
        self.calls: list[tuple[str, dict]] = []
        self._pages = pages or {}
        self._assets = assets or []
        self._snapshots = snapshots or {}
        self._fail = fail
        self.pause = 0

    def _get(self, host, path, params):
        self.calls.append((path, dict(params)))
        if self._fail:
            raise self._fail
        if path == "/v2/assets":
            return self._assets
        if path == "/v2/stocks/snapshots":
            return self._snapshots
        token = params.get("page_token")
        return self._pages.get(token, {"bars": {}, "next_page_token": None})


# ── ترقيم الصفحات ──
pages = {
    None: {"bars": {"AAPL": [bar("2026-08-03T04:00:00Z")]},
           "next_page_token": "p2"},
    "p2": {"bars": {"AAPL": [bar("2026-08-04T04:00:00Z")],
                    "MSFT": [bar("2026-08-04T04:00:00Z")]},
           "next_page_token": None},
}
a = Fake(pages=pages)
out = a.fetch_many(["AAPL", "MSFT"], "1d", limit=100)
check("الصفحة التالية تُتابَع", len(out.get("AAPL", [])) == 2,
      len(out.get("AAPL", [])))
check("ورموز الصفحة الثانية لا تضيع", "MSFT" in out, sorted(out))
check("وطلبان لا أكثر", len(a.calls) == 2, len(a.calls))

# صفحة تعيد الرمز نفسه إلى ما لا نهاية كانت ستعلّق المسح لولا أن
# الشرط على غياب الرمز المميّز لا على تغيّر المحتوى
check("الرمز المميّز الغائب ينهي الحلقة",
      Fake(pages={None: {"bars": {"A": [bar("2026-08-03T04:00:00Z")]}}}
           ).fetch_many(["A"], "1d") is not None)

# ── تقسيم الدفعات ──
many = [f"SYM{i}" for i in range(250)]
b = Fake(pages={None: {"bars": {}, "next_page_token": None}})
b.fetch_many(many, "1d")
check("‏250 رمزاً تُقسم ثلاث دفعات", len(b.calls) == 3, len(b.calls))
sizes = [len(c[1]["symbols"].split(",")) for c in b.calls]
check("ولا دفعة تتجاوز الحدّ", max(sizes) <= SYMBOLS_PER_REQUEST, sizes)
check("ولا رمز يضيع بين الدفعات", sum(sizes) == 250, sum(sizes))

# ── الوسائط المرسلة ──
p = b.calls[0][1]
check("تعديل التجزئة مطلوب (بدونه تبدو التجزئة انهياراً)",
      p.get("adjustment") == "split", p.get("adjustment"))
check("والفريم يُترجم إلى صيغة Alpaca", p.get("timeframe") == "1Day",
      p.get("timeframe"))
check("والترتيب تصاعدي", p.get("sort") == "asc")
check("والتغذية مذكورة صراحةً", p.get("feed") == "sip")
check("وتاريخ البداية موجود", bool(p.get("start")))

hourly = Fake(pages={None: {"bars": {}}})
hourly.fetch_many(["A"], "1h")
check("‏1h ← 1Hour", hourly.calls[0][1]["timeframe"] == "1Hour")
q = Fake(pages={None: {"bars": {}}})
q.fetch_many(["A"], "15m")
check("‏15m ← 15Min", q.calls[0][1]["timeframe"] == "15Min")

try:
    Fake().fetch_many(["A"], "3h")
    check("فريم غير مدعوم يرفع خطأ مفهوماً", False)
except AlpacaError as exc:
    check("فريم غير مدعوم يرفع خطأ مفهوماً", "3h" in str(exc))

# نافذة البداية تتّسع مع الفريم البطيء لا تنكمش
long_start = AlpacaAdapter._start_for("1d", 1200)
short_start = AlpacaAdapter._start_for("15m", 1200)
check("نافذة 1d أقدم من نافذة 15m", long_start < short_start,
      f"{long_start[:10]} vs {short_start[:10]}")
check("ولا تسبق 2016 (بداية أرشيف Alpaca)",
      AlpacaAdapter._start_for("1d", 100000) >= "2016-01-01")

# ── fetch المفرد يحترم العقد ──
one = Fake(pages={None: {"bars": {"AAPL": daily}, "next_page_token": None}})
frame = one.fetch("AAPL", "1d", limit=50)
check("‏fetch يعيد الشكل الموحّد",
      list(frame.columns) == ["open", "high", "low", "close", "volume"])
try:
    Fake(pages={None: {"bars": {}}}).fetch("NOPE", "1d")
    check("رمز بلا بيانات يرفع خطأ لا إطاراً فارغاً", False)
except AlpacaError as exc:
    check("رمز بلا بيانات يرفع خطأ لا إطاراً فارغاً", "NOPE" in str(exc))


# ══════════════════════════════ الأصول والاكتشاف

assets = [
    {"symbol": "AAPL", "name": "Apple", "exchange": "NASDAQ",
     "tradable": True, "status": "active"},
    {"symbol": "BRK.B", "name": "Berkshire B", "exchange": "NYSE",
     "tradable": True},
    {"symbol": "DEAD", "name": "Halted", "exchange": "NYSE",
     "tradable": False},
    {"symbol": "PINK", "name": "OTC thing", "exchange": "OTC",
     "tradable": True},
    {"symbol": "SPY", "name": "SPDR", "exchange": "ARCA", "tradable": True},
]
c = Fake(assets=assets)
syms = [a["symbol"] for a in c.assets()]
check("غير القابل للتداول يُستبعد", "DEAD" not in syms, syms)
check("و OTC يُستبعد (تسعير متقطّع وحجم ضجيج)", "PINK" not in syms, syms)
check("والرمز ذو النقطة يُستبعد (بيانات متقطّعة واسم ملف معطوب)",
      "BRK.B" not in syms, syms)
check("والصالح يبقى", set(syms) == {"AAPL", "SPY"}, syms)

# الترشيح بالحجم يعتمد متوسط عشرين يوماً لا يوم الأرباح وحده
AlpacaAdapter._universe_cache = None
big = [bar(f"2026-07-{d:02d}T04:00:00Z", c=100.0, v=1_000_000.0)
       for d in range(1, 21)]
small = [bar(f"2026-07-{d:02d}T04:00:00Z", c=1.0, v=1000.0)
         for d in range(1, 21)]
d2 = Fake(assets=assets,
          pages={None: {"bars": {"AAPL": big, "SPY": small},
                        "next_page_token": None}})
universe = d2.usdt_universe(min_quote_volume=1_000_000)
check("الرمز فوق العتبة يمرّ", universe == ["AAPL"], universe)
check("والأحجام تُحفظ للتصنيف بلا طلب ثانٍ",
      abs(d2.quote_volumes().get("AAPL", 0) - 100_000_000) < 1,
      d2.quote_volumes())
AlpacaAdapter._universe_cache = None


# ══════════════════════════════ اللقطات السعرية

snap = {"snapshots": {
    "AAPL": {"latestTrade": {"p": 210.0}, "prevDailyBar": {"c": 200.0}},
    "MSFT": {"minuteBar": {"c": 400.0}, "prevDailyBar": {"c": 400.0}},
    "BAD": {"prevDailyBar": {"c": 10.0}},
    "ZERO": {"latestTrade": {"p": 5.0}, "prevDailyBar": {"c": 0}},
}}
parsed = AlpacaAdapter.parse_snapshots(snap)
check("السعر يُقرأ من آخر صفقة", parsed["AAPL"]["price"] == 210.0)
check("والتغيّر يُحسب من إغلاق أمس",
      abs(parsed["AAPL"]["change_pct"] - 5.0) < 0.01,
      parsed["AAPL"]["change_pct"])
check("وشمعة الدقيقة بديل عند غياب الصفقة", parsed["MSFT"]["price"] == 400.0)
check("ولقطة بلا سعر تُتخطّى", "BAD" not in parsed, sorted(parsed))
check("وقسمة على صفر لا تُسقط التحليل", "ZERO" not in parsed
      or parsed["ZERO"]["change_pct"] is None)
check("واستجابة فارغة لا تنهار", AlpacaAdapter.parse_snapshots({}) == {})


# ══════════════════════════════ التغذية والمفاتيح

AlpacaAdapter._feed_detected = None
sip_ok = Fake(feed=None, pages={None: {"bars": {"AAPL": daily}}})
check("‏sip تُعتمد حين تُقبل", sip_ok.feed == "sip", sip_ok.feed)
check("وتحذير الجزئية لا يظهر معها",
      sip_ok.feed_notice()["partial"] is False)

AlpacaAdapter._feed_detected = None
denied = Fake(feed=None, fail=AlpacaError("403 subscription required"))
check("الاشتراك المرفوض ينزل إلى iex", denied.feed == "iex", denied.feed)
notice = denied.feed_notice()
check("ويُعلن التحذير", notice["partial"] is True)
check("والتحذير يذكر النسبة صراحةً لا يلمّح", "2.5" in notice["text"],
      notice["text"][:60])
check("ويسمّي المؤشرات المتأثّرة", "RVOL" in notice["text"])

AlpacaAdapter._feed_detected = None
check("والكشف يجري مرة واحدة لا لكل طلب",
      (lambda f: (f.feed, f.feed, len(f.calls)))(
          Fake(feed=None, pages={None: {"bars": {}}}))[2] == 1)
AlpacaAdapter._feed_detected = None

class SnapDenied(Fake):
    """sip مقبول للشموع لكن مرفوض للقطات — حالة الخطة الأساسية."""

    def __init__(self, **kwargs):
        kwargs.setdefault("feed", None)
        super().__init__(**kwargs)

    def _get(self, host, path, params):
        if path == "/v2/stocks/snapshots":
            if params.get("feed") == "sip":
                raise AlpacaError(
                    "403 subscription does not permit querying recent SIP data")
            return self._snapshots
        return super()._get(host, path, params)

AlpacaAdapter._feed_detected = None
AlpacaAdapter._snapshot_feed = None
sd = SnapDenied(
    pages={None: {"bars": {"AAPL": daily}}},
    snapshots={"snapshots": {"AAPL": {"latestTrade": {"p": 100.0},
                                        "prevDailyBar": {"c": 99.0}}}},
)
check("شموع sip + لقطات مرفوضة → feed sip", sd.feed == "sip", sd.feed)
check("لقطات تنزل إلى iex", sd.snapshot_feed() == "iex", sd.snapshot_feed())
got = sd.quotes(["AAPL"])
check("الأسعار لا تبقى فارغة", "AAPL" in got, got)
check("لقطات الأسعار على iex", sd.snapshot_feed() == "iex", sd.snapshot_feed())
AlpacaAdapter._snapshot_feed = None

bare = AlpacaAdapter()
bare.key, bare.secret = "", ""
try:
    bare._headers()
    check("غياب المفاتيح يعطي إرشاداً لا أثر استثناء", False)
except AlpacaError as exc:
    check("غياب المفاتيح يعطي إرشاداً لا أثر استثناء",
          ".env" in str(exc) and "ALPACA_API_KEY_ID" in str(exc))


# ══════════════════════════════ الحساب الورقي مقابل الحقيقي
#
# العطب الذي ظهر في أول تشغيل حقيقي: مفتاح ورقي (‏PK…) على مضيف
# الحساب الحقيقي يُرفض بـ 401. وكان محيّراً لأن بيانات السوق تصل
# (مضيفها واحد للحسابين) بينما /v2/assets وحده يفشل.

import os as _os
from scanner.adapters.alpaca import PAPER_HOST, TRADING_HOST


def with_env(**env):
    saved = {k: _os.environ.get(k) for k in
             ("ALPACA_ENDPOINT", "ALPACA_PAPER")}
    for k in saved:
        _os.environ.pop(k, None)
    _os.environ.update({k: v for k, v in env.items() if v is not None})
    return saved


def restore(saved):
    for k, v in saved.items():
        _os.environ.pop(k, None)
        if v is not None:
            _os.environ[k] = v


saved = with_env()
paper = AlpacaAdapter()
paper.key = "PKYMEOD7S324MYVWKZU"
check("مفتاح PK ← مضيف الحساب الورقي",
      paper.trading_host() == PAPER_HOST, paper.trading_host())
live = AlpacaAdapter()
live.key = "AKFAKEFAKEFAKEFAKE"
check("ومفتاح AK ← مضيف الحساب الحقيقي",
      live.trading_host() == TRADING_HOST, live.trading_host())
blank = AlpacaAdapter()
blank.key = ""
check("وبلا مفتاح لا ينهار الاختيار",
      blank.trading_host() in (PAPER_HOST, TRADING_HOST))
restore(saved)

saved = with_env(ALPACA_PAPER="1")
forced = AlpacaAdapter()
forced.key = "AKLOOKSLIKELIVE"
check("‏ALPACA_PAPER=1 يغلب البادئة", forced.trading_host() == PAPER_HOST)
restore(saved)

saved = with_env(ALPACA_PAPER="0")
forced = AlpacaAdapter()
forced.key = "PKLOOKSLIKEPAPER"
check("‏ALPACA_PAPER=0 يغلبها أيضاً", forced.trading_host() == TRADING_HOST)
restore(saved)

# ما يُلصق من اللوحة ينتهي بـ /v2 — قبوله كما هو يوفّر خطأً صامتاً
saved = with_env(ALPACA_ENDPOINT="https://paper-api.alpaca.markets/v2")
pasted = AlpacaAdapter()
pasted.key = "AKANY"
check("العنوان المنسوخ من اللوحة يُقبل بلاحقة /v2",
      pasted.trading_host() == PAPER_HOST, pasted.trading_host())
restore(saved)

saved = with_env(ALPACA_ENDPOINT="https://paper-api.alpaca.markets/")
check("والشرطة الأخيرة تُقصّ",
      AlpacaAdapter().trading_host() == PAPER_HOST)
restore(saved)

check("المضيف المقابل معروف للاثنين",
      AlpacaAdapter._other_host(TRADING_HOST) == PAPER_HOST
      and AlpacaAdapter._other_host(PAPER_HOST) == TRADING_HOST)
check("ومضيف البيانات ليس له مقابل (واحد للحسابين)",
      AlpacaAdapter._other_host("https://data.alpaca.markets") is None)


# يُستبدل urlopen وحده، فيُنفَّذ منطق السقوط الحقيقي في ``_get`` لا
# نسخة منه في الاختبار. اختبارٌ يعيد كتابة ما يختبره يمرّ دائماً.
import io
import json as _json
import urllib.error
import urllib.request

_hosts: list[str] = []


def fake_urlopen(req, timeout=None):
    url = req.full_url
    _hosts.append(url.split("/v2")[0])
    if url.startswith(TRADING_HOST):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {},
                                     io.BytesIO(b"unauthorized"))
    body = _json.dumps([{"symbol": "AAPL", "name": "Apple",
                         "exchange": "NASDAQ", "tradable": True}]).encode()

    class R:
        def read(self): return body
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return R()


real_urlopen = urllib.request.urlopen
urllib.request.urlopen = fake_urlopen
try:
    flip = AlpacaAdapter(feed="sip")
    flip.key, flip.secret = "AKLIVELOOKING", "s"   # بادئة تشير للحقيقي
    got = [a["symbol"] for a in flip.assets()]
    check("‏401 على مضيف يجرّب المقابل تلقائياً", got == ["AAPL"], _hosts)
    check("والمحاولة الثانية على المضيف الورقي",
          _hosts[-1] == PAPER_HOST, _hosts)
    check("ولا يعيد المحاولة إلى ما لا نهاية", len(_hosts) == 2, _hosts)

    # والفشل على الاثنين يعطي رسالة إرشادية لا أثر HTTP
    _hosts.clear()
    urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
        urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {},
                               io.BytesIO(b"unauthorized")))
    dead = AlpacaAdapter(feed="sip")
    dead.key, dead.secret = "AKX", "s"
    try:
        dead.assets()
        check("فشل المضيفين يرفع إرشاداً", False)
    except AlpacaError as exc:
        check("فشل المضيفين يرفع إرشاداً",
              "ALPACA_PAPER=1" in str(exc) and "PK" in str(exc))
        check("والرسالة لا تكشف المفتاح", "AKX" not in str(exc))
finally:
    urllib.request.urlopen = real_urlopen

alp_src = (ROOT / "scanner" / "adapters" / "alpaca.py").read_text("utf-8")
check("ورسالة 401 تسمّي سبب الورقي/الحقيقي أولاً",
      "ALPACA_PAPER=1" in alp_src and "PK" in alp_src)
check("و /v2/assets يستعمل المضيف المكتشف لا ثابتاً",
      "self.trading_host(), \"/v2/assets\"" in alp_src)

scan_src = (ROOT / "web" / "dashboard" / "management" / "commands"
            / "scan.py").read_text("utf-8")
check("وفشل الاكتشاف ينزل إلى قائمة الملف بدل صفر نتائج",
      "تعذّر اكتشاف الرموز" in scan_src)


# ══════════════════════════════ طبقة العرض لا تنتظر الشبكة
#
# العطب الذي وقع: ``feed_notice`` كانت تجسّ Alpaca عند كل استدعاء،
# وكانت تُستدعى من عرض اللوحة. فمع مفاتيح خاطئة انتظرت الصفحة ثلاث
# محاولات × 25 ثانية — تعليق يقارب الدقيقة والنصف ثم صفحة فارغة.

AlpacaAdapter._feed_detected = None


class Trap(AlpacaAdapter):
    """يرفع خطأً فور أي نداء شبكة — فيكشف الجسّ غير المقصود."""

    def __init__(self):
        super().__init__()
        self.key, self.secret = "PKX", "s"
        self.hits = 0

    def _get(self, *a, **k):
        self.hits += 1
        raise AssertionError("نداء شبكة من مسار يجب ألّا يلمسها")


trap = Trap()
note = trap.feed_notice()
check("‏feed_notice لا تلمس الشبكة افتراضياً", trap.hits == 0, trap.hits)
check("وتعلن أن التغذية غير محدَّدة بدل التخمين",
      note["known"] is False and note["partial"] is False, note)
check("ولا تُظهر تحذيراً كاذباً قبل أن تعرف",
      "2.5" not in note["text"], note["text"][:50])

trap2 = Trap()
try:
    trap2.feed_notice(probe=True)
except AssertionError:
    pass
check("والجسّ الصريح وحده يسمح بالشبكة", trap2.hits == 1, trap2.hits)

AlpacaAdapter._feed_detected = "iex"
known = Trap().feed_notice()
check("وبعد أن تُعرف التغذية يظهر التحذير بلا شبكة",
      known["known"] and known["partial"] and "2.5" in known["text"])
AlpacaAdapter._feed_detected = None

views_src = (ROOT / "web" / "dashboard" / "views.py").read_text("utf-8")
check("والعرض يستدعيها بـ probe=False صراحةً",
      "feed_notice(probe=False)" in views_src,
      "الافتراض وحده لا يكفي — التصريح يمنع تغييره سهواً")
check("والحالة الفارغة تشخّص بدل أن تصف",
      "_setup_hint" in views_src and "ALPACA_API_KEY_ID" in views_src)
check("والتشخيص محلّي بلا شبكة",
      "from scanner.adapters.alpaca import credentials" in views_src)


# ══════════════════════════════ العقد والتسجيل

check("المحوّل مسجَّل باسمه", isinstance(get_adapter("alpaca"), AlpacaAdapter))
check("ويرث العقد الموحّد", isinstance(get_adapter("alpaca"), MarketAdapter))
for method in ("fetch", "fetch_many", "usdt_universe", "quote_volumes",
               "quotes", "search", "feed_notice"):
    check(f"وفيه {method}", callable(getattr(AlpacaAdapter, method, None)))

cfg_text = (ROOT / "config" / "us.yaml").read_text(encoding="utf-8")
check("وملف السوق يستعمله", "adapter: alpaca" in cfg_text)
check("والاكتشاف التلقائي مفعَّل", "universe: auto" in cfg_text)
check("وعتبة السيولة أعلى بكثير من الكريبتو",
      "min_quote_volume: 20000000" in cfg_text)

# المفاتيح لا تُكتب في المستودع
check("لا مفاتيح مكتوبة في ملف الإعدادات",
      "ALPACA_API_SECRET_KEY=" not in cfg_text.replace(
          "ALPACA_API_SECRET_KEY=...", ""))
gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
check("و .env مستثنى من git", ".env" in gitignore)


# ── التغذية الجزئية تُذكر حيث يُتّخذ القرار ──
#
# «وصل سعر الدخول» تعني في ذهن القارئ أن الشريط طبع هذا السعر. وعلى
# ‏IEX قد لا يكون كذلك، وحالة المرصد لا رجعة فيها. فالمصدر جزء من
# الخبر — تُختبر هنا بلا Django بقراءة المصدر.
import ast as _ast

_mon = Path(__file__).parent / "web" / "dashboard" / "monitor.py"
_mon_src = _mon.read_text(encoding="utf-8")
_mon_code = "\n".join(
    ln for ln in _mon_src.splitlines() if not ln.strip().startswith("#")
)
check("المرصد يقرأ تغذية اللقطات", "snapshot_feed()" in _mon_code)
check("التنبيه يذكر IEX عند التغذية الجزئية",
      "feed_is_partial(" in _mon_code and "IEX" in _mon_code)
check("التحقّق يسجّل تغذيته", "trigger_feed" in _mon_code)
check("التغذية تُحفظ فعلاً في الصف",
      '"trigger_feed"' in _mon_code and "update_fields" in _mon_code)

# الحقل موجود في النموذج وله هجرة — بلا الهجرة يسقط الحفظ وقت التشغيل
_models_src = (Path(__file__).parent / "web" / "dashboard" / "models.py").read_text(
    encoding="utf-8")
check("حقل trigger_feed في النموذج", "trigger_feed = models.CharField" in _models_src)
_migrations = list((Path(__file__).parent / "web" / "dashboard" / "migrations").glob("*.py"))
check("هجرة الحقل موجودة",
      any("trigger_feed" in p.read_text(encoding="utf-8") for p in _migrations))

# و api_quotes يسمّي التغذية بدل «مؤجَّل» المثبَّت الذي يخفي الفرق
_views_src = (Path(__file__).parent / "web" / "dashboard" / "views.py").read_text(
    encoding="utf-8")
_views_code = "\n".join(
    ln for ln in _views_src.splitlines() if not ln.strip().startswith("#")
)
check("واجهة الأسعار تسمّي التغذية", '"feed": feed' in _views_code)
check("وتعلن الجزئية صراحةً", '"partial"' in _views_code)

# التغذية الكاملة لا تُنتج تحذيراً — التحذير الدائم يُهمَل
_ns: dict = {}
_tree = _ast.parse(_mon_src)
for _node in _tree.body:
    if isinstance(_node, _ast.Assign) and getattr(
            _node.targets[0], "id", "") == "PARTIAL_FEEDS":
        _ns["PARTIAL_FEEDS"] = _ast.literal_eval(_node.value)
check("sip ليست تغذية جزئية", "sip" not in _ns.get("PARTIAL_FEEDS", set()))
check("iex تغذية جزئية", "iex" in _ns.get("PARTIAL_FEEDS", set()))

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
