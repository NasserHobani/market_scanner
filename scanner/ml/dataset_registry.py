# -*- coding: utf-8 -*-
"""Dataset registry — version every exported dataset."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .metadata import (
    FEATURE_VERSION,
    LABEL_VERSION,
    SCHEMA_VERSION,
    DatasetMetadata,
)

DEFAULT_REGISTRY = Path("data/ml/datasets/registry.jsonl")


def new_dataset_id() -> str:
    return f"mls_{uuid.uuid4().hex[:16]}"


def _fingerprint(meta: dict[str, Any]) -> str:
    raw = json.dumps(meta, sort_keys=True).encode("utf-8")
    return f"mlfp_{hashlib.sha256(raw).hexdigest()[:16]}"


@dataclass
class RegisteredDataset:
    """Registry entry linking dataset metadata to storage path."""

    metadata: DatasetMetadata
    storage_path: str = ""
    status: str = "registered"

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.metadata.to_dict(),
            "storage_path": self.storage_path,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> RegisteredDataset:
        meta = DatasetMetadata.from_dict(row)
        return cls(
            metadata=meta,
            storage_path=row.get("storage_path") or "",
            status=row.get("status") or "registered",
        )


class DatasetRegistry:
    """Append-only registry for versioned ML datasets."""

    def __init__(self, path: Path | str = DEFAULT_REGISTRY) -> None:
        self.path = Path(path)

    def register(self, *,
                 dataset_id: str | None = None,
                 row_count: int = 0,
                 feature_count: int = 0,
                 label_columns: list[str] | None = None,
                 filters_applied: list[str] | None = None,
                 research_experiment_id: str = "",
                 storage_path: str = "",
                 schema_version: str = SCHEMA_VERSION,
                 feature_version: str = FEATURE_VERSION,
                 label_version: str = LABEL_VERSION,
                 extra: dict[str, Any] | None = None) -> RegisteredDataset:
        did = dataset_id or new_dataset_id()
        meta_dict = {
            "dataset_id": did,
            "schema_version": schema_version,
            "feature_version": feature_version,
            "label_version": label_version,
            "row_count": row_count,
            "feature_count": feature_count,
            "label_columns": label_columns or [],
            "filters_applied": filters_applied or [],
            "research_experiment_id": research_experiment_id,
        }
        entry = RegisteredDataset(
            metadata=DatasetMetadata(
                dataset_id=did,
                schema_version=schema_version,
                feature_version=feature_version,
                label_version=label_version,
                research_experiment_id=research_experiment_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                row_count=row_count,
                feature_count=feature_count,
                label_columns=list(label_columns or []),
                filters_applied=list(filters_applied or []),
                fingerprint=_fingerprint(meta_dict),
                extra=dict(extra or {}),
            ),
            storage_path=storage_path,
        )
        self._append(entry)
        return entry

    def _append(self, entry: RegisteredDataset) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False, default=str) + "\n")

    def _read_all(self) -> list[RegisteredDataset]:
        if not self.path.exists():
            return []
        out: list[RegisteredDataset] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(RegisteredDataset.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def load(self, dataset_id: str) -> RegisteredDataset:
        for entry in self._read_all():
            if entry.metadata.dataset_id == dataset_id:
                return entry
        raise KeyError(f"dataset not found: {dataset_id}")

    def history(self, *, limit: int = 50) -> list[RegisteredDataset]:
        rows = self._read_all()
        rows.sort(key=lambda e: e.metadata.created_at or "", reverse=True)
        return rows[:limit]

    def list_ids(self) -> list[str]:
        return [e.metadata.dataset_id for e in self._read_all()]
