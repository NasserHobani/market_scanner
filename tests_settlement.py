# -*- coding: utf-8 -*-
"""اختبارات عامل حسم الصفقات — Django مُقلَّد، بلا شبكة.

العطب الذي يعالجه العامل صامت: صفقة على فريم لا يمسحه المسح التلقائي
تبقى «مفتوحة» إلى الأبد فلا تدخل الإحصاءات — والغائب ليس عشوائياً،
فتظهر النتائج أفضل أو أسوأ مما هي.

    python tests_settlement.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=dt_tz.utc)
results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


# ─────────────────── Django مُقلَّد

def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Atomic:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __call__(self, *a, **k): return self


class DBError(Exception): pass
class OpError(DBError): pass
class ProgError(DBError): pass


_mod("django")
_mod("django.db", transaction=types.SimpleNamespace(atomic=_Atomic()))
_mod("django.db.utils", DatabaseError=DBError, IntegrityError=DBError,
     OperationalError=OpError, ProgrammingError=ProgError)
_mod("django.utils", timezone=types.SimpleNamespace(now=lambda: NOW))
_mod("django.utils.timezone", now=lambda: NOW)
_mod("django.conf", settings=types.SimpleNamespace(
    SCANNER_CONFIG_DIR=ROOT / "config"))


class FakeTrade:
    _rows: list = []
    _fail: Exception | None = None

    def __init__(self, **kw):
        d = dict(symbol="BTCUSDT", market="crypto", timeframe="4h", side="buy",
                 entry=100.0, stop=90.0, target1=120.0, status="pending",
                 candle_time=NOW - timedelta(days=3), entry_price=None,
                 exit_price=None, r_multiple=None, best_r=None, worst_r=None,
                 bars_held=0, resolution_note="", closed_at=None,
                 opened_at=None, checked_at=None, factors=[], grade="A")
        d.update(kw)
        for k, v in d.items():
            setattr(self, k, v)
        self.saved = []

    def save(self, update_fields=None):
        self.saved = list(update_fields or [])

    class _QS:
        def __init__(self, rows): self.rows = rows
        def filter(self, **kw):
            if FakeTrade._fail:
                raise FakeTrade._fail
            out = self.rows
            if "status__in" in kw:
                out = [r for r in out if r.status in kw["status__in"]]
            return FakeTrade._QS(out)
        def order_by(self, *a): return list(self.rows)
        def __iter__(self): return iter(self.rows)

    class _Mgr:
        def filter(self, **kw): return FakeTrade._QS(FakeTrade._rows).filter(**kw)
        def all(self): return FakeTrade._QS(FakeTrade._rows)

    objects = _Mgr()


_mod("dashboard", __path__=[str(ROOT / "web" / "dashboard")])
_mod("dashboard.models", Trade=FakeTrade)

_expired = {"n": 0}


def _load(name):
    spec = importlib.util.spec_from_file_location(
        f"dashboard.{name}", ROOT / "web" / "dashboard" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"dashboard.{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


trades = _load("trades")


def fake_expire():
    _expired["n"] += 1
    return 0


trades.expire_stale = fake_expire
settlement = _load("settlement")

# ─────────────────── شموع مصطنعة

import pandas as pd


def frame(n=60, base=100.0, dip=None, rally=None, end=NOW):
    idx = pd.date_range(end=end, periods=n, freq="4h", tz="UTC")
    close = [base] * n
    high = [base * 1.01] * n
    low = [base * 0.99] * n
    if dip is not None:
        low[-1] = dip
        close[-1] = dip
    if rally is not None:
        high[-1] = rally
        close[-1] = rally
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": [1.0] * n}, index=idx)


FETCHED = {"n": 0}


def stub_candles(frames: dict):
    """يستبدل الجلب الشبكي بجدول جاهز لكل رمز."""
    def fake(market, symbol, timeframe):
        FETCHED["n"] += 1
        return frames.get(symbol), True
    settlement._fresh_candles = fake


# ─────────────────── الاختبارات

# ١. الحالة التي دفعت لبناء العامل: فريم غير ممسوح
FakeTrade._rows = [
    FakeTrade(symbol="AAAUSDT", timeframe="1h", status="open", entry_price=100.0),
    FakeTrade(symbol="BBBUSDT", timeframe="4h", status="open", entry_price=100.0),
]
stub_candles({"AAAUSDT": frame(rally=125.0), "BBBUSDT": frame()})
r = settlement.settle_once()
check("يحسم صفقات كل الفريمات لا فريم المسح وحده",
      r["groups"] == 2 and r["settled"] == 1, r)
check("الرابحة صارت رابحة",
      FakeTrade._rows[0].status == "won", FakeTrade._rows[0].status)
check("والتي لم تتحرك تبقى مفتوحة",
      FakeTrade._rows[1].status == "open", FakeTrade._rows[1].status)

# ٢. الوقف
FakeTrade._rows = [FakeTrade(symbol="CCCUSDT", status="open", entry_price=100.0)]
stub_candles({"CCCUSDT": frame(dip=85.0)})
settlement.settle_once()
check("ضرب الوقف يُسجَّل خسارة",
      FakeTrade._rows[0].status == "lost", FakeTrade._rows[0].status)

# ٣. التجميع يمنع تكرار الجلب
FETCHED["n"] = 0
FakeTrade._rows = [
    FakeTrade(symbol="DDDUSDT", timeframe="4h", status="open", entry_price=100.0),
    FakeTrade(symbol="DDDUSDT", timeframe="4h", status="pending"),
]
stub_candles({"DDDUSDT": frame()})
settlement.settle_once()
check("الرمز الواحد يُجلب مرة واحدة لصفقتين",
      FETCHED["n"] == 1, FETCHED["n"])

# ٤. انتهاء الصلاحية يُستدعى
_expired["n"] = 0
FakeTrade._rows = []
settlement.settle_once()
check("انتهاء الصلاحية يُفحص في كل دورة", _expired["n"] == 1, _expired["n"])

# ٥. لا صفقات ← لا عمل
FETCHED["n"] = 0
r = settlement.settle_once()
check("بلا صفقات حيّة لا جلب ولا حسم",
      FETCHED["n"] == 0 and r["checked"] == 0 and r["groups"] == 0, r)

# ٦. جدول مفقود لا يُسقط الخيط
FakeTrade._fail = ProgError("no such table")
r = settlement.settle_once()
check("جدول مفقود يعطي سبباً لا استثناءً",
      r["error"] and "migrate" in r["error"], r["error"])
FakeTrade._fail = None

# ٧. شموع مفقودة تُتخطّى
FakeTrade._rows = [FakeTrade(symbol="EEEUSDT", status="open", entry_price=100.0)]
stub_candles({})
r = settlement.settle_once()
check("رمز بلا شموع يُتخطّى بلا انهيار",
      r["checked"] == 0 and FakeTrade._rows[0].status == "open", r)

# ٨. الحدّ الأقصى للرموز في الدورة
FakeTrade._rows = [FakeTrade(symbol=f"S{i}USDT", status="open", entry_price=100.0)
                   for i in range(10)]
FETCHED["n"] = 0
stub_candles({f"S{i}USDT": frame() for i in range(10)})
settlement.settle_once(max_symbols=4)
check("حدّ الرموز يمنع دورة طويلة تحجب غيرها",
      FETCHED["n"] == 4, FETCHED["n"])

# ٩. الحالة معروضة
st = settlement.status()
check("الحالة تحمل ما تعرضه الصفحة",
      {"running", "thread_started", "settled_total", "last_error"} <= set(st),
      sorted(st))

# ١٠. الدورة من الإعدادات مع حدّ أدنى
check("الدورة الافتراضية معقولة",
      settlement.DEFAULT_INTERVAL >= 60 and settlement.MIN_INTERVAL >= 30)
check("‏_interval يرجع للافتراضي عند تعذّر الإعدادات",
      settlement._interval(123) == 123)

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
