# -*- coding: utf-8 -*-
"""Dataset export — CSV, JSON, Parquet (interface)."""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from .feature_store import MLDataset
from .metadata import ExportMetadata, FEATURE_VERSION, LABEL_VERSION, SCHEMA_VERSION


ExportFormat = Literal["csv", "json", "parquet"]


@dataclass
class ExportResult:
    """Result of a dataset export operation."""

    path: str
    format: str
    row_count: int
    metadata: ExportMetadata

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "format": self.format,
            "row_count": self.row_count,
            "metadata": self.metadata.to_dict(),
        }


class DatasetExporter:
    """Export ML datasets with attached metadata."""

    def export(self, dataset: MLDataset, path: Path | str, *,
               fmt: ExportFormat = "csv",
               include_meta_columns: bool = False) -> ExportResult:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "csv":
            return self._export_csv(dataset, path, include_meta_columns)
        if fmt == "json":
            return self._export_json(dataset, path, include_meta_columns)
        if fmt == "parquet":
            return self._export_parquet(dataset, path, include_meta_columns)
        raise ValueError(f"unsupported format: {fmt}")

    def _export_csv(self, dataset: MLDataset, path: Path,
                    include_meta: bool) -> ExportResult:
        rows = dataset.to_dicts()
        if not rows:
            path.write_text("", encoding="utf-8")
            meta_path = path.with_suffix(".meta.json")
            meta = self._build_metadata(dataset, "csv", [])
            meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
            return ExportResult(str(path), "csv", 0, meta)

        columns = self._column_order(dataset, rows[0], include_meta)
        with path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                flat = {k: v for k, v in row.items() if not k.startswith("_")}
                if include_meta:
                    flat.update({k: v for k, v in row.get("_meta", {}).items()})
                writer.writerow({c: flat.get(c) for c in columns})

        meta = self._build_metadata(dataset, "csv", columns)
        meta_path = path.with_suffix(".meta.json")
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")
        return ExportResult(str(path), "csv", len(rows), meta)

    def _export_json(self, dataset: MLDataset, path: Path,
                     include_meta: bool) -> ExportResult:
        rows = dataset.to_dicts()
        columns = self._column_order(dataset, rows[0] if rows else {}, include_meta)
        payload = {
            "metadata": self._build_metadata(dataset, "json", columns).to_dict(),
            "columns": columns,
            "rows": [
                {c: self._row_value(r, c, include_meta) for c in columns}
                for r in rows
            ],
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
        meta = ExportMetadata(**payload["metadata"])
        return ExportResult(str(path), "json", len(rows), meta)

    def _export_parquet(self, dataset: MLDataset, path: Path,
                        include_meta: bool) -> ExportResult:
        """Parquet export interface — implementation deferred.

        Writes a JSON sidecar with schema and defers binary parquet to future sprint.
        """
        rows = dataset.to_dicts()
        columns = self._column_order(dataset, rows[0] if rows else {}, include_meta)
        meta = self._build_metadata(dataset, "parquet", columns)
        sidecar = path.with_suffix(".parquet.schema.json")
        sidecar.write_text(json.dumps({
            **meta.to_dict(),
            "status": "deferred",
            "note": "Parquet binary export requires pyarrow — use CSV or JSON for now",
            "columns": columns,
            "row_count": len(rows),
        }, indent=2), encoding="utf-8")
        return ExportResult(str(sidecar), "parquet", len(rows), meta)

    def _build_metadata(self, dataset: MLDataset, fmt: str,
                        columns: list[str]) -> ExportMetadata:
        from datetime import datetime, timezone
        return ExportMetadata(
            dataset_id=dataset.dataset_id,
            format=fmt,
            exported_at=datetime.now(timezone.utc).isoformat(),
            schema_version=SCHEMA_VERSION,
            feature_version=FEATURE_VERSION,
            label_version=LABEL_VERSION,
            column_order=columns,
            row_count=dataset.row_count,
        )

    def _column_order(self, dataset: MLDataset, sample: dict,
                      include_meta: bool) -> list[str]:
        cols = ["event_id", "snapshot_id"]
        if dataset.column_order:
            cols += [c for c in dataset.column_order if c not in cols]
        else:
            feature_cols = [k for k in sample if not k.startswith("_")
                            and k not in cols and not k.startswith("label_")]
            cols += sorted(feature_cols)
        cols += [c for c in dataset.label_columns if c not in cols]
        if include_meta:
            cols += ["market", "timeframe", "symbol"]
        return cols

    @staticmethod
    def _row_value(row: dict, col: str, include_meta: bool) -> Any:
        if col in row:
            return row[col]
        if include_meta and col in (row.get("_meta") or {}):
            return row["_meta"][col]
        return None
