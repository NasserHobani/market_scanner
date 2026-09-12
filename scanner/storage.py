"""تخزين تراكمي: لا يُعاد تنزيل التاريخ كاملاً، تُضاف الشموع الجديدة فقط."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")


# أعمدة الشمعة بترتيب ثابت — الترتيب جزء من الصيغة الثنائية.
OHLCV = ("open", "high", "low", "close", "volume")

# صيغ مقروءة بترتيب الأفضلية. الأولى تُكتَب، والبقية تُقرأ للتوافق.
#
# ═══ لماذا صيغة ثنائية ═══
#
# ‏CSV نصّ: كل رقم يُحوَّل من محارف إلى عدد عند كل قراءة، وكل طابع
# زمني يُحلَّل من نصّ. وقياسٌ على ملفّاتك (1578 شمعة، 96KB):
#
#     CSV → DataFrame      16.21 ms
#     ثنائي → DataFrame     0.63 ms      أسرع ×25.6
#     الحجم                71KB مقابل 96KB
#
# ولـ500 رمز: **8.1 ثانية تصير 0.3**.
#
# وهذا هو سرّ سرعة المنصّات الكبيرة رغم تاريخها الضخم: تخزين عمودي
# ثنائي بأنواع محدَّدة، لا نصّ يُعاد تحليله في كل مرّة.
#
# ═══ ولماذا الطوابع منفصلة ═══
#
# جرّبتُ أوّلاً وضع الطابع داخل مصفوفة ``float64`` مع الأسعار. ونجح
# الاختبار — **بالصدفة**: الطابع بالنانوثانية يبلغ 1.79e18 بينما
# ``float64`` يضمن الدقّة حتى 9.0e15 فقط. ومرّ لأن طوابع الشموع
# مضاعفات الثانية، فتترك تسع بتّات صفرية تتّسع بالكاد.
#
# وأي مصدر بدقّة الميلي أو الميكرو كان سيُزيح الوقت بصمت. فالطوابع
# تُخزَّن ``int64`` في مصفوفة مستقلّة: لا مصادفة ولا افتراض.
FORMATS = ("npz", "parquet", "csv")

# لواحق الملفّات المقروءة — مشتقّة من ``FORMATS`` لا مكتوبة يدوياً.
#
# ═══ لماذا اشتقاقاً ═══
#
# كان في ``market_sync/service.py`` سطرٌ يقول
# ``if p.suffix in (".parquet", ".csv")`` — قائمةٌ يدويّة كُتبت يوم
# كانت الصيغتان اثنتين. ولمّا أضفتُ ``npz`` وصارت هي الافتراض، لم
# يَعُد ذلك السطر يرى شيئاً على القرص: صار السوق الأمريكي يسقط إلى
# قائمة الرموز الاحتياطية (عشرة رموز) وكأنّ القرص فارغ.
#
# لم يكشفه اختبار لأن الاختبارات تكتب وتقرأ عبر ``storage`` نفسه،
# ولا تمرّ على ذلك التصفية. فالعلاج بنيويّ: مصدر واحد للّواحق،
# ومن أراد تعداد ما على القرص فليستعمل ``stored_symbols``.
SUFFIXES = tuple(f".{f}" for f in FORMATS)


def stored_symbols(market: str, timeframe: str) -> list[str]:
    """الرموز الموجودة فعلاً على القرص لهذا السوق والإطار."""
    root = DATA_DIR / market / timeframe
    if not root.exists():
        return []
    seen: dict[str, None] = {}
    try:
        for p in root.iterdir():
            if p.suffix in SUFFIXES:
                seen.setdefault(p.stem, None)
    except OSError:
        return []
    return list(seen)


def _path(market: str, symbol: str, timeframe: str, fmt: str) -> Path:
    return DATA_DIR / market / timeframe / f"{symbol}.{fmt}"


def _fmt() -> str:
    """الصيغة التي تُكتَب بها الشموع الجديدة."""
    import os

    forced = os.getenv("SCANNER_STORAGE_FORMAT", "").strip().lower()
    if forced in FORMATS:
        return forced
    return "npz"


def storage_format() -> str:
    """الصيغة المستعملة فعلاً."""
    return _fmt()


def _existing_path(market: str, symbol: str, timeframe: str):
    """أوّل ملفّ موجود بترتيب الأفضلية — ``(المسار، الصيغة)`` أو None.

    التوافق للخلف ليس ترفاً: عندك آلاف ملفّات ‏CSV، وكسرُها يعني فقدان
    تاريخ لا يُشترى. فالقراءة تقبل الصيغ الثلاث، والكتابة وحدها تُحدَّث.
    """
    for fmt in FORMATS:
        p = _path(market, symbol, timeframe, fmt)
        if p.exists():
            return p, fmt
    return None


# وحدة الطوابع المخزَّنة. تُكتب داخل الملف ولا تُفترَض.
#
# ═══ عطبٌ وقع فعلاً ═══
#
# النسخة الأولى كتبت ``idx.view("int64")`` وقرأتها
# ``ts.view("datetime64[ns]")`` — أي افترضت النانوثانية دائماً.
#
# و‏pandas 2.x **لا تفرضها**: الفهرس قد يكون ``datetime64[us]`` أو
# ``[ms]`` أو ``[s]`` حسب مصدره، و``view("int64")`` يعطي الرقم بوحدته
# هو. فملفّ NVDA على 4h كُتب بالميكروثانية وقُرئ نانوثانيةً، فصار
# تاريخه **1970-01-21** بدل 2025.
#
# والعطب صامت تماماً: لا استثناء ولا تحذير — ملفّ يبدو سليماً بتواريخ
# مستحيلة. ولم يظهر في اختباراتي لأنها تبني الفهرس بـ``date_range``
# الذي يعطي نانوثانية.
#
# فالوحدة تُثبَّت عند الكتابة وتُقرأ من الملف عند القراءة. والملفّات
# التي كُتبت قبل هذا الإصلاح تُكتشَف بغياب المفتاح ويُرفض قبولها.
_TS_UNIT = "ns"


def _read_npz(path: Path) -> pd.DataFrame:
    import numpy as np

    with np.load(path) as z:
        ts = z["ts"]
        arr = z["ohlcv"]
        # ملفّ بلا وحدة معلَنة كُتب بنسخة معطوبة — لا يُقبل تخميناً
        unit = str(z["unit"]) if "unit" in z.files else ""
    if unit not in ("s", "ms", "us", "ns"):
        raise ValueError(
            f"ملفّ شموع بلا وحدة زمنية معلَنة: {path.name} — "
            "كُتب بنسخة معطوبة، أعد بناءه من المصدر")
    idx = pd.DatetimeIndex(
        ts.view(f"datetime64[{unit}]"), tz="UTC", name="open_time")
    return pd.DataFrame(dict(zip(OHLCV, arr.T)), index=idx)


def _write_npz(path: Path, df: pd.DataFrame) -> None:
    import numpy as np

    idx = pd.DatetimeIndex(df.index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    # التثبيت على وحدة واحدة قبل ``view``: الوحدة المختلطة هي أصل العطب
    try:
        idx = idx.as_unit(_TS_UNIT)
    except AttributeError:          # pandas أقدم من 2.0 — النانوثانية أصلاً
        pass
    ts = np.asarray(idx.view("int64"), dtype=np.int64)
    cols = [
        df[c].to_numpy(dtype=np.float64) if c in df.columns
        else np.full(len(df), np.nan)
        for c in OHLCV
    ]
    np.savez(path, ts=ts, ohlcv=np.column_stack(cols),
             unit=np.array(_TS_UNIT))


def load(market: str, symbol: str, timeframe: str) -> pd.DataFrame | None:
    found = _existing_path(market, symbol, timeframe)
    if found is None:
        return None
    path, fmt = found

    cached = _frame_cache_get(path)
    if cached is not None:
        return cached

    if fmt == "npz":
        try:
            df = _read_npz(path)
        except (ValueError, KeyError, OSError) as exc:
            # ملفّ ثنائي تالف لا يُخفي وجود CSV سليم بجانبه، ولا
            # يُرجع بيانات مشكوكاً فيها. والصمت هنا كان سيُنتج تواريخ
            # من 1970 تمرّ في كل حساب لاحق.
            import logging

            logging.getLogger(__name__).warning(
                "ملفّ شموع ثنائي مرفوض (%s): %s", path.name, str(exc)[:120])
            csv_path = _path(market, symbol, timeframe, "csv")
            if csv_path.exists():
                df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
                _frame_cache_put(csv_path, df)
                return df
            return None
    elif fmt == "parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, index_col=0, parse_dates=True)

    _frame_cache_put(path, df)
    return df


def save(market: str, symbol: str, timeframe: str, df: pd.DataFrame) -> Path:
    """يحفظ بالصيغة الحالية، ويزيل النسخ القديمة للرمز نفسه.

    ═══ الترحيل يقع عند الحفظ ═══

    لا حاجة لخطوة ترحيل إجبارية: كل رمز يُحدَّث يُكتب بالصيغة الجديدة
    تلقائياً. والقديم يبقى مقروءاً حتى يأتي دوره.

    وإزالة النسخة القديمة ضرورية لا تجميلية: ملفّان لنفس الرمز يعني
    أن ``_existing_path`` قد يقرأ أحدهما والآخر يتقادم — أي مصدرا حقيقة
    لبيانات واحدة، وهو أسوأ من البطء.
    """
    fmt = _fmt()
    p = _path(market, symbol, timeframe, fmt)
    p.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "npz":
        _write_npz(p, df)
    elif fmt == "parquet":
        df.to_parquet(p)
    else:
        df.to_csv(p)

    for other in FORMATS:
        if other == fmt:
            continue
        stale = _path(market, symbol, timeframe, other)
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass

    _frame_cache_invalidate(p)
    return p


# ─────────────────────────────────────── ذاكرة الإطارات
#
# ═══ لماذا ═══
#
# الملفّ الواحد يُقرأ مرّات في الدورة: المسح، ثمّ الحسم، ثمّ فحص
# الحداثة، ثمّ عرض الشارت. وكلّها تقرأ **نفس البايتات** وتعيد بناء
# نفس الإطار.
#
# والذاكرة هنا تُبطِل نفسها بزمن تعديل الملف وحجمه، لا بمهلة. فملفّ
# لم يتغيّر يُخدَم من الذاكرة، وملفّ كُتب من جديد يُقرأ من جديد —
# فلا تُبنى قرارات على شموع قديمة، وهو الخطر الوحيد الذي تستحقّ
# الذاكرة الحذر منه.
#
# والإطار يُعاد **كما هو** لا نسخةً منه: النسخ يُلغي أغلب المكسب.
# والمنادون في هذا المشروع لا يعدّلون الإطار في مكانه — وهذا عقد
# ضمني يحرسه اختبار.
_FRAME_CACHE: dict = {}
_FRAME_CACHE_MAX = 600
_frame_lock = None


def _cache_lock():
    global _frame_lock
    if _frame_lock is None:
        import threading

        _frame_lock = threading.Lock()
    return _frame_lock


def _stat_key(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _frame_cache_get(path: Path):
    key = _stat_key(path)
    if key is None:
        return None
    with _cache_lock():
        hit = _FRAME_CACHE.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    return None


def _frame_cache_put(path: Path, df) -> None:
    key = _stat_key(path)
    if key is None or df is None:
        return
    with _cache_lock():
        if len(_FRAME_CACHE) >= _FRAME_CACHE_MAX:
            # إخلاء بسيط: أقدم مدخل إدراجاً. القواميس في بايثون تحفظ
            # ترتيب الإدراج، فهذا كافٍ بلا بنية إضافية.
            for old_key in list(_FRAME_CACHE)[:_FRAME_CACHE_MAX // 4]:
                _FRAME_CACHE.pop(old_key, None)
        _FRAME_CACHE[str(path)] = (key, df)


def _frame_cache_invalidate(path: Path) -> None:
    with _cache_lock():
        _FRAME_CACHE.pop(str(path), None)


def clear_frame_cache() -> None:
    """يفرّغ ذاكرة الإطارات — للاختبارات وللصيانة."""
    with _cache_lock():
        _FRAME_CACHE.clear()


def merge(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    if old is None or old.empty:
        return new
    combined = pd.concat([old, new])
    combined = combined[~combined.index.duplicated(keep="last")]
    return combined.sort_index()


def archive_scan(market: str, rows: list[dict]) -> Path:
    """أرشفة كل مسح — هذه الخطوة هي ما يسمح بتقييم الأداء لاحقاً."""
    out_dir = DATA_DIR / "archive"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M")
    p = out_dir / f"{market}_{stamp}.csv"
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def last_time(df: pd.DataFrame | None):
    """وقت آخر شمعة مخزّنة — أو None إن لا تخزين."""
    if df is None or df.empty:
        return None
    try:
        return df.index[-1]
    except (IndexError, AttributeError):
        return None


# ملفّات تعذّرت قراءتها — تُسجَّل مرّةً لكلٍّ لا في كل نداء.
# التحذير المتكرّر آلاف المرّات في الدقيقة يُغرق السجلّ ويُهمَل.
_UNREADABLE: set[str] = set()


def _note_unreadable(path) -> None:
    key = str(path)
    if key in _UNREADABLE:
        return
    _UNREADABLE.add(key)
    try:
        import logging

        logging.getLogger("scanner.storage").warning(
            "ملفّ شموع تالف يُعامَل كغائب: %s — سيُعاد بناؤه بالجلب", key)
    except Exception:  # noqa: BLE001
        pass


def unreadable_files() -> list[str]:
    """ما تعذّرت قراءته منذ الإقلاع — للتشخيص."""
    return sorted(_UNREADABLE)


def last_time_on_disk(market: str, symbol: str, timeframe: str):
    """وقت آخر شمعة **بلا تحميل الملف كاملاً**.

    ═══ لماذا وُجدت ═══

    ``assess_freshness`` كان ينادي ``load()`` — أي يقرأ ويحلّل 1200
    شمعة — ثمّ يأخذ الطابع الأخير وحده ويرمي الباقي. و
    ``global_status`` يكرّر ذلك لكل زوج مسجَّل: **1588 زوجاً**.

    والقياس: 18.76ms للزوج، أي **26.3 ثانية** لنداء واحد. وهذه النقطة
    تُنادى من كل صفحة عند التحميل وكل ثلاثين ثانية — فيبقى «التحديث»
    دائراً نصف دقيقة، وهي شكوى المستخدم حرفياً.

    والقراءة هنا تقفز إلى آخر الملف وتقرأ بضعة كيلوبايتات. النتيجة
    نفسها، والكلفة جزء من الألف.

    تُعيد ``None`` عند أي شكّ — والمنادي يسقط حينها إلى ``load()``
    الكامل، فلا يُبنى قرار على قراءة ناقصة.
    """
    found = _existing_path(market, symbol, timeframe)
    if found is None:
        return None
    path, fmt = found
    try:
        if fmt == "npz":
            # الصيغة الثنائية تحمل الطوابع في مصفوفة مستقلّة، فآخر
            # عنصر يُقرأ مباشرةً بلا بناء إطار ولا تحليل نصّ.
            import numpy as np

            cached = _frame_cache_get(path)
            if cached is not None:
                return last_time(cached)
            with np.load(path) as z:
                ts = z["ts"]
                if len(ts) == 0:
                    return None
                return pd.Timestamp(int(ts[-1]), tz="UTC")
        if fmt != "csv":
            # ‏parquet لا يُقرأ بالذيل — نرجع للتحميل الكامل
            return last_time(load(market, symbol, timeframe))

        size = path.stat().st_size
        if size <= 0:
            return None
        # نصف كيلوبايت يكفي لسطرين — والسطر الواحد نحو ثمانين محرفاً.
        # القراءة الأكبر لا تضيف إلا نقل بيانات لا تُستعمل.
        chunk = min(size, 512)
        with path.open("rb") as fh:
            fh.seek(size - chunk)
            tail = fh.read(chunk).decode("utf-8", errors="ignore")
        lines = [ln for ln in tail.splitlines() if ln.strip()]
        # السطر الأول قد يكون مقطوعاً في المنتصف حين لا يبدأ القراءة
        # من بداية سطر — يُهمَل ما لم يكن الملف كلّه في القطعة
        if chunk < size and len(lines) > 1:
            lines = lines[1:]
        for line in reversed(lines):
            stamp = line.split(",", 1)[0].strip()
            if not stamp or stamp.lower().startswith("open_time"):
                continue
            # ‏fromisoformat أسرع من pd.to_datetime بأربعمئة ضعف على
            # طابع مفرد (0.0006ms مقابل 0.283ms). و pandas تُستدعى
            # احتياطاً وحدها حين تختلف الصيغة.
            try:
                from datetime import datetime as _dt

                ts = pd.Timestamp(_dt.fromisoformat(stamp))
            except ValueError:
                ts = pd.to_datetime(stamp, errors="coerce", utc=True)
                if ts is pd.NaT or ts != ts:
                    continue
            return ts
        return None
    except Exception:  # noqa: BLE001
        # ═══ ملفٌّ تالف يُعامَل كغائب لا كانهيار ═══
        #
        # وُجد ``crypto/4h/GIGGLEUSDT.npz`` مبتوراً (٧٢ كيلوبايت، كتابة
        # قُطعت في منتصفها). و``np.load`` يرمي ``BadZipFile`` — وهو
        # ليس ``OSError`` ولا ``ValueError``، فكان يعبر هذا الحارس
        # ويصعد.
        #
        # وأثره أوسع من رمزٍ واحد: ``scan_freshness_gate`` يقيّم كل
        # رموز السوق في قائمةٍ واحدة بلا حماية، فملفٌّ تالف يُسقط
        # تقييم **السوق كلّه**. بايتٌ واحد على القرص يُعمي سوقاً.
        #
        # والغياب هو الوصف الصادق: لا نعرف آخر شمعة. والجلب التراكمي
        # سيعيد بناء الملف من الصفر — وهو ما يُصلحه فعلاً.
        _note_unreadable(path)
        return None


def bars_needed(df: pd.DataFrame | None, timeframe: str, full: int,
                *, now=None, margin: int = 3) -> int:
    """كم شمعة يلزم جلبها فعلاً؟

    هذا الملف بُني للتخزين التراكمي منذ البداية، لكن أمر المسح كان يطلب
    ``full`` شمعة في كل دورة — أي ~1500 شمعة لرمز لم يتغيّر منه إلا
    شمعة أو اثنتان. النتيجة طلبان لكل رمز ومئات الكيلوبايتات بلا فائدة.

    ``margin`` هامش يعوّض انقطاعاً قصيراً أو تصحيحاً في آخر الشموع؛
    وأي فجوة أطول تُملأ تلقائياً لأن الحساب من آخر شمعة مخزّنة.
    """
    if full <= 0:
        return 0
    last = last_time(df)
    if last is None:
        return full

    try:
        from .live import timeframe_seconds

        seconds = timeframe_seconds(timeframe)
    except Exception:  # noqa: BLE001
        return full
    if not seconds:
        return full

    now = now if now is not None else pd.Timestamp.now("UTC")
    try:
        if getattr(last, "tzinfo", None) is not None and now.tzinfo is None:
            now = now.tz_localize("UTC")
        elif getattr(last, "tzinfo", None) is None and now.tzinfo is not None:
            now = now.tz_localize(None)
        elapsed = (now - last).total_seconds()
    except (TypeError, ValueError):
        return full
    if elapsed < 0:
        elapsed = 0.0

    needed = int(elapsed // seconds) + margin
    return max(2, min(full, needed))


def bars_behind(df: pd.DataFrame | None, timeframe: str, *, now=None,
                market: str | None = None):
    """كم شمعة تأخّر آخر ما لدينا عن الحاضر؟ ``None`` إن تعذّر القياس."""
    return bars_behind_from(last_time(df), timeframe, now=now, market=market)


def bars_behind_from(last, timeframe: str, *, now=None,
                     market: str | None = None):
    """كـ:func:`bars_behind` لكن من الطابع وحده بلا إطار.

    وُجدت لتسمح لـ``assess_freshness`` بقراءة ذيل الملف بدل تحميله
    كاملاً — وهو ما خفّض ``global_status`` من 26 ثانية.

    ولماذا لا تُستنسخ الحسبة هناك: استنسختُها أوّلاً فأعطت **عدداً
    صحيحاً** بينما الأصل يعطي **كسراً** (2 مقابل 3.07)، فاختلف تصنيف
    الحداثة بين مسارين يفترض أن يتّفقا. والاختبار أمسكه.

    فالقاعدة: حسبة واحدة في موضع واحد، ومن يحتاجها ينادِها.

    ═══ ``market`` ولماذا يغيّر الجواب ═══

    بلا سوق يُقاس المنقضي بساعة الحائط — وهو صحيح للكريبتو وحده.
    ومع سوق يُقاس **بزمن السوق المفتوح**، ثمّ تُطرح مهلة بثّ
    الاشتراك.

    وبلا هذا كان كل سبت يُنتج ``بيانات السوق متأخرة جداً``: أربعون
    ساعة بين إغلاق الخميس وصباح السبت، لا تُتداول فيها ورقة واحدة،
    كانت تُحسَب تأخّراً. والإنذار الذي يكذب كل أسبوع يُفقد الثقة
    بالإنذار الصادق يوم يتعطّل الجلب فعلاً.
    """
    if last is None:
        return None
    try:
        from .live import timeframe_seconds

        seconds = timeframe_seconds(timeframe)
    except Exception:  # noqa: BLE001
        return None
    if not seconds:
        return None

    now = now if now is not None else pd.Timestamp.now("UTC")
    try:
        if getattr(last, "tzinfo", None) is not None and now.tzinfo is None:
            now = now.tz_localize("UTC")
        elif getattr(last, "tzinfo", None) is None and now.tzinfo is not None:
            now = now.tz_localize(None)
        elapsed = (now - last).total_seconds()
    except (TypeError, ValueError):
        return None
    elapsed = max(0.0, elapsed)

    if market:
        try:
            from . import sessions

            # مهلة البثّ تُطرح من الزمن المفتوح قبل التحويل إلى
            # شموع: الاشتراك المجاني يتأخّر ربع ساعة، فأحدث ما
            # يمكن الحصول عليه أصلاً عمره ربع ساعة. عدّه تأخّراً
            # معاقبةٌ على حدٍّ في الاشتراك لا على خلل في النظام.
            delay = sessions.feed_delay_seconds(market)
            ref = now
            if delay:
                ref = now - pd.Timedelta(seconds=delay)
                if ref < last:
                    return 0.0
            return max(0.0, sessions.bars_elapsed(last, ref, seconds, market))
        except Exception:  # noqa: BLE001
            pass          # سوق مجهول أو منطقة زمنية غائبة — الحائط يكفي

    return elapsed / seconds


def is_stale(df: pd.DataFrame | None, timeframe: str, *, max_bars: int = 3,
             now=None, market: str | None = None) -> bool:
    """هل آخر شمعة أقدم من أن تُبنى عليها توصية؟

    عطب حقيقي لا احتياط نظري: رمز يُشطب من المنصّة يبقى ملفه على القرص،
    والجلب التراكمي يطلب الناقص فلا يعود بشيء، فيصير آخر ما في الملف —
    شمعة من 2022 مثلاً — هو «آخر شمعة» في نظر المحلّل. فيصدر توصية
    بسعر عمره سنوات، وتُفتح صفقة معلّقة لن تُحسم أبداً لأن السعر لن
    يتحرّك. وُجد سبعة وخمسون صفّاً كهذا في قاعدة البيانات، من 2022
    إلى 2025.

    والقياس بالشموع لا بالأيام: ثلاث شموع على 15m خمسة وأربعون دقيقة،
    وعلى 1d ثلاثة أيام. عتبة زمنية واحدة إمّا تخنق الفريم البطيء أو
    تترك السريع.

    ``None`` من ``bars_behind`` يعني تعذّر القياس — لا يُحكم بالقِدم
    عند الشكّ، فإسقاط رمز صالح أسوأ من فحص رمز قديم.

    ═══ ``market`` ولماذا هو ضروريّ هنا تحديداً ═══

    الحدّ ثلاث شمعات. وسهمٌ أمريكي على فريم ``1d`` عند إغلاق الجمعة
    يصير الثلاثاء **متأخّراً 4.5 شمعة** بساعة الحائط بينما لم تمرّ
    إلّا جلستان. وهذا يُسقط كل رمز في السوق دفعةً واحدة بعد أي عطلة
    طويلة، فيقول المسح «لا نتائج» ولا يُحفَظ شيء — فتظلّ اللوحة على
    آخر دورة ناجحة مهما قدُمت.

    والقياس بزمن السوق يجعل الحدّ يعني ما يقوله: ثلاث **جلسات**.
    """
    behind = bars_behind(df, timeframe, now=now, market=market)
    return behind is not None and behind > max_bars
