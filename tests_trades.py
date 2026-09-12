# -*- coding: utf-8 -*-
"""اختبارات طبقة الصفقات (dashboard/trades.py) بـ Django مُقلَّد.

الغرض تشغيلها في أي بيئة بلا تثبيت Django ولا قاعدة بيانات، لأن ما
نختبره هنا منطق ترجمة لا استعلامات: استخراج العوامل، ترشيح الشموع،
وانتقالات الحالة.

    python tests_trades.py
"""
from __future__ import annotations

import sys
import types
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

# ─────────────────────── Django مُقلَّد بالقدر اللازم فقط

NOW = datetime(2026, 8, 8, 12, 0, tzinfo=dt_tz.utc)


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


_mod("django")
_mod("django.db", transaction=types.SimpleNamespace(atomic=_Atomic()))
_mod("django.db.utils", DatabaseError=type("DatabaseError", (Exception,), {}),
     IntegrityError=type("IntegrityError", (Exception,), {}),
     OperationalError=type("OperationalError", (Exception,), {}),
     ProgrammingError=type("ProgrammingError", (Exception,), {}))
_mod("django.utils", timezone=types.SimpleNamespace(now=lambda: NOW))
_mod("django.utils.timezone", now=lambda: NOW)


class _FakeManager:
    def filter(self, **k): return self
    def values_list(self, *a, **k): return []
    def all(self): return []


class _FakeTrade:
    objects = _FakeManager()

    def __init__(self, **kw):
        defaults = dict(
            symbol="BTCUSDT", market="crypto", timeframe="4h", side="buy",
            entry=100.0, stop=90.0, target1=120.0, status="pending",
            candle_time=NOW - timedelta(hours=8), entry_price=None,
            exit_price=None, r_multiple=None, best_r=None, worst_r=None,
            bars_held=0, resolution_note="", closed_at=None, opened_at=None,
            checked_at=None, factors=[], grade="A",
        )
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)
        self.saved_fields: list[str] = []

    def save(self, update_fields=None):
        self.saved_fields = list(update_fields or [])


_mod("dashboard", __path__=[str(ROOT / "web" / "dashboard")])
_mod("dashboard.models", Trade=_FakeTrade)

import importlib.util

spec = importlib.util.spec_from_file_location(
    "dashboard.trades", ROOT / "web" / "dashboard" / "trades.py")
trades = importlib.util.module_from_spec(spec)
sys.modules["dashboard.trades"] = trades
spec.loader.exec_module(trades)

# ─────────────────────── الاختبارات

results: list[tuple[bool, str, str]] = []


def check(name, cond, extra=""):
    results.append((bool(cond), name, str(extra)))


def bar(t, o, h, l, c):
    return {"time": t, "open": o, "high": h, "low": l, "close": c}


SIG = NOW - timedelta(hours=8)
H = timedelta(hours=4)

# ── استخراج العوامل ──
reco = {"breakdown": [
    {"label": "الفريم الأعلى", "value": 0.8},
    {"label": "نماذج الشموع", "value": -0.6},
    {"label": "موجات إليوت", "value": 0.5},
    {"label": "النموذج السعري", "value": 0},
    {"label": "شيء غير معروف", "value": 1.0},
]}
f = trades.extract_factors(reco)
check("العوامل الموجبة فقط تُلتقط", f == ["htf", "elliott"], f)
check("لا عوامل من توصية فارغة", trades.extract_factors(None) == [])
check("قيمة نصّية تالفة لا تُسقط الاستخراج",
      trades.extract_factors({"breakdown": [{"label": "الفريم الأعلى", "value": "x"}]}) == [])

# ── ترشيح الشموع ──
candles = [bar(SIG - H, 1, 1, 1, 1), bar(SIG, 2, 2, 2, 2),
           bar(SIG + H, 3, 3, 3, 3), bar(SIG + 2 * H, 4, 4, 4, 4)]
after = trades._bars_after(candles, SIG)
check("شمعة الإشارة وما قبلها تُستبعد (لا إعادة رسم)",
      len(after) == 2 and after[0]["open"] == 3, len(after))
check("شمعة بلا وقت تُتخطّى",
      len(trades._bars_after([{"open": 1}] + candles, SIG)) == 2)

# ── انتقالات الحالة ──
t = _FakeTrade(status="pending")
changed = trades.resolve_with_candles(t, [bar(SIG + H, 105, 106, 104, 105)])
check("لم يبلغ الدخول ← تبقى منتظِرة",
      t.status == "pending" and changed is False, t.status)

t = _FakeTrade(status="pending")
trades.resolve_with_candles(t, [bar(SIG + H, 102, 103, 99, 101)])
# وقت الدخول = وقت الشمعة لا لحظة الحسم. كان هذا التوكيد يطلب NOW،
# وهو ما جعل كل المدد صفراً — راجع tests_times.py
check("بلغ الدخول ← مفتوحة وسعر التنفيذ ووقت الشمعة محفوظ",
      t.status == "open" and t.entry_price == 100 and t.opened_at == SIG + H,
      f"{t.status} @ {t.entry_price} · {t.opened_at}")

t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW)
trades.resolve_with_candles(t, [bar(SIG + H, 101, 121, 100, 120)])
check("بلغ الهدف ← رابحة +2R ووقت الخروج من الشمعة",
      t.status == "won" and t.r_multiple == 2.0 and t.closed_at == SIG + H,
      f"{t.status} {t.r_multiple} · {t.closed_at}")

t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW)
trades.resolve_with_candles(t, [bar(SIG + H, 99, 100, 89, 90)])
check("ضُرب الوقف ← خاسرة −1R",
      t.status == "lost" and t.r_multiple == -1.0, f"{t.status} {t.r_multiple}")

t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW)
trades.resolve_with_candles(t, [bar(SIG + H, 100, 125, 85, 110)])
check("شمعة تلمس الوقف والهدف ← خسارة مع تعليل",
      t.status == "lost" and "الوقف والهدف" in t.resolution_note,
      t.resolution_note)

# ── الإغلاق القسري بعد أقصى مدة ──
t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW, timeframe="4h")
cap = trades.MAX_HOLD_BARS["4h"]
flat = [bar(SIG + H * (i + 1), 105, 106, 104, 105) for i in range(cap + 5)]
trades.resolve_with_candles(t, flat)
check("صفقة عالقة تُغلق بالسوق بدل أن تبقى خارج الإحصاءات",
      t.status == "won" and "أُغلقت بالسوق" in t.resolution_note,
      f"{t.status} · {t.resolution_note}")

t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW, timeframe="4h")
flat_down = [bar(SIG + H * (i + 1), 95, 96, 94, 95) for i in range(cap + 5)]
trades.resolve_with_candles(t, flat_down)
check("الإغلاق القسري تحت التنفيذ ← خسارة",
      t.status == "lost" and t.r_multiple == -0.5,
      f"{t.status} {t.r_multiple}")

t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW, timeframe="4h")
short = [bar(SIG + H * (i + 1), 105, 106, 104, 105) for i in range(cap - 5)]
trades.resolve_with_candles(t, short)
check("دون الحد الأقصى تبقى مفتوحة", t.status == "open", t.status)

# ── انقضاء مهلة الدخول ──
t = _FakeTrade(status="pending", timeframe="4h")
never = [bar(SIG + H * (i + 1), 200, 205, 199, 200)
         for i in range(trades.ENTRY_DEADLINE_BARS["4h"] + 3)]
trades.resolve_with_candles(t, never)
check("انقضت مهلة الدخول ← لم تُفعَّل", t.status == "expired", t.status)

# ── حفظ الحقول المتغيّرة فقط ──
t = _FakeTrade(status="open", entry_price=100.0, opened_at=NOW)
trades.resolve_with_candles(t, [bar(SIG + H, 101, 121, 100, 120)])
check("الحفظ يقتصر على الحقول المتغيّرة",
      "status" in t.saved_fields and "symbol" not in t.saved_fields,
      str(t.saved_fields))
check("لا تكرار في قائمة الحفظ",
      len(t.saved_fields) == len(set(t.saved_fields)), str(t.saved_fields))

# ── تحويل DataFrame ──
try:
    import pandas as pd

    idx = pd.to_datetime([SIG + H, SIG + 2 * H], utc=True)
    df = pd.DataFrame({"open": [1.0, 2.0], "high": [3.0, 4.0],
                       "low": [0.5, 1.5], "close": [2.0, 3.0],
                       "volume": [10.0, 20.0]}, index=idx)
    c = trades.candles_from_frame(df)
    check("DataFrame ← شموع بأوقات واعية بالمنطقة",
          len(c) == 2 and c[0]["high"] == 3.0 and c[0]["time"].tzinfo is not None,
          str(c[:1]))
    check("جدول فارغ ← لا شموع", trades.candles_from_frame(pd.DataFrame()) == [])
    check("أعمدة ناقصة ← لا شموع",
          trades.candles_from_frame(pd.DataFrame({"open": [1.0]})) == [])
    check("None ← لا شموع", trades.candles_from_frame(None) == [])
except ImportError:
    check("pandas غير متاح — تُخطّى اختبارات التحويل", True)

# ── التقرير ──
rows = trades.rows_for_stats([
    _FakeTrade(status="won", r_multiple=2.0, factors=["htf", "elliott"]),
    _FakeTrade(status="lost", r_multiple=-1.0, factors=[]),
])
check("مفاتيح العوامل تُترجَم للعرض",
      rows[0]["factors"] == ["الفريم الأعلى", "موجات إليوت"], str(rows[0]["factors"]))
check("صفقة بلا عوامل تُعطي قائمة فارغة", rows[1]["factors"] == [])

# ── التقرير النهائي ──
bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
