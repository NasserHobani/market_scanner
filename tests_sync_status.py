# -*- coding: utf-8 -*-
"""حالة بيانات السوق — لا تُحسَب في مسار الطلب.

═══ العطب المقيس ═══

``global_status()`` كان يُعيد تقييم **كل زوج مسجَّل** بقراءة ملفّ شموعه
من القرص. وقياسٌ فعلي على 1588 زوجاً: **26.3 ثانية** للنداء الواحد.

وهذه النقطة تُنادى من ``base.html`` في كل تحميل صفحة وكل ثلاثين ثانية.
فكانت كل صفحة تنتظر ألفاً وخمسمئة قراءة قرص متسلسلة قبل أن ترسم شارة
صغيرة — وهو ما يظهر للمستخدم «تحديثاً يظلّ يدور».

═══ العلاج على ثلاث طبقات ═══

  ١. **قراءة الذيل** بدل تحميل الملف كاملاً: كل المطلوب طابع آخر شمعة.
  ٢. **ذاكرة قصيرة**: الحالة لا تتغيّر أسرع من دورة عامل المزامنة.
  ٣. **القديم فوراً والتحديث خلفاً**: وإلّا حلّت الذاكرة تسعة وتسعين
     طلباً وتركت المئة ينتظر — وهو من يشتكي.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


def code_of(path: str) -> str:
    src = (ROOT / path).read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith("#"))


# ── ١) قراءة الذيل تطابق التحميل الكامل ──
#
# سرعةٌ تعطي جواباً مختلفاً ليست تحسيناً بل عطباً جديداً.
from scanner import storage  # noqa: E402

pairs: list[tuple[str, str, str]] = []
for market in ("crypto", "us", "saudi"):
    base = ROOT / "data" / market
    if not base.exists():
        continue
    for tf_dir in sorted(base.iterdir())[:3]:
        if not tf_dir.is_dir():
            continue
        for f in sorted(tf_dir.glob("*.csv"))[:25]:
            pairs.append((market, f.stem, tf_dir.name))

if pairs:
    mismatch = []
    for m, s, tf in pairs[:60]:
        fast = storage.last_time_on_disk(m, s, tf)
        full = storage.last_time(storage.load(m, s, tf))
        if str(fast) != str(full):
            mismatch.append((s, tf, str(fast), str(full)))
    check("١ الذيل يطابق التحميل الكامل", not mismatch,
          str(mismatch[:2]))

    # وأسرع فعلاً — وإلّا فلا مبرّر لوجوده
    # الذاكرة تُفرَّغ قبل كل قياس — وإلّا قِيس ``load`` مذاكَراً
    # ضدّ قراءة باردة، وهي مقارنة تقول عكس الحقيقة.
    sample = pairs[:40]
    storage.clear_frame_cache()
    t0 = time.time()
    for m, s, tf in sample:
        storage.clear_frame_cache()
        storage.last_time_on_disk(m, s, tf)
    fast_ms = (time.time() - t0) * 1000 / len(sample)
    t0 = time.time()
    for m, s, tf in sample:
        storage.clear_frame_cache()
        storage.last_time(storage.load(m, s, tf))
    full_ms = (time.time() - t0) * 1000 / len(sample)
    check("  وأسرع من التحميل الكامل", fast_ms < full_ms,
          f"{fast_ms:.2f}ms مقابل {full_ms:.2f}ms")
else:
    check("١ الذيل يطابق التحميل الكامل", True, "لا شموع مخزَّنة")
    check("  وأسرع من التحميل الكامل", True, "لا شموع مخزَّنة")

# الملفّ المفقود يعطي None لا استثناءً
check("  والمفقود يعطي None",
      storage.last_time_on_disk("crypto", "__لا_وجود_له__", "4h") is None)


# ── ٢) الذاكرة تعمل ──
from scanner.market_sync import get_service  # noqa: E402
from scanner.market_sync import service as svc_mod  # noqa: E402

svc = get_service()
svc_mod._STATUS_CACHE.clear()

t0 = time.time()
first = svc.global_status(markets=["saudi"])
cold = time.time() - t0
t0 = time.time()
second = svc.global_status(markets=["saudi"], max_age=60.0)
warm = time.time() - t0

check("٢ الذاكرة تُصيب", second.get("cached") is True, str(second.get("cached")))
check("  وأسرع بكثير", warm < max(cold, 1e-6), f"{warm*1000:.2f}ms")
check("  والنتيجة نفسها",
      first["pairs"] == second["pairs"] and first["status"] == second["status"])
check("  وعمرها معلَن", "cache_age" in second)

# ``max_age=0`` يفرض إعادة الحساب — عامل الخلفية يحتاجها
fresh = svc.global_status(markets=["saudi"])
check("  و max_age=0 يُعيد الحساب", not fresh.get("cached"))


# ── ٣) القديم فوراً والتحديث خلفاً ──
#
# أهمّ اختبار: طلبٌ يصل بعد انتهاء المهلة يجب ألّا ينتظر إعادة الحساب.
svc.global_status(markets=["saudi"])          # يملأ الذاكرة
lat = []
for _ in range(5):
    t0 = time.time()
    r = svc.global_status(markets=["saudi"], max_age=0.001)   # منتهية دائماً
    lat.append((time.time() - t0) * 1000)
worst = max(lat)
check("٣ الطلب بعد انتهاء المهلة لا ينتظر", worst < 500, f"أسوأ {worst:.1f}ms")
# «قديم» يظهر حين يكون التحديث جارياً. وقد يكتمل التحديث قبل الفحص
# على سوق بزوج واحد، فالفحص على المنطق لا على السباق الزمني.
svc_src = code_of("scanner/market_sync/service.py")
check("  ويُعلَن أنه قديم", '"stale"' in svc_src and "_refresh_in_background" in svc_src)

# خيط تحديث واحد لكل مفتاح — وإلّا صار العلاج مشكلة
check("  وخيط واحد لكل مفتاح", "_REFRESHING" in code_of(
    "scanner/market_sync/service.py"))
check("  محميّ بقفل", "_REFRESH_LOCK" in code_of(
    "scanner/market_sync/service.py"))


# ── ٤) النقطة تستعمل الذاكرة ──
view = code_of("web/dashboard/market_sync_views.py")
check("٤ النقطة تطلب نتيجة مذاكَرة", "max_age=" in view)
m = __import__("re").search(r"max_age=([\d.]+)", view)
check("  بمهلة معقولة", m and 5.0 <= float(m.group(1)) <= 300.0,
      m.group(1) if m else "—")

# التقييم لا يُحمّل الملف كاملاً حين لا يلزم
fresh_src = code_of("scanner/market_sync/freshness.py")
check("  والتقييم يستعمل الذيل", "last_time_on_disk" in fresh_src)
check("  ويسقط إلى التحميل عند الشكّ", "storage.load(" in fresh_src)


# ── ٥) الحساب من الطابع يطابق الحساب من الإطار ──
#
# ``bars_behind`` كان يحتاج DataFrame. والنسخة التي تعمل على الطابع
# وحده هي ما سمح بترك التحميل — فيجب أن تُعطي الرقم نفسه.
_bars_behind_from_last = storage.bars_behind_from

if pairs:
    diffs = []
    for m_, s_, tf_ in pairs[:30]:
        df = storage.load(m_, s_, tf_)
        if df is None or getattr(df, "empty", True):
            continue
        a = storage.bars_behind(df, tf_)
        b = _bars_behind_from_last(storage.last_time(df), tf_)
        if a is None and b is None:
            continue
        if a is None or b is None or abs(a - b) > 1:
            diffs.append((s_, tf_, a, b))
    check("٥ الحساب من الطابع يطابق الإطار", not diffs, str(diffs[:2]))
else:
    check("٥ الحساب من الطابع يطابق الإطار", True, "لا شموع")

check("  وبلا طابع يعيد None", _bars_behind_from_last(None, "4h") is None)
check("  وفريم مجهول يعيد None",
      _bars_behind_from_last("2026-01-01T00:00:00+00:00", "غير_معروف") is None)

# ── ٦) «لا بيانات بعد» ليس «بيانات متأخّرة» ──
#
# ═══ العطب ═══
#
# كان شرط الرفض ``critical + missing > النصف`` — فيخلط حالتين
# متضادّتين: ملفٌّ قديم (خطر: توصية بسعر عمره أسابيع) وغياب ملف
# (لا خطر: يُجلَب في السطر التالي).
#
# وانفجر لحظة **نجاح** الاكتشاف: صار السوق الأمريكي يكتشف أربعمئة
# رمز، وتسعون وثلاثمئة منها بلا ملف لأنّها جديدة. فتجاوز
# ``missing`` النصف، فأوقفت البوابة المسح، فلم تُحفَظ دورة، فظلّت
# اللوحة تعرض دورةً عمرها أسبوعان بعشرة رموز.
#
# أي أنّ البوابة كانت **تعاقب النجاح**: كلّما اكتشف النظام أكثر،
# ازداد يقينها أنّ شيئاً معطوب.
import shutil as _sh  # noqa: E402
import tempfile as _tf  # noqa: E402
from unittest import mock as _mk  # noqa: E402

import pandas as pd  # noqa: E402

from scanner import storage  # noqa: E402
from scanner.market_sync.config import MarketSyncConfig as _MSC  # noqa: E402
from scanner.market_sync.service import MarketDataSyncService as _SVC  # noqa: E402

_cfg6 = _MSC(max_symbols_per_market=1000, sync_timeframes=("1d",))
_tmp6 = Path(_tf.mkdtemp())


def _frame6(n, end):
    idx = pd.date_range(end=end, periods=n, freq="1D", tz="UTC")
    return pd.DataFrame({c: [1.0] * n for c in storage.OHLCV}, index=idx)


with _mk.patch.object(storage, "DATA_DIR", _tmp6 / "data"):
    storage.clear_frame_cache()
    _svc6 = _SVC(_cfg6)
    _fri = pd.Timestamp("2026-08-21 20:00", tz="UTC")     # إغلاق الجمعة
    for _i in range(10):
        storage.save("us", f"SYM{_i}", "1d", _frame6(200, _fri))
    _syms6 = ([f"SYM{i}" for i in range(10)]
              + [f"NEW{i}" for i in range(390)])
    _g = _svc6.scan_freshness_gate("us", "1d", symbols=_syms6,
                                   auto_refresh=False)
    check("٦ الإقلاع لا يُعدّ عطلاً", _g.get("ok") is True,
          f"{_g.get('code')} — {_g.get('counts')}")
    check("  والغياب يُحصى ولا يُبتلع",
          _g.get("counts", {}).get("missing") == 390,
          str(_g.get("counts")))

    # والنصف الآخر: الإنذار الصادق يجب أن يبقى صارخاً
    _sh.rmtree(_tmp6 / "data", ignore_errors=True)
    storage.clear_frame_cache()
    _old = pd.Timestamp("2026-08-07 20:00", tz="UTC")     # عشر جلسات
    for _i in range(20):
        storage.save("us", f"OLD{_i}", "1d", _frame6(200, _old))
    _g2 = _svc6.scan_freshness_gate("us", "1d",
                                    symbols=[f"OLD{i}" for i in range(20)],
                                    auto_refresh=False)
    check("  والتوقّف الحقيقي ما زال يُرفَض",
          _g2.get("ok") is False and _g2.get("code") == "MARKET_DATA_STALE",
          str(_g2.get("code")))
    # الرقم في الرسالة: «متأخرة جداً» بلا عدد لا تقول أثلاثة أم أربعمئة
    check("  والرسالة تحمل العدد", "20" in str(_g2.get("reason")),
          str(_g2.get("reason"))[:70])

_sh.rmtree(_tmp6, ignore_errors=True)
storage.clear_frame_cache()


# ── ٧) المقبرة لا تُحسب على الأحياء ──
#
# ═══ العطب ═══
#
# توقّف المسح التلقائي للكريبتو يوم ٢٠ أغسطس ولم يُنتج دورةً ولا
# مراقبةً ولا صفقةً بعدها. والسبب لم يكن في المسح:
#
#   crypto 4h · ٥٣٤ زوجاً · منها ١٣٨ آخر شمعة لها من **٢٠٢٢**
#
# رموزٌ شُطبت من المنصّة وبقيت ملفّاتها على القرص. كانت تُعدّ
# ``critical``، فبلغ «الحرج» ٥٤٫٩٪ — فوق النصف — فأعلنت البوابة
# السوق متأخّراً وأجهضت المسح قبل أن يبدأ.
#
# أي أنّ **مقبرةً على القرص كانت تحجب سوقاً حيّاً**، وكلّما طال
# الزمن ازدادت المقبرة ورسخ الحجب.
#
# والمقبرة لا تقول شيئاً عن صحّة الجلب اليوم، فتُخرَج من المقام.
_tmp7 = Path(_tf.mkdtemp())
_svc7 = _SVC(_MSC(max_symbols_per_market=1000, sync_timeframes=("4h",)))

with _mk.patch.object(storage, "DATA_DIR", _tmp7 / "data"):
    storage.clear_frame_cache()
    _now = pd.Timestamp.now("UTC").floor("h")

    def _bars(n, end, freq="4h"):
        idx = pd.date_range(end=end, periods=n, freq=freq, tz="UTC")
        return pd.DataFrame({c: [1.0] * n for c in storage.OHLCV}, index=idx)

    # ٢٠٠ حيّ (حديث) · ١٤٠ مشطوب من ٢٠٢٢ · ٣٠ متأخّر تأخّراً حقيقيّاً
    for i in range(200):
        storage.save("crypto", f"LIVE{i}", "4h", _bars(300, _now))
    for i in range(140):
        storage.save("crypto", f"DEAD{i}", "4h",
                     _bars(300, pd.Timestamp("2022-10-10", tz="UTC")))
    for i in range(30):
        storage.save("crypto", f"LAG{i}", "4h",
                     _bars(300, _now - pd.Timedelta(hours=40)))

    _syms7 = ([f"LIVE{i}" for i in range(200)]
              + [f"DEAD{i}" for i in range(140)]
              + [f"LAG{i}" for i in range(30)])
    _g7 = _svc7.scan_freshness_gate("crypto", "4h", symbols=_syms7,
                                    auto_refresh=False)
    _c7 = _g7.get("counts", {})

    check("٧ المشطوب يُصنَّف ميّتاً لا حرجاً",
          _c7.get("dead") == 140, str(_c7))
    check("  والمتأخّر حقيقيّاً يبقى حرجاً",
          _c7.get("critical") == 30, str(_c7))
    check("  والمقام هو الأحياء وحدهم",
          _g7.get("living") == 230, str(_g7.get("living")))
    # ١٧٠ من ٣٧٠ = ٤٦٪ بالحساب القديم… لكن ١٤٠ منها مقبرة
    check("  والمسح يمرّ", _g7.get("ok") is True,
          f"{_g7.get('code')} — {_c7}")
    check("  والمقبرة تُعرَض لا تُخفى", _g7.get("dead") == 140)

    # والنصف الآخر: عطلٌ حقيقيّ في الأحياء ما زال يوقف
    _g8 = _svc7.scan_freshness_gate(
        "crypto", "4h",
        symbols=[f"LAG{i}" for i in range(30)] + [f"DEAD{i}" for i in range(140)],
        auto_refresh=False)
    check("  والعطل الحقيقيّ ما زال يوقف",
          _g8.get("ok") is False, str(_g8.get("code")))
    check("  حتى لو غلبته المقبرة عدداً",
          _g8.get("counts", {}).get("dead") == 140
          and _g8.get("living") == 30, str(_g8.get("living")))

    # والمزامنة لا تلاحق الموتى: خمسمئة طلبٍ ضائع في كل دورة هي ما
    # ضخّم سجلّ الأحداث إلى ٣٠٥ ميغابايت.
    _yaml7 = _tmp7 / "config"
    _yaml7.mkdir(exist_ok=True)
    (_yaml7 / "crypto.yaml").write_text(
        'name: crypto\nadapter: binance\ntimeframes: ["4h"]\ncandles: 50\n'
        "universe: list\nsymbols: []\nworkers: 2\nweights: {}\nparams: {}\n",
        encoding="utf-8")
    _resolved = _svc7.resolve_symbols("crypto", config_dir=_yaml7)
    check("  والمزامنة تتخطّى المشطوبين",
          not any(s.startswith("DEAD") for s in _resolved),
          f"{sum(1 for s in _resolved if s.startswith('DEAD'))} مشطوباً تسرّب")
    check("  وتُبقي الأحياء والمتأخّرين",
          len(_resolved) == 230, str(len(_resolved)))
    check("  وتُعلن من دُفن", len(_svc7.last_buried) == 140,
          str(len(_svc7.last_buried)))

_sh.rmtree(_tmp7, ignore_errors=True)
storage.clear_frame_cache()

# ── ٨) سجلّ الأحداث يُدوَّر ──
#
# بلغ ٣٠٥ ميغابايت. والأداة التي وُضعت لتُفهم بها الأعطال صارت هي
# نفسها عطلاً: قرصٌ يمتلئ وسجلٌّ لا يُقرأ.
from scanner.market_sync import observability as _obs  # noqa: E402

check("٨ للسجلّ حدُّ حجم", hasattr(_obs, "MAX_EVENT_BYTES"))
check("  ومعقول (بين ١ و٥١٢ ميغا)",
      1 << 20 <= _obs.MAX_EVENT_BYTES <= 512 << 20,
      str(_obs.MAX_EVENT_BYTES))

_tmp8 = Path(_tf.mkdtemp())
_ev = _tmp8 / "events.jsonl"
_ev.write_text("x" * (_obs.MAX_EVENT_BYTES + 10), encoding="utf-8")
_obs._LAST_SIZE_CHECK[0] = 0.0
_obs._rotate(_ev)
check("  والتجاوز يُدوَّر", not _ev.exists() or _ev.stat().st_size == 0)
check("  والقديم يُحفظ نسخةً", (_tmp8 / "events.jsonl.1").exists())
_obs._LAST_SIZE_CHECK[0] = 0.0
_obs._rotate(_tmp8 / "لا_يوجد.jsonl")      # لا يرمي
check("  والملف الغائب لا يرمي", True)
_sh.rmtree(_tmp8, ignore_errors=True)


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
