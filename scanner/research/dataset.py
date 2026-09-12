# -*- coding: utf-8 -*-
"""Dataset builder — experiments never read raw storage directly."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from scanner.tracking import LOST, WON


def _now() -> str:
    """طابع زمني بمنطقة زمنية صريحة.

    ‏``datetime.utcnow()`` كانت تُعيد وقتاً **بلا منطقة زمنية** يحمل
    قيمة UTC، فيُلحَق به ``"Z"`` يدوياً. وهذا مصدر عطب متكرّر: الوقت
    الساذج يُقارَن بوقت واعٍ فيرفع استثناءً، أو — وهو أسوأ — يُفسَّر
    بالتوقيت المحلّي فينزاح ساعات بلا أي علامة.

    والصيغة هنا ``+00:00`` لتطابق ``jobs.py`` و``experiment.py``؛ كان
    هذا الملف وحده يكتب ``Z`` فيختلف ترتيب النصّ عند الفرز.
    """
    return datetime.now(timezone.utc).isoformat()



@dataclass
class Dataset:
    """Immutable research dataset with metadata."""

    dataset_id: str
    label: str
    rows: list[dict] = field(default_factory=list)
    filters_applied: list[str] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.rows)

    @property
    def closed_count(self) -> int:
        return sum(1 for r in self.rows if r.get("status") in (WON, LOST))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "label": self.label,
            "count": self.count,
            "closed_count": self.closed_count,
            "filters_applied": list(self.filters_applied),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    def fingerprint(self) -> str:
        meta = {
            "label": self.label,
            "count": self.count,
            "filters": self.filters_applied,
        }
        raw = json.dumps(meta, sort_keys=True).encode("utf-8")
        return f"ds_{hashlib.sha256(raw).hexdigest()[:16]}"


class DatasetBuilder:
    """Build reusable datasets from provided trade rows."""

    def from_rows(self, rows: Iterable[dict], *,
                  label: str = "all_trades") -> Dataset:
        rows = list(rows)
        return Dataset(
            dataset_id=f"ds_{label}_{len(rows)}",
            label=label,
            rows=rows,
            filters_applied=["source:provided"],
            created_at=_now(),
            metadata={"source": "provided", "total": len(rows)},
        )

    def completed(self, dataset: Dataset) -> Dataset:
        rows = [r for r in dataset.rows if r.get("status") in (WON, LOST)]
        return self._derive(dataset, rows, "completed_trades")

    def winners(self, dataset: Dataset) -> Dataset:
        rows = [r for r in dataset.rows if r.get("status") == WON]
        return self._derive(dataset, rows, "winning_trades")

    def losers(self, dataset: Dataset) -> Dataset:
        rows = [r for r in dataset.rows if r.get("status") == LOST]
        return self._derive(dataset, rows, "losing_trades")

    def by_market(self, dataset: Dataset, market: str) -> Dataset:
        rows = [r for r in dataset.rows if r.get("market") == market]
        return self._derive(dataset, rows, f"market_{market}")

    def by_timeframe(self, dataset: Dataset, timeframe: str) -> Dataset:
        rows = [r for r in dataset.rows if r.get("timeframe") == timeframe]
        return self._derive(dataset, rows, f"timeframe_{timeframe}")

    def by_factor(self, dataset: Dataset, factor: str) -> Dataset:
        rows = [r for r in dataset.rows
                if factor in (r.get("factors") or [])]
        return self._derive(dataset, rows, f"factor_{factor}")

    def by_regime(self, dataset: Dataset, regime: str) -> Dataset:
        rows = [r for r in dataset.rows
                if (r.get("grade") or r.get("regime") or "") == regime]
        return self._derive(dataset, rows, f"regime_{regime}")

    def by_similarity_group(self, dataset: Dataset,
                            event_ids: list[str]) -> Dataset:
        id_set = set(event_ids)
        rows = [r for r in dataset.rows if r.get("event_id") in id_set]
        return self._derive(dataset, rows, "similarity_group")

    def _derive(self, parent: Dataset, rows: list[dict],
                label: str) -> Dataset:
        return Dataset(
            dataset_id=f"{parent.dataset_id}_{label}",
            label=label,
            rows=rows,
            filters_applied=parent.filters_applied + [label],
            created_at=_now(),
            metadata={**parent.metadata, "parent": parent.dataset_id, "filtered_to": len(rows)},
        )
