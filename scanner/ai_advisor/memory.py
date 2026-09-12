# -*- coding: utf-8 -*-
"""Persistent advisor memory — platform-owned, not user-owned."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvisorMemory:
    """Append-only JSONL store for advisor review records.

    Each record captures the full audit trail:
    Decision Package ID, prompt version, provider, model,
    response, acceptance status, and later performance.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[2] / "data" / "advisor_memory.jsonl"
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def save(self, *,
             package_id: str,
             event_id: str,
             prompt_version: str,
             provider_id: str,
             model_name: str,
             response: dict[str, Any],
             accepted: bool,
             rejected: bool = False,
             rejection_reason: str = "",
             execution_result: dict[str, Any] | None = None,
             later_performance: dict[str, Any] | None = None,
             review_id: str = "",
             trade_id: str = "",
             symbol: str = "",
             market: str = "",
             timeframe: str = "") -> str:
        record_id = review_id or f"mem_{uuid.uuid4().hex[:16]}"
        record = {
            "record_id": record_id,
            "package_id": package_id,
            "event_id": event_id,
            "trade_id": trade_id,
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "prompt_version": prompt_version,
            "provider_id": provider_id,
            "model_name": model_name,
            "response": response,
            "accepted": accepted,
            "rejected": rejected,
            "rejection_reason": rejection_reason,
            "execution_result": execution_result or {},
            "later_performance": later_performance or {},
            "saved_at": _now(),
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
        return record_id

    def load(self, record_id: str) -> dict[str, Any] | None:
        for record in self._iter_records():
            if record.get("record_id") == record_id:
                return record
        return None

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        records = list(self._iter_records())
        return records[-limit:]

    def update_performance(self, record_id: str,
                           performance: dict[str, Any]) -> bool:
        records = list(self._iter_records())
        updated = False
        for record in records:
            if record.get("record_id") == record_id:
                record["later_performance"] = performance
                record["performance_updated_at"] = _now()
                updated = True
                break
        if updated:
            self._rewrite(records)
        return updated

    def find_latest_for_symbol(self, *, symbol: str, market: str,
                               timeframe: str = "") -> dict[str, Any] | None:
        """Most recent accepted review for a symbol (for trade-close evaluation)."""
        matches = []
        for record in self._iter_records():
            if not record.get("accepted"):
                continue
            if record.get("symbol") != symbol or record.get("market") != market:
                continue
            if timeframe and record.get("timeframe") and record.get("timeframe") != timeframe:
                continue
            matches.append(record)
        return matches[-1] if matches else None

    def find_by_trade_id(self, trade_id: str) -> dict[str, Any] | None:
        for record in self._iter_records():
            if str(record.get("trade_id", "")) == str(trade_id):
                return record
        return None

    def count(self) -> int:
        return sum(1 for _ in self._iter_records())

    def _iter_records(self):
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
