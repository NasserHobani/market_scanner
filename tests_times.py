# -*- coding: utf-8 -*-
"""اختبارات أوقات الصفقة — رصد ودخول وخروج ومدة.

العطب الذي تحرسه: كانت ``opened_at`` و``closed_at`` تُكتب بلحظة تشغيل
الحسم لا بوقت الشمعة. فصفقة نُفّذت قبل ثلاثة أيام وحُسمت الآن تُسجَّل
كأنها فُتحت وأُغلقت في اللحظة نفسها — فتصير كل المدد صفراً، ويعكس
الترتيب الزمني ترتيبَ المعالجة لا ترتيب السوق.

    python tests_times.py
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone as dt_tz
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

PROCESSED_AT = datetime(2026, 8, 8, 20, 0, tzinfo=dt_tz.utc)   # لحظة الحسم
SIGNAL = datetime(2026, 8, 1, 0, 0, tzinfo=dt_tz.utc)          # شمعة الإشارة
H4 = timedelta(hours=4)

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


_mod("django")
_mod("django.db", transaction=types.SimpleNamespace(atomic=_Atomic()))
_mod("django.db.utils", DatabaseError=type("E", (Exception,), {}),
     IntegrityError=type("E", (Exception,), {}),
     OperationalError=type("E", (Exception,), {}),
     ProgrammingError=type("E", (Exception,), {}))
_mod("django.utils", timezone=types.SimpleNamespace(now=lambda: PROCESSED_AT))
_mod("django.utils.timezone", now=lambda: PROCESSED_AT)


class FakeTrade:
    def __init__(self, **kw):
        d = dict(symbol="X", market="crypto", timeframe="4h", side="buy",
                 entry=100.0, stop=90.0, target1=120.0, status="pending",
                 candle_time=SIGNAL, entry_price=None, exit_price=None,
                 r_multiple=None, best_r=None, worst_r=None, bars_held=0,
                 resolution_note="", closed_at=None, opened_at=None,
                 checked_at=None, factors=[], grade="A")
        d.update(kw)
        for k, v in d.items():
            setattr(self, k, v)

    def save(self, update_fields=None):
        pass


_mod("dashboard", __path__=[str(ROOT / "web" / "dashboard")])
_mod("dashboard.models", Trade=FakeTrade)

spec = importlib.util.spec_from_file_location(
    "dashboard.trades", ROOT / "web" / "dashboard" / "trades.py")
trades = importlib.util.module_from_spec(spec)
sys.modules["dashboard.trades"] = trades
spec.loader.exec_module(trades)

# مرشّح العرض
tpl = types.ModuleType("django.template")


class Library:
    def filter(self, name=None, **kw):
        return lambda fn: fn


tpl.Library = Library
sys.modules["django.template"] = tpl
spec = importlib.util.spec_from_file_location(
    "fmt", ROOT / "web" / "dashboard" / "templatetags" / "fmt.py")
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)


def bar(i, o, h, l, c):
    return {"time": SIGNAL + H4 * (i + 1), "open": o, "high": h,
            "low": l, "close": c}


FLAT = lambda i: bar(i, 105, 106, 104, 105)          # noqa: E731
TOUCH = lambda i: bar(i, 102, 103, 99, 101)          # noqa: E731
HIT = lambda i: bar(i, 101, 121, 100, 120)           # noqa: E731
STOPPED = lambda i: bar(i, 99, 100, 89, 90)          # noqa: E731

# ─────────────────── الجوهر: أوقات سوق لا أوقات معالجة

bars = [FLAT(0), FLAT(1), TOUCH(2), FLAT(3), FLAT(4), HIT(5)]
t = FakeTrade()
trades.resolve_with_candles(t, bars)
check("الرابحة تُحسم", t.status == "won", t.status)
check("وقت الدخول = شمعة بلوغ السعر",
      t.opened_at == bars[2]["time"], f"{t.opened_at} ≠ {bars[2]['time']}")
check("وقت الخروج = شمعة ضرب الهدف",
      t.closed_at == bars[5]["time"], f"{t.closed_at} ≠ {bars[5]['time']}")
check("ولا واحد منهما لحظة المعالجة",
      t.opened_at != PROCESSED_AT and t.closed_at != PROCESSED_AT,
      "العطب الأصلي: كلاهما = لحظة تشغيل الحسم")
check("فالمدة حقيقية لا صفر",
      (t.closed_at - t.opened_at) == H4 * 3, t.closed_at - t.opened_at)

# ─────────────────── الوقف
t = FakeTrade()
trades.resolve_with_candles(t, [FLAT(0), TOUCH(1), STOPPED(2)])
check("الخاسرة: الخروج عند شمعة الوقف",
      t.status == "lost" and t.closed_at == SIGNAL + H4 * 3,
      f"{t.status} · {t.closed_at}")

# ─────────────────── المفتوحة
t = FakeTrade()
trades.resolve_with_candles(t, [FLAT(0), TOUCH(1), FLAT(2)])
check("المفتوحة لها وقت دخول بلا وقت خروج",
      t.status == "open" and t.opened_at == SIGNAL + H4 * 2
      and t.closed_at is None, f"{t.status} · {t.opened_at} · {t.closed_at}")

# ─────────────────── المنتظِرة
t = FakeTrade()
trades.resolve_with_candles(t, [FLAT(0), FLAT(1)])
check("المنتظِرة بلا وقت دخول ولا خروج",
      t.status == "pending" and t.opened_at is None and t.closed_at is None,
      f"{t.status} · {t.opened_at}")

# ─────────────────── الصفقة الفورية تحتفظ بوقتها الأصلي
opened = SIGNAL + H4
t = FakeTrade(status="open", entry_price=100.0, opened_at=opened)
trades.resolve_with_candles(t, [FLAT(0), HIT(1)])
check("صفقة مفتوحة سلفاً لا يُعاد كتابة وقت دخولها",
      t.opened_at == opened, t.opened_at)

# ─────────────────── الإغلاق القسري
t = FakeTrade(status="open", entry_price=100.0, opened_at=SIGNAL, timeframe="4h")
cap = trades.MAX_HOLD_BARS["4h"]
long_flat = [FLAT(i) for i in range(cap + 5)]
trades.resolve_with_candles(t, long_flat)
check("الإغلاق القسري بوقت آخر شمعة لا بلحظة المعالجة",
      t.closed_at == long_flat[-1]["time"], f"{t.closed_at}")

# ─────────────────── شموع بلا وقت لا تُسقط الحسم
t = FakeTrade()
notime = [{"open": 102, "high": 103, "low": 99, "close": 101, "time": SIGNAL + H4},
          {"open": 101, "high": 121, "low": 100, "close": 120}]
trades.resolve_with_candles(t, notime)
check("شمعة بلا مفتاح وقت تُتخطّى في الترشيح بلا انهيار",
      t.status in ("open", "won", "pending"), t.status)

check("‏_bar_time لفهرس خارج المدى ← None",
      trades._bar_time([{"time": SIGNAL}], 9) is None)
check("‏_bar_time لـ None ← None", trades._bar_time([], None) is None)

# ─────────────────── مرشّح المدة
c = fmt.span
check("مدة بالدقائق", c(SIGNAL, SIGNAL + timedelta(minutes=45)) == "45د")
check("مدة بالساعات", c(SIGNAL, SIGNAL + timedelta(hours=3, minutes=20)) == "3س 20د")
check("ساعة كاملة بلا دقائق", c(SIGNAL, SIGNAL + timedelta(hours=5)) == "5س")
check("مدة بالأيام", c(SIGNAL, SIGNAL + timedelta(days=2, hours=6)) == "2ي 6س")
check("يوم كامل", c(SIGNAL, SIGNAL + timedelta(days=1)) == "1ي")
check("أقل من دقيقة", c(SIGNAL, SIGNAL + timedelta(seconds=30)) == "أقل من دقيقة")
check("بلا خروج ← شرطة", c(SIGNAL, None) == "—")
check("بلا دخول ← شرطة", c(None, SIGNAL) == "—")
check("ترتيب معكوس ← شرطة", c(SIGNAL + H4, SIGNAL) == "—")
check("نوع خاطئ ← شرطة", c("نص", SIGNAL) == "—")

# ─────────────────── الفتح الفوري: وقت شمعة لا وقت معالجة
#
# العطب الذي ظهر في اللقطة: صفقة اختراق دخلت 16:05 وخرجت 16:00 —
# الدخول بعد الخروج. السبب أن الفتح يستعمل timezone.now() والحسم
# يستعمل وقت الشمعة، فمصدران مختلفان في الصفقة الواحدة.

class Row:
    def __init__(self, candle_time=SIGNAL):
        self.symbol, self.market, self.score = "X", "crypto", 50.0
        self.candle_time = candle_time


made: list = []


class Recorder(FakeTrade):
    @staticmethod
    def _mk(**kw):
        t = FakeTrade(**kw)
        made.append(t)
        return t


class _Mgr:
    def get_or_create(self, **kw):
        d = dict(kw.pop("defaults", {}))
        d.update(kw)
        t = FakeTrade(**d)
        made.append(t)
        return t, True


FakeTrade.objects = _Mgr()

made.clear()
trades.open_from_reco(Row(), {"action": "now", "entry": 100, "stop": 90,
                              "targets": [120], "grade": "A"}, "4h")
check("«شراء الآن» يفتح بوقت شمعة الإشارة لا لحظة المسح",
      made and made[0].opened_at == SIGNAL,
      f"{made[0].opened_at if made else 'لا صفقة'} ≠ {SIGNAL}")
check("ولا يساوي لحظة المعالجة",
      made and made[0].opened_at != PROCESSED_AT)

made.clear()
trades.open_from_reco(Row(), {"action": "pending", "entry": 100, "stop": 90,
                              "targets": [120]}, "4h")
check("«شراء لاحقاً» بلا وقت دخول حتى يُنفَّذ",
      made and made[0].opened_at is None)

made.clear()
trades.open_from_breakout(Row(), {"entry": 100, "stop": 90, "target": 120,
                                  "reasons": []}, "4h")
check("الاختراق أيضاً يفتح بوقت الشمعة",
      made and made[0].opened_at == SIGNAL,
      made[0].opened_at if made else "لا صفقة")

# ─────────────────── الحارس ضدّ الانقلاب
t = FakeTrade(status="open", entry_price=100.0,
              opened_at=PROCESSED_AT)          # وقت معالجة متأخر جداً
trades.resolve_with_candles(t, [FLAT(0), HIT(1)])
check("خروج قبل دخول يُصحَّح لا يُترك سالباً",
      t.opened_at <= t.closed_at,
      f"دخول {t.opened_at} · خروج {t.closed_at}")

# ─────────────────── القالب
TPL = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "performance.html").read_text(encoding="utf-8")
for cell in ("detected", "opened", "closed", "held"):
    check(f"عمود «{cell}» موجود في الجدول", f'data-cell="{cell}"' in TPL)
check("الرصد يعرض شمعة الإشارة لا وقت المسح",
      't.candle_time|date:"m-d H:i"' in TPL)
check("ووقت المسح في التلميح",
      "رُصدت في المسح" in TPL)
check("والصفحة تشرح أنها أوقات سوق",
      "أوقات سوق لا أوقات معالجة" in TPL)
check("وتذكر المنطقة الزمنية المعروضة", "{{ tz_name }}" in TPL)
check("وفيها زرّ إصلاح الأوقات القديمة", 'id="repair-times"' in TPL)

# ─────────────────── التحديث الحيّ لا يعيد الأوقات إلى UTC
#
# العطب: الخادم يرسم بالتوقيت المحلي، ثم JavaScript يقصّ ISO الوارد
# من الـ API — وهو UTC — ويكتبه فوق الخلية بعد عشرين ثانية. فيظهر
# «وقت الرصد» محلياً و«الدخول» بـ UTC، أي الرصد بعد الدخول.
VIEWS = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
api = VIEWS[VIEWS.index("def api_performance"):VIEWS.index("def _local_text")]
check("الـ API لا يرسل ISO خاماً لأوقات الصفقة",
      "opened_at.isoformat()" not in api and "closed_at.isoformat()" not in api,
      "ISO بـ UTC يتجاوز تحويل الخادم")
check("بل نصّاً منسَّقاً بالتوقيت المحلي",
      '"opened": _local_text(' in api and '"closed": _local_text(' in api)
check("‏_local_text يستعمل localtime لا التوقيت الخام",
      "tz.localtime(value)" in VIEWS)
check("والمتصفّح يعرض ما وصله بلا قصّ",
      ".slice(5, 16)" not in TPL and ".slice(0, 16)" not in TPL,
      "القصّ يعني تجاهل تنسيق الخادم")
check("ويستعمل النصّ الكامل للتلميح", 't[key + "_full"]' in TPL)

# ─────────────────── الإعدادات: عرض محلي وتخزين UTC
SET = (ROOT / "web" / "config" / "settings.py").read_text(encoding="utf-8")
check("‏TIME_ZONE لم يعد UTC ثابتاً",
      'TIME_ZONE = os.getenv("SCANNER_TIMEZONE"' in SET)
check("والتخزين يبقى UTC", "USE_TZ = True" in SET)
check("ومنطقة خاطئة لا تُسقط الخادم", "منطقة زمنية غير معروفة" in SET)

# ─────────────────── لا استدعاءات وقت مهجورة
#
# ‏``datetime.utcnow()`` تُعيد وقتاً **بلا منطقة زمنية** يحمل قيمة UTC.
# وهذا مصدر عطب متكرّر في هذا المشروع بالذات: الوقت الساذج يُقارَن
# بوقت واعٍ فيرفع استثناءً، أو — وهو أسوأ — يُفسَّر بالتوقيت المحلّي
# فينزاح ساعات بلا أي علامة. وقد انقلبت أوقات صفقات فعلاً لهذا السبب.
#
# و``pd.Timestamp.utcnow()`` مهجورة في pandas 4 وتطبع تحذيراً في كل
# مسح — والتحذير الذي يتكرّر يُدرَّب المستخدم على تجاهله، فيضيع معه
# التحذير الذي يهمّ.
#
# الفحص يتخطّى التعليقات والسلاسل النصّية بتحليل الشجرة، فلا يُمسك
# شرحاً للعطب القديم كما وقع سابقاً مع فواحص أخرى.
import ast as _ast

_DEPRECATED = {
    ("datetime", "utcnow"): "datetime.now(timezone.utc)",
    ("Timestamp", "utcnow"): 'pd.Timestamp.now("UTC")',
    ("datetime", "utcfromtimestamp"): "datetime.fromtimestamp(ts, timezone.utc)",
}

_offenders: list[str] = []
for _py in sorted(ROOT.rglob("*.py")):
    if "__pycache__" in _py.parts or ".venv" in _py.parts:
        continue
    try:
        _tree = _ast.parse(_py.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for _node in _ast.walk(_tree):
        if not isinstance(_node, _ast.Call):
            continue
        _fn = _node.func
        if not isinstance(_fn, _ast.Attribute):
            continue
        _owner = _fn.value
        _owner_name = (
            _owner.attr if isinstance(_owner, _ast.Attribute)
            else _owner.id if isinstance(_owner, _ast.Name) else ""
        )
        _key = (_owner_name, _fn.attr)
        if _key in _DEPRECATED:
            _offenders.append(
                f"{_py.relative_to(ROOT)}:{_node.lineno} "
                f"{_owner_name}.{_fn.attr}() → {_DEPRECATED[_key]}"
            )

check("لا استدعاء وقت مهجور في المشروع", not _offenders,
      " · ".join(_offenders[:4]) + (f" (+{len(_offenders) - 4})"
                                    if len(_offenders) > 4 else ""))

# ووقت البحث نفسه واعٍ بالمنطقة — لا يكفي ألّا يكون مهجوراً
from scanner.research.dataset import _now as _ds_now  # noqa: E402

check("طابع الداتاست يحمل منطقة زمنية",
      _ds_now().endswith("+00:00"), _ds_now())
check("ويطابق صيغة jobs و experiment",
      "Z" not in _ds_now(), _ds_now())

bad = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not bad else f"✗ فشل {len(bad)} من {len(results)}")
sys.exit(1 if bad else 0)
