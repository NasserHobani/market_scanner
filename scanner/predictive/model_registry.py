# -*- coding: utf-8 -*-
"""Model registry — append-only versioned model records."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model_metadata import ModelMetadata

DEFAULT_REGISTRY = Path("data/predictive/registry.jsonl")


class ModelRegistry:
    """Append-only registry for all trained models."""

    def __init__(self, path: Path | str = DEFAULT_REGISTRY) -> None:
        self.path = Path(path)

    def register(self, metadata: ModelMetadata) -> str:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(metadata.to_dict(), ensure_ascii=False, default=str) + "\n")
        return metadata.model_id

    def _read_all(self) -> list[ModelMetadata]:
        if not self.path.exists():
            return []
        out: list[ModelMetadata] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(ModelMetadata.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def load(self, model_id: str) -> ModelMetadata:
        matches = [m for m in self._read_all() if m.model_id == model_id]
        if not matches:
            raise KeyError(f"model not found in registry: {model_id}")
        return matches[-1]

    def list_all(self, *, limit: int = 50) -> list[ModelMetadata]:
        rows = self._read_all()
        rows.sort(key=lambda m: m.training_timestamp or "", reverse=True)
        return rows[:limit]

    def update_evaluation(self, model_id: str,
                          evaluation_summary: dict[str, Any]) -> None:
        """Append updated record with evaluation summary."""
        meta = self.load(model_id)
        meta.evaluation_summary = evaluation_summary
        self.register(meta)
