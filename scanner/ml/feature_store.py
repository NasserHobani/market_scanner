# -*- coding: utf-8 -*-
"""Feature store — join feature snapshots with trade/outcome rows."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scanner.tracking import LOST, WON

from .feature_vector import FeatureVector, FeatureVectorBuilder
from .label_store import LabelStore


@dataclass
class MLDatasetRow:
    """Single joined row: features + labels + identifiers."""

    event_id: str
    snapshot_id: str
    features: dict[str, Any] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    missing_features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "snapshot_id": self.snapshot_id,
            **self.features,
            **self.labels,
            "_meta": dict(self.meta),
            "_missing_features": list(self.missing_features),
        }


@dataclass
class MLDataset:
    """In-memory ML dataset ready for validation and export."""

    dataset_id: str
    rows: list[MLDatasetRow] = field(default_factory=list)
    column_order: list[str] = field(default_factory=list)
    label_columns: list[str] = field(default_factory=list)
    filters_applied: list[str] = field(default_factory=list)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.rows]


class FeatureStore:
    """Prepare ML rows by joining snapshots with trade outcomes.

    Never reads raw storage — caller provides all data.
  """

    def __init__(self,
                 vector_builder: FeatureVectorBuilder | None = None,
                 label_store: LabelStore | None = None) -> None:
        self._vectors = vector_builder or FeatureVectorBuilder()
        self._labels = label_store or LabelStore()

    def build_rows(self, *,
                   feature_snapshots: list[dict[str, Any]],
                   trade_rows: list[dict[str, Any]],
                   outcome_rows: list[dict[str, Any]] | None = None,
                   join_key: str = "feature_snapshot_id",
                   completed_only: bool = True) -> list[MLDatasetRow]:
        """Join feature snapshots to trade rows via join_key."""
        snap_by_id = {s.get("snapshot_id"): s for s in feature_snapshots}
        snap_by_event = {s.get("event_id"): s for s in feature_snapshots}

        outcomes_by_event: dict[str, dict] = {}
        if outcome_rows:
            for o in outcome_rows:
                eid = o.get("event_id") or ""
                if eid:
                    outcomes_by_event[eid] = o

        result: list[MLDatasetRow] = []
        for trade in trade_rows:
            if completed_only and trade.get("status") not in (WON, LOST):
                continue

            snap_id = trade.get(join_key) or trade.get("snapshot_id") or ""
            event_id = trade.get("event_id") or ""

            snapshot = snap_by_id.get(snap_id) or snap_by_event.get(event_id)
            if not snapshot:
                continue

            vector = self._vectors.from_feature_snapshot(snapshot)
            outcome = outcomes_by_event.get(event_id)
            labels = self._labels.extract(trade, outcome_row=outcome)

            result.append(MLDatasetRow(
                event_id=event_id or snapshot.get("event_id", ""),
                snapshot_id=snap_id or snapshot.get("snapshot_id", ""),
                features=vector.values,
                labels=labels,
                meta={
                    "market": snapshot.get("market") or trade.get("market"),
                    "timeframe": snapshot.get("timeframe") or trade.get("timeframe"),
                    "symbol": snapshot.get("symbol") or trade.get("symbol"),
                },
                missing_features=vector.missing,
            ))
        return result

    def build_dataset(self, *,
                      dataset_id: str,
                      feature_snapshots: list[dict[str, Any]],
                      trade_rows: list[dict[str, Any]],
                      outcome_rows: list[dict[str, Any]] | None = None,
                      filters_applied: list[str] | None = None,
                      join_key: str = "feature_snapshot_id",
                      completed_only: bool = True) -> MLDataset:
        rows = self.build_rows(
            feature_snapshots=feature_snapshots,
            trade_rows=trade_rows,
            outcome_rows=outcome_rows,
            join_key=join_key,
            completed_only=completed_only,
        )
        column_order: list[str] = []
        if rows:
            column_order = sorted(rows[0].features.keys())
        label_columns = list(self._labels.names()) if rows else []
        return MLDataset(
            dataset_id=dataset_id,
            rows=rows,
            column_order=column_order,
            label_columns=label_columns,
            filters_applied=filters_applied or [],
        )
