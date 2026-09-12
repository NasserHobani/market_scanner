# -*- coding: utf-8 -*-
"""مخزن اللقطات الزمنية — إلحاق فقط، بلا إعادة كتابة.

═══ العطب الذي عولج هنا ═══

كانت ``_update_index`` تفعل لكل لقطة واحدة:

  ١. تقرأ ``index.json`` كاملاً وتحلّله،
  ٢. تضيف مدخلاً واحداً — وتخزّن فيه **اللقطة كاملة**،
  ٣. تكتب الملف كاملاً من جديد.

فصار الفهرس نسخة ثانية من مخزن اللقطات كلّه، تُعاد كتابتها من الصفر
عند كل صفّ. والكلفة تربيعية: كلما كبر المخزن غلا كل صفّ جديد.

القياس على مخزن المستخدم: ``index.json`` بلغ **5.06 ميجابايت**
لـ 716 لقطة، وكلفة اللقطة الواحدة **164 ملّي ثانية** قراءةً وتسلسلاً.

    ١٠٠ رمز في المسح  ⇒  16 ثانية في الفهرسة وحدها
    ٤٠٠ رمز           ⇒  66 ثانية
    ١٠٠٠ رمز          ⇒  164 ثانية

وكل هذا داخل ``transaction.atomic`` في أمر المسح، أي أن معاملة قاعدة
البيانات تبقى مفتوحة طوال المدة. وهذه وحدها كانت تفسّر معظم البطء.

═══ الحلّ ═══

فهرس **بالإلحاق** أيضاً: سطر صغير لكل لقطة يحمل المعرّفات و**إزاحة
البايت** في ملف اللقطات. فالكتابة ثابتة الكلفة مهما كبر المخزن،
والقراءة تقفز مباشرة إلى موضع اللقطة بلا مسح الملف.

واللقطة نفسها لا تُخزَّن في الفهرس — تخزينها مرّتين كان أصل المشكلة.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .contract import PointInTimeSnapshot

V3_STORE = Path("data/feature_snapshots/v3_snapshots.jsonl")
INDEX_STORE = Path("data/feature_snapshots/index.json")     # القديم — للهجرة
INDEX_JSONL = Path("data/feature_snapshots/index.jsonl")

_lock = threading.Lock()
# ذاكرة الفهرس داخل العملية: المسح يقرأه مئات المرات في الدورة
_cache: dict[str, Any] | None = None
_cache_size: int = -1


def _append_line(path: Path, text: str) -> int:
    """يُلحق سطراً ويعيد إزاحة بدايته بالبايت.

    الوضع الثنائي مقصود: ``seek`` على ملف نصّي لا يقبل إلا قيمة جاءت
    من ``tell`` الخاص به، وأي إزاحة محسوبة بالبايت تعطي نتيجة خاطئة
    بصمت — فيسقط الاسترجاع إلى المسح الكامل ويعود البطء من باب آخر.
    والنصّ عربي، فكل محرف يشغل بايتين أو ثلاثة ولا يساوي محرفاً واحداً.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (text + "\n").encode("utf-8")
    with path.open("ab") as fh:
        offset = fh.tell()
        fh.write(data)
    return offset


def _append(row: dict[str, Any], path: Path = V3_STORE) -> int:
    return _append_line(path, json.dumps(row, ensure_ascii=False, default=str))


def save(snapshot: PointInTimeSnapshot, *, path: Path | None = None) -> str:
    dest = path or V3_STORE
    with _lock:
        offset = _append(snapshot.to_dict(), dest)
        # الفهرس يُكتب فقط للمخزن الافتراضي: مسار مخصّص يعني اختباراً
        # أو تصديراً، وتلويث الفهرس الحيّ به يفسده
        if dest == V3_STORE:
            _index_append(snapshot, offset)
    return snapshot.snapshot_id


def _index_append(snapshot: PointInTimeSnapshot, offset: int) -> None:
    """سطر واحد صغير — لا إعادة كتابة ولا نسخ للّقطة."""
    global _cache
    entry = {
        "snapshot_id": snapshot.snapshot_id,
        "legacy_snapshot_id": snapshot.legacy_snapshot_id,
        "event_id": snapshot.event_id,
        "offset": offset,
        "created_at": snapshot.created_at,
    }
    _append_line(INDEX_JSONL, json.dumps(entry, ensure_ascii=False,
                                         default=str))
    if _cache is not None:
        _merge_entry(_cache, entry)
        _cache["updated_at"] = snapshot.created_at


def _merge_entry(idx: dict[str, Any], entry: dict[str, Any]) -> None:
    sid = entry.get("snapshot_id")
    if sid:
        idx.setdefault("by_id", {})[sid] = entry.get("offset")
    legacy = entry.get("legacy_snapshot_id")
    if legacy and sid:
        idx.setdefault("by_legacy", {})[legacy] = sid
    event = entry.get("event_id")
    if event and sid:
        idx.setdefault("by_event", {})[event] = sid


def _migrate_legacy(idx: dict[str, Any]) -> None:
    """يستوعب ``index.json`` القديم مرّة واحدة بلا فقدان الروابط.

    القديم كان يخزّن اللقطة كاملة تحت ``by_id``؛ هنا يُحتفظ بالمعرّفات
    والروابط فقط، ويُترك الملف مكانه بلا حذف — الحذف ليس من شأن دالة
    قراءة.
    """
    if not INDEX_STORE.exists():
        return
    try:
        old = json.loads(INDEX_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for sid in (old.get("by_id") or {}):
        idx.setdefault("by_id", {}).setdefault(sid, None)   # None = بلا إزاحة
    idx.setdefault("by_legacy", {}).update(old.get("by_legacy") or {})
    idx.setdefault("by_event", {}).update(old.get("by_event") or {})


def load_index() -> dict[str, Any]:
    """الفهرس مبنيّاً من ملف الإلحاق، مخزَّناً في الذاكرة.

    يُعاد البناء فقط إن كبر الملف — أي بعد كتابة من عملية أخرى.
    """
    global _cache, _cache_size
    size = INDEX_JSONL.stat().st_size if INDEX_JSONL.exists() else 0
    if _cache is not None and size == _cache_size:
        return _cache

    idx: dict[str, Any] = {"by_id": {}, "by_legacy": {}, "by_event": {}}
    _migrate_legacy(idx)
    if INDEX_JSONL.exists():
        with INDEX_JSONL.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    _merge_entry(idx, json.loads(line))
                except json.JSONDecodeError:
                    continue        # سطر نصف مكتوب من انقطاع
    _cache, _cache_size = idx, size
    return idx


def _read_at(offset: int, path: Path) -> dict[str, Any] | None:
    """سطر واحد من موضع بايت محدَّد — بلا قراءة ما قبله ولا ما بعده."""
    try:
        with path.open("rb") as fh:
            fh.seek(offset)
            raw = fh.readline()
        line = raw.decode("utf-8").strip()
        return json.loads(line) if line else None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def get_by_id(snapshot_id: str, *, path: Path | None = None
              ) -> PointInTimeSnapshot | None:
    dest = path or V3_STORE
    if not dest.exists():
        return None

    if dest == V3_STORE:
        offset = (load_index().get("by_id") or {}).get(snapshot_id)
        if offset is not None:
            row = _read_at(int(offset), dest)
            # التحقّق من المعرّف بعد القفز: إزاحة قديمة من ملف نُقل أو
            # قُصّ تعطي سطراً خاطئاً، والسكوت عنه يعيد لقطة رمز آخر
            if row and row.get("snapshot_id") == snapshot_id:
                return PointInTimeSnapshot.from_dict(row)

    # احتياط: مسح من الآخِر (الأحدث أولاً) بلا تحميل الملف كله
    for row in _iter_rows_reversed(dest):
        if row.get("snapshot_id") == snapshot_id:
            return PointInTimeSnapshot.from_dict(row)
    return None


def _iter_rows_reversed(path: Path):
    """قراءة سطراً سطراً بلا تحميل الملف كله في الذاكرة.

    ``read_text().splitlines()`` على ملف خمسة ميجابايت يبني نسختين منه
    في الذاكرة لكل استدعاء — وهو ما كان يُستدعى داخل حلقة المسح.
    """
    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def get_by_legacy(legacy_id: str) -> PointInTimeSnapshot | None:
    sid = (load_index().get("by_legacy") or {}).get(legacy_id)
    return get_by_id(sid) if sid else None


def iter_snapshots(*, path: Path | None = None) -> list[PointInTimeSnapshot]:
    dest = path or V3_STORE
    if not dest.exists():
        return []
    out: list[PointInTimeSnapshot] = []
    with dest.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                try:
                    out.append(PointInTimeSnapshot.from_dict(json.loads(line)))
                except json.JSONDecodeError:
                    continue
    return out


def count_snapshots(*, path: Path | None = None) -> int:
    dest = path or V3_STORE
    if not dest.exists():
        return 0
    with dest.open(encoding="utf-8") as fh:
        return sum(1 for ln in fh if ln.strip())


def rebuild_index(*, path: Path | None = None) -> int:
    """يعيد بناء ``index.jsonl`` من ملف اللقطات — بإزاحات صحيحة.

    يُحتاج إليه بعد ترقية من الفهرس القديم أو بعد نقل الملفات: الإزاحة
    التي لا تطابق ملفها أسوأ من غيابها.
    """
    global _cache, _cache_size
    dest = path or V3_STORE
    if not dest.exists():
        return 0
    tmp = INDEX_JSONL.with_suffix(".rebuilding")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    # القراءة ثنائية لا نصّية: الوضع النصّي يترجم CRLF إلى LF عند
    # القراءة، فيصير عدّ البايتات أقلّ بواحد لكل سطر — والملف كُتب على
    # ويندوز فعلاً. النتيجة إزاحات منزاحة تدريجياً تفشل بصمت وتُسقط
    # الاسترجاع إلى المسح الكامل، أي أن العطب الذي نصلحه يعود متخفّياً.
    with dest.open("rb") as src, tmp.open("w", encoding="utf-8") as out:
        offset = 0
        for raw in src:
            line = raw.strip()
            if line:
                try:
                    row = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    row = None
                if row:
                    out.write(json.dumps({
                        "snapshot_id": row.get("snapshot_id"),
                        "legacy_snapshot_id": row.get("legacy_snapshot_id"),
                        "event_id": row.get("event_id"),
                        "offset": offset,
                        "created_at": row.get("created_at"),
                    }, ensure_ascii=False, default=str) + "\n")
                    n += 1
            offset += len(raw)
    os.replace(tmp, INDEX_JSONL)
    _cache, _cache_size = None, -1
    return n
