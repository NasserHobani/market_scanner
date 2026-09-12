# -*- coding: utf-8 -*-
"""Pipeline execution persistence — append-only JSONL."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .state import PipelineExecution


DEFAULT_STORE = Path("data/pipeline/executions.jsonl")


class PipelineStore:
    """JSONL-backed store for pipeline executions."""

    def __init__(self, path: Path | str = DEFAULT_STORE) -> None:
        self.path = Path(path)

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, row: dict[str, Any]) -> None:
        self._ensure_parent()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def _read_all(self) -> list[PipelineExecution]:
        if not self.path.exists():
            return []
        out: list[PipelineExecution] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(PipelineExecution.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def save(self, execution: PipelineExecution) -> str:
        if not execution.execution_id:
            execution.execution_id = f"pex_{uuid.uuid4().hex[:16]}"
        self._append(execution.to_dict())
        return execution.execution_id

    def load(self, execution_id: str) -> PipelineExecution:
        for ex in self._read_all():
            if ex.execution_id == execution_id:
                return ex
        raise KeyError(f"execution not found: {execution_id}")

    def history(self, *, limit: int = 50,
                pipeline_type: str | None = None,
                event_id: str | None = None) -> list[PipelineExecution]:
        rows = self._read_all()
        if pipeline_type:
            rows = [r for r in rows if r.pipeline_type == pipeline_type]
        if event_id:
            rows = [r for r in rows if r.event_id == event_id]
        rows.sort(key=lambda r: r.started_at, reverse=True)
        return rows[:limit]

    def latest_for_event(self, event_id: str) -> PipelineExecution | None:
        rows = self.history(event_id=event_id, limit=1)
        return rows[0] if rows else None
