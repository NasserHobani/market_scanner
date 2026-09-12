# -*- coding: utf-8 -*-
"""Learning history — append-only store for proposals, hypotheses, reports."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_SCHEMA_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningHistory:
    """Versioned append-only history for all learning artifacts."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = Path(__file__).resolve().parents[2] / "data"
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._proposals_path = self._base / "learning_proposals.jsonl"
        self._hypotheses_path = self._base / "learning_hypotheses.jsonl"
        self._reports_path = self._base / "learning_reports.jsonl"

    def save_proposal(self, proposal: dict[str, Any]) -> str:
        return self._append(self._proposals_path, proposal, "proposal_id", "prop_")

    def save_hypothesis(self, hypothesis: dict[str, Any]) -> str:
        return self._append(self._hypotheses_path, hypothesis, "hypothesis_id", "hyp_")

    def save_report(self, report: dict[str, Any]) -> str:
        return self._append(self._reports_path, report, "report_id", "lrpt_")

    def list_proposals(self) -> list[dict[str, Any]]:
        return self._read(self._proposals_path)

    def list_hypotheses(self) -> list[dict[str, Any]]:
        return self._read(self._hypotheses_path)

    def list_reports(self) -> list[dict[str, Any]]:
        return self._read(self._reports_path)

    def _append(self, path: Path, record: dict[str, Any],
                id_field: str, prefix: str) -> str:
        record_id = record.get(id_field) or f"{prefix}{uuid.uuid4().hex[:16]}"
        full = {
            id_field: record_id,
            "schema_version": HISTORY_SCHEMA_VERSION,
            "saved_at": _now(),
            **record,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(full, default=str) + "\n")
        return record_id

    def _read(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records
