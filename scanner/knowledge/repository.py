# -*- coding: utf-8 -*-
"""Append-only knowledge repository — persistence only, no business logic."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import RepositoryError, SnapshotNotFoundError
from .schemas import KnowledgeRecord, SnapshotKind


DEFAULT_STORE = Path("data/knowledge/records.jsonl")


# ذاكرة السجلّات المقروءة — مفتاحها حالة الملفّ لا الزمن.
_CACHE: dict[tuple, list] = {}


def clear_cache() -> None:
    """تفريغ الذاكرة — للاختبارات وللأدوات التي تعدّل الملفّ خارجاً."""
    _CACHE.clear()


class KnowledgeRepository:
    """JSONL-backed store for all knowledge snapshot types."""

    def __init__(self, path: Path | str = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, row: dict[str, Any]) -> None:
        self._ensure_parent()
        try:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            raise RepositoryError(str(exc)) from exc

    def _read_all(self) -> list[KnowledgeRecord]:
        """كل السجلّات — مذاكَرةً على (وقت التعديل، الحجم).

        ═══ العطب المقيس ═══

        كانت تقرأ الملفّ كاملاً وتحلّل كل سطر JSON في **كل نداء**.
        وقاعدة المعرفة ٩٣٥٩ سجلّاً، وبحث التشابه ينادي هذه الدالّة
        خمساً وستّين مرّة للرمز الواحد.

        فالحصيلة **٦٠٨ آلاف تحليل JSON لكل رمز** — قياساً بالمُشرِّح:
        ٦٠٫٧ ثانية للرمز الواحد. ولمئة وخمسين رمزاً: **ساعتان ونصف**.
        وهو ما بدا «تعليقاً» بعد ‏«150/150‏»: المسح لم يعلّق، كان
        يحلّل واحداً وتسعين مليون سطر JSON.

        والمذاكرة على (mtime, size) لا على الوقت: الملفّ يُلحَق به
        أثناء المسح نفسه، ومذاكرةٌ بمهلة زمنية كانت ستُرجع سجلّات
        قديمة بعد أوّل كتابة. والتحقّق من حالة الملفّ يجعل الجواب
        صحيحاً دائماً ويُعاد حسابه فقط حين يتغيّر فعلاً.
        """
        if not self.path.exists():
            return []
        try:
            st = self.path.stat()
            key = (str(self.path), st.st_mtime_ns, st.st_size)
        except OSError:
            key = None
        if key is not None:
            hit = _CACHE.get(key)
            if hit is not None:
                return hit

        out: list[KnowledgeRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(KnowledgeRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        if key is not None:
            # مدخلٌ واحد لكل ملف: المفتاح يحمل حالته، فالقديم لا
            # يُستعمل ولا يتراكم.
            _CACHE.clear()
            _CACHE[key] = out
        return out

    def save(self, record: KnowledgeRecord) -> str:
        if not record.record_id:
            record.record_id = f"rec_{uuid.uuid4().hex[:16]}"
        self._append(record.to_dict())
        return record.record_id

    def load(self, record_id: str) -> KnowledgeRecord:
        for rec in self._read_all():
            if rec.record_id == record_id:
                return rec
        raise SnapshotNotFoundError(record_id)

    def search(self, *, kind: SnapshotKind | None = None,
               event_id: str | None = None,
               symbol: str | None = None,
               market: str | None = None,
               timeframe: str | None = None,
               limit: int = 100) -> list[KnowledgeRecord]:
        rows = self._read_all()
        if event_id:
            rows = [r for r in rows if r.event_id == event_id]
        if kind is not None:
            rows = [r for r in rows if r.kind == kind]
        if symbol:
            rows = [r for r in rows if r.payload.get("symbol") == symbol]
        if market:
            rows = [r for r in rows if r.payload.get("market") == market]
        if timeframe:
            rows = [r for r in rows if r.payload.get("timeframe") == timeframe]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]

    def history(self, event_id: str) -> list[KnowledgeRecord]:
        rows = [r for r in self._read_all() if r.event_id == event_id]
        rows.sort(key=lambda r: r.created_at)
        return rows

    def statistics(self, *, market: str | None = None,
                   timeframe: str | None = None) -> dict[str, Any]:
        rows = self.search(market=market, timeframe=timeframe, limit=10_000)
        by_kind: dict[str, int] = {}
        events: set[str] = set()
        symbols: set[str] = set()
        for rec in rows:
            by_kind[rec.kind.value] = by_kind.get(rec.kind.value, 0) + 1
            events.add(rec.event_id)
            sym = rec.payload.get("symbol")
            if sym:
                symbols.add(sym)
        outcomes = [r for r in rows if r.kind == SnapshotKind.OUTCOME]
        rs = [r.payload.get("r_multiple") for r in outcomes
              if r.payload.get("r_multiple") is not None]
        return {
            "total_records": len(rows),
            "unique_events": len(events),
            "unique_symbols": len(symbols),
            "by_kind": by_kind,
            "closed_outcomes": len(outcomes),
            "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def save_snapshot(self, *, kind: SnapshotKind, event_id: str,
                      payload: dict[str, Any],
                      created_at: datetime | None = None) -> str:
        record = KnowledgeRecord(
            record_id=f"rec_{uuid.uuid4().hex[:16]}",
            kind=kind,
            event_id=event_id,
            created_at=created_at or datetime.now(timezone.utc),
            payload=payload,
        )
        return self.save(record)
