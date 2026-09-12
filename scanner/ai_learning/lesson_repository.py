# -*- coding: utf-8 -*-
"""Lesson repository — versioned lesson storage with fingerprint deduplication."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .lesson_fingerprint import fingerprint_from_lesson

LESSON_SCHEMA_VERSION = "1.1.0"

LESSON_STATUSES = ("NEW", "UNDER_REVIEW", "VALIDATED", "REJECTED", "ARCHIVED")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_merge(a: list[str], b: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in list(a) + list(b):
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


class LessonRepository:
    """Persist structured lessons with fingerprint-based upsert."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[2] / "data" / "learning_lessons.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, lesson: dict[str, Any]) -> str:
        lesson_id = lesson.get("lesson_id") or f"lesson_{uuid.uuid4().hex[:16]}"
        fp = lesson.get("fingerprint") or fingerprint_from_lesson(lesson)
        now = _now()
        full = {
            "lesson_id": lesson_id,
            "schema_version": LESSON_SCHEMA_VERSION,
            "status": lesson.get("status", "NEW"),
            "fingerprint": fp,
            "created_at": lesson.get("created_at") or now,
            "first_seen": lesson.get("first_seen") or now,
            "last_seen": lesson.get("last_seen") or now,
            **lesson,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, default=str) + "\n")
        return lesson_id

    def find_by_fingerprint(self, fingerprint: str) -> dict[str, Any] | None:
        best = None
        for record in self._iter():
            if record.get("fingerprint") == fingerprint:
                if best is None or (record.get("last_seen", "") >= best.get("last_seen", "")):
                    best = record
        return best

    def upsert(self, lesson: dict[str, Any]) -> tuple[str, bool]:
        """Return (lesson_id, created). Updates existing lesson when fingerprint matches."""
        fp = lesson.get("fingerprint") or fingerprint_from_lesson(lesson)
        lesson["fingerprint"] = fp
        existing = self.find_by_fingerprint(fp)
        if existing:
            merged = self._merge_lesson(existing, lesson)
            self._replace_record(existing["lesson_id"], merged)
            return existing["lesson_id"], False
        return self.save(lesson), True

    def _merge_lesson(self, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        new_examples = incoming.get("trade_examples") or []
        old_examples = existing.get("trade_examples") or []
        seen_trades = {ex.get("trade_id") for ex in old_examples}
        merged_examples = list(old_examples)
        for ex in new_examples:
            tid = ex.get("trade_id")
            if tid and tid not in seen_trades:
                merged_examples.append(ex)
                seen_trades.add(tid)

        new_sample = max(
            int(existing.get("sample_size") or 0),
            int(incoming.get("sample_size") or 0),
            len(merged_examples),
        )

        merged = {**existing, **incoming}
        merged.update({
            "lesson_id": existing["lesson_id"],
            "created_at": existing.get("created_at") or incoming.get("created_at"),
            "first_seen": existing.get("first_seen") or incoming.get("first_seen") or now,
            "last_seen": now,
            "sample_size": new_sample,
            "supporting_evidence": _unique_merge(
                existing.get("supporting_evidence") or [],
                incoming.get("supporting_evidence") or incoming.get("evidence") or [],
            )[:20],
            "evidence": _unique_merge(
                existing.get("evidence") or [],
                incoming.get("evidence") or [],
            )[:30],
            "trade_examples": merged_examples[:30],
            "affected_markets": _unique_merge(
                existing.get("affected_markets") or [],
                incoming.get("affected_markets") or [],
            ),
            "affected_symbols": _unique_merge(
                existing.get("affected_symbols") or [],
                incoming.get("affected_symbols") or [],
            ),
            "affected_timeframes": _unique_merge(
                existing.get("affected_timeframes") or [],
                incoming.get("affected_timeframes") or [],
            ),
            "affected_strategies": _unique_merge(
                existing.get("affected_strategies") or [],
                incoming.get("affected_strategies") or [],
            ),
            "affected_providers": _unique_merge(
                existing.get("affected_providers") or [],
                incoming.get("provider", ""),
            ),
            "status": existing.get("status", "NEW"),
        })
        return merged

    def load(self, lesson_id: str) -> dict[str, Any] | None:
        for record in self._iter():
            if record.get("lesson_id") == lesson_id:
                return record
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """Latest record per fingerprint (backward compatible with legacy duplicates)."""
        by_fp: dict[str, dict[str, Any]] = {}
        legacy: list[dict[str, Any]] = []
        for record in self._iter():
            fp = record.get("fingerprint")
            if not fp:
                legacy.append(record)
                continue
            prev = by_fp.get(fp)
            if prev is None or (record.get("last_seen", "") >= prev.get("last_seen", "")):
                by_fp[fp] = record
        return list(by_fp.values()) + legacy

    def by_status(self, status: str) -> list[dict[str, Any]]:
        return [r for r in self.list_all() if r.get("status") == status]

    def update_status(self, lesson_id: str, status: str) -> bool:
        if status not in LESSON_STATUSES:
            return False
        records = list(self._iter())
        found = False
        for record in records:
            if record.get("lesson_id") == lesson_id:
                record["status"] = status
                record["status_updated_at"] = _now()
                found = True
                break
        if found:
            self._rewrite(records)
        return found

    def count(self) -> int:
        return len(self.list_all())

    def _replace_record(self, lesson_id: str, updated: dict[str, Any]) -> None:
        records = list(self._iter())
        for i, record in enumerate(records):
            if record.get("lesson_id") == lesson_id:
                records[i] = updated
                break
        else:
            records.append(updated)
        self._rewrite(records)

    def _iter(self):
        if not self._path.exists():
            return
        with open(self._path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def _rewrite(self, records: list[dict[str, Any]]) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, default=str) + "\n")
