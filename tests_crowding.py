# -*- coding: utf-8 -*-
"""اختبارات الازدحام والبيانات الميتة — Django مُقلَّد، بلا شبكة.

عطبان اكتُشفا بمراجعة الصفقات الخاسرة، وكلاهما يفسد القياس لا التنفيذ:

  • سبع صفقات فُتحت في لحظة واحدة على 15m فخسرت خمس معاً. سبعة رموز
    في سوق واحد ولحظة واحدة ليست سبع عيّنات بل عيّنة واحدة — تتحرّك
    معاً وتُحسم معاً، فيضيق فاصل الثقة زوراً وتبدو النتائج حاسمة وهي
    ضجيج.

  • سبع وخمسون صفقة معلّقة على شموع من 2022 إلى 2025: رموز شُطبت من
    المنصّة، وملفّاتها باقية على القرص، والجلب التراكمي لا يعيد لها
    شيئاً — فيقرأ المحلّل شمعة قديمة على أنها الأحدث.

    python tests_crowding.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

import pandas as pd

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


# ══════════════════════════════════════════ 1) قِدم البيانات

from scanner import storage

STEP = {"15m": "15min", "1h": "h", "4h": "4h"}


def frame(timeframe: str, end, bars: int = 60):
    idx = pd.date_range(end=end, periods=bars, freq=STEP[timeframe], tz="UTC")
    return pd.DataFrame({"open": 1.0, "high": 1.1, "low": 0.9,
                         "close": 1.0, "volume": 10.0}, index=idx)


now_ts = pd.Timestamp(NOW)

fresh = frame("4h", now_ts)
check("شموع محدَّثة ليست قديمة",
      not storage.is_stale(fresh, "4h", now=now_ts))

behind = storage.bars_behind(frame("4h", now_ts - pd.Timedelta("20h")), "4h",
                             now=now_ts)
check("تأخّر خمس شموع يُقاس خمساً", behind is not None and abs(behind - 5) < 0.01,
      behind)
check("وخمس شموع تتجاوز عتبة الثلاث",
      storage.is_stale(frame("4h", now_ts - pd.Timedelta("20h")), "4h",
                       now=now_ts))

# الحالة الحقيقية: رمز مشطوب منذ سنوات
dead = frame("1h", pd.Timestamp("2022-11-28 02:00", tz="UTC"))
check("رمز متوقّف منذ 2022 يُعدّ قديماً",
      storage.is_stale(dead, "1h", now=now_ts))

# القياس بالشموع لا بالساعات — وإلا خُنق الفريم البطيء أو نجا السريع
gap = pd.Timedelta("2h")
check("ساعتان تُسقطان رمز 15m", storage.is_stale(frame("15m", now_ts - gap),
                                                  "15m", now=now_ts))
check("والساعتان نفسها لا تُسقطان رمز 4h",
      not storage.is_stale(frame("4h", now_ts - gap), "4h", now=now_ts))

# لا يُحكم بالقِدم عند تعذّر القياس: إسقاط رمز صالح أسوأ من فحص قديم
check("بلا شموع لا حكم", not storage.is_stale(None, "4h", now=now_ts))
check("بإطار فارغ لا حكم",
      not storage.is_stale(pd.DataFrame(), "4h", now=now_ts))
check("بفريم مجهول لا حكم",
      not storage.is_stale(fresh, "فريم-غريب", now=now_ts))
check("و bars_behind تعيد None لا صفراً عند التعذّر",
      storage.bars_behind(None, "4h", now=now_ts) is None)

# شمعة في المستقبل (ساعة الجهاز متأخرة) يجب ألّا تعطي رقماً سالباً
ahead = storage.bars_behind(frame("4h", now_ts + pd.Timedelta("8h")), "4h",
                            now=now_ts)
check("شمعة في المستقبل تُقرأ صفراً لا سالباً", ahead == 0, ahead)


# ══════════════════════════════════════════ 2) إلغاء الصفقات الميتة

class FakeTrade:
    _rows: list = []

    def __init__(self, **kw):
        d = dict(symbol="X", market="crypto", timeframe="4h", status="pending",
                 candle_time=NOW - timedelta(hours=8), resolution_note="",
                 saved=[])
        d.update(kw)
        for k, v in d.items():
            setattr(self, k, v)
        self.saved = []

    def save(self, update_fields=None):
        self.saved = list(update_fields or [])

    class objects:
        @staticmethod
        def filter(**kw):
            rows = [r for r in FakeTrade._rows
                    if r.status in kw.get("status__in", [r.status])]
            return types.SimpleNamespace(__iter__=lambda s: iter(rows),
                                         __len__=lambda s: len(rows))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_mod("dashboard")
_mod("dashboard.models", Trade=FakeTrade)
trades = load("dashboard.trades", ROOT / "web" / "dashboard" / "trades.py")
FakeTrade.objects.filter = staticmethod(
    lambda **kw: [r for r in FakeTrade._rows
                  if r.status in kw.get("status__in", [r.status])])

young = FakeTrade(symbol="FRESH", timeframe="4h",
                  candle_time=NOW - timedelta(hours=8), status="open")
aging = FakeTrade(symbol="AGING", timeframe="4h",           # 50 شمعة
                  candle_time=NOW - timedelta(hours=200), status="open")
ancient = FakeTrade(symbol="TOMOUSDT", timeframe="1h",
                    candle_time=datetime(2023, 11, 20, tzinfo=dt_tz.utc),
                    status="pending")
FakeTrade._rows = [young, aging, ancient]

n = trades.cancel_stale_candles()
check("الصفقة الميتة (2023) تُلغى", n == 1 and ancient.status == "expired", n)
check("وسببها مميَّز عن انقضاء المهلة",
      "بيانات قديمة" in ancient.resolution_note, ancient.resolution_note)
check("الصفقة الطازجة لا تُمسّ", young.status == "open")
# هذا ما أسقطته اختبارات الحسم حين كانت العتبة عشر شموع ثابتة:
# صفقة 4h تبقى مئة شمعة بحكم MAX_HOLD_BARS وهي سليمة تماماً
check("والصفقة التي شاخت شيخوخة مشروعة (50 شمعة) لا تُلغى",
      aging.status == "open",
      "العتبة يجب أن تُشتقّ من MAX_HOLD_BARS لا أن تكون رقماً ثابتاً")
check("العتبة مضاعف لأقصى مدة احتفاظ لا رقم مطلق",
      trades.MAX_HOLD_BARS["4h"] * trades.STALE_MULTIPLE > 100)

FakeTrade._rows = []
check("بلا صفقات حيّة لا عمل", trades.cancel_stale_candles() == 0)

# ── المكبح: العتبة الخاطئة تظهر في الحجم لا في النوع ──
#
# الحادثة التي أوجبته: عتبة ثابتة (عشر شموع) ألغت 91 صفقة سليمة في
# دورة واحدة على قاعدة حيّة، بينها خمس رابحة بلغت هدفها. لا شيء كان
# يسأل «إلغاء نصف السجلّ دفعةً، أهذا معقول؟».
old = datetime(2020, 1, 1, tzinfo=dt_tz.utc)
FakeTrade._rows = [FakeTrade(symbol=f"S{i}", timeframe="4h",
                             candle_time=old, status="open")
                   for i in range(40)]
check("إلغاء جماعي فوق السقف يُرفض كله",
      trades.cancel_stale_candles() == 0,
      "40 من 40 = 100% > 25%")
check("ولا صفقة تُمسّ عند الرفض",
      all(t.status == "open" for t in FakeTrade._rows))

# نسبة معقولة تمرّ: خمس ميتة من أربعين
FakeTrade._rows = ([FakeTrade(symbol=f"D{i}", timeframe="4h",
                              candle_time=old, status="open")
                    for i in range(5)]
                   + [FakeTrade(symbol=f"L{i}", timeframe="4h",
                                candle_time=NOW - timedelta(hours=8),
                                status="open") for i in range(35)])
check("والنسبة المعقولة تمرّ", trades.cancel_stale_candles() == 5)

# السجلّ الصغير لا تُطبَّق عليه النسبة: صفقتان ميتتان من ثلاث ليست
# إشارة عطب، والمكبح هناك يمنع التنظيف المشروع
FakeTrade._rows = [FakeTrade(symbol=f"T{i}", timeframe="4h",
                             candle_time=old, status="open")
                   for i in range(3)]
check("والسجلّ الصغير يُنظَّف بلا مكبح",
      trades.cancel_stale_candles() == 3)
check("وحدّ السجلّ الصغير معلَن لا سحري",
      trades.MIN_CANCEL_FLOOR > 0 and 0 < trades.MAX_CANCEL_RATIO < 1)

FakeTrade._rows = []


# ══════════════════════════════════════════ 3) حدّ الصفقات المتزامنة

_mod("dashboard.trades", **{k: getattr(trades, k) for k in dir(trades)
                            if not k.startswith("__")})
# ‏django مُقلَّد كوحدة مسطّحة لا حزمة، فالاستيرادات العميقة في أمر
# المسح تحتاج تسجيلاً صريحاً. البديل — تثبيت Django — يحوّل كل اختبار
# في المشروع إلى اختبار تكامل بطيء يحتاج قاعدة بيانات.
sys.modules["django"].__path__ = []
_mod("django.core")
_mod("django.core.management")
_mod("django.core.management.base", BaseCommand=type("BaseCommand", (), {}))
_mod("django.conf", settings=types.SimpleNamespace(
    SCANNER_CONFIG_DIR=ROOT / "config", COMPLIANCE_RULES=None))
_mod("dashboard.models", Trade=FakeTrade, ScanResult=object,
     ScanRun=object, SignalAlert=object, Watch=object)
scan = load("scan_cmd", ROOT / "web" / "dashboard" / "management"
            / "commands" / "scan.py")


class Row:
    def __init__(self, symbol):
        self.symbol = symbol


def reco(grade, conf):
    return {"grade": grade, "confidence": conf}


pool = [(Row("C1"), reco("C", 0.9)), (Row("A1"), reco("A", 0.5)),
        (Row("B1"), reco("B", 0.9)), (Row("A2"), reco("A", 0.8)),
        (Row("B2"), reco("B", 0.1))]

top = scan._best_first(pool, 3)
check("الحدّ يُحترم", len(top) == 3, len(top))
check("والتصنيف يسبق الثقة",
      [r.symbol for r, _ in top] == ["A2", "A1", "B1"],
      [r.symbol for r, _ in top])
check("بلا حدّ (0) يمرّ الجميع", len(scan._best_first(pool, 0)) == 5)
check("حدّ أكبر من العدد لا يحذف شيئاً",
      len(scan._best_first(pool, 99)) == 5)
check("قائمة فارغة لا تنهار", scan._best_first([], 3) == [])
check("توصية بلا تصنيف تُرتَّب أخيراً لا تُسقط النظام",
      scan._best_first([(Row("N"), None), (Row("A"), reco("A", 0.1))],
                       2)[0][0].symbol == "A")

# الترتيب حتمي: رمزان بنفس التصنيف والثقة يجب ألّا يتبادلا المواقع
# بين مسحين، وإلا صار «أفضل ثلاثة» رهن ترتيب وصول الشبكة
tie = [(Row("ZZZ"), reco("A", 0.5)), (Row("AAA"), reco("A", 0.5))]
check("التعادل يُحسم بالاسم لا بترتيب الوصول",
      [r.symbol for r, _ in scan._best_first(tie, 2)] == ["AAA", "ZZZ"])
check("وإعادة الترتيب تعطي النتيجة نفسها",
      scan._best_first(tie, 1)[0][0].symbol
      == scan._best_first(tie[::-1], 1)[0][0].symbol)

hits = [(Row("S1"), {"rvol": 9.0}), (Row("S2"), {"rvol": 40.0}),
        (Row("S3"), {"rvol": 22.0})]
best = scan._best_breakouts(hits, 2)
check("الاختراقات تُرتَّب بشدّة الحجم",
      [r.symbol for r, _ in best] == ["S2", "S3"], [r.symbol for r, _ in best])
check("اختراق بلا rvol لا يُسقط الترتيب",
      len(scan._best_breakouts([(Row("A"), {}), (Row("B"), {"rvol": 3})], 2)) == 2)

check("عتبة قِدم المسح ثلاث شموع", scan.STALE_BARS == 3, scan.STALE_BARS)
check("وللمسح استثناء خاص لا يختلط بالفشل",
      issubclass(scan.StaleData, Exception))


bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad
      else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
