# -*- coding: utf-8 -*-
"""Standardized label definitions and extraction."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scanner.tracking import LOST, WON


class LabelType(str, Enum):
    BINARY = "binary"
    REGRESSION = "regression"
    MULTICLASS = "multiclass"


class LabelName(str, Enum):
    WINNER = "label_winner"
    LOSER = "label_loser"
    BREAK_EVEN = "label_break_even"
    R_MULTIPLE = "label_r_multiple"
    BINARY_WIN = "label_binary_win"
    OUTCOME_CLASS = "label_outcome_class"


@dataclass(frozen=True)
class LabelDefinition:
    """Schema definition for a single label."""

    name: str
    description: str
    label_type: str
    version: str = "1.0.0"
    source_layer: str = "outcome"
    deterministic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "label_type": self.label_type,
            "version": self.version,
            "source_layer": self.source_layer,
            "deterministic": self.deterministic,
        }


_BUILTIN_LABELS: list[LabelDefinition] = [
    LabelDefinition(LabelName.WINNER.value, "Binary: trade was a winner",
                    LabelType.BINARY.value, source_layer="tracking"),
    LabelDefinition(LabelName.LOSER.value, "Binary: trade was a loser",
                    LabelType.BINARY.value, source_layer="tracking"),
    LabelDefinition(LabelName.BREAK_EVEN.value, "Binary: trade broke even",
                    LabelType.BINARY.value, source_layer="outcome"),
    LabelDefinition(LabelName.R_MULTIPLE.value, "Regression: R-multiple outcome",
                    LabelType.REGRESSION.value, source_layer="tracking"),
    LabelDefinition(LabelName.BINARY_WIN.value, "Binary: r_multiple > 0",
                    LabelType.BINARY.value, source_layer="tracking"),
    LabelDefinition(LabelName.OUTCOME_CLASS.value, "Multiclass: winner/loser/break_even",
                    LabelType.MULTICLASS.value, source_layer="outcome"),
]


class LabelStore:
    """Manage label definitions and deterministic extraction."""

    def __init__(self) -> None:
        self._labels: dict[str, LabelDefinition] = {
            l.name: l for l in _BUILTIN_LABELS
        }

    def register(self, label: LabelDefinition) -> None:
        self._labels[label.name] = label

    def get(self, name: str) -> LabelDefinition | None:
        return self._labels.get(name)

    def list_all(self) -> list[LabelDefinition]:
        return sorted(self._labels.values(), key=lambda l: l.name)

    def names(self) -> list[str]:
        return sorted(self._labels.keys())

    def extract(self, trade_row: dict[str, Any], *,
                outcome_row: dict[str, Any] | None = None) -> dict[str, Any]:
        """Extract all labels from a trade/outcome row — deterministic."""
        status = trade_row.get("status") or (outcome_row or {}).get("status") or ""
        r_mult = trade_row.get("r_multiple")
        if r_mult is None and outcome_row:
            r_mult = outcome_row.get("r_multiple")

        outcome_class = (outcome_row or {}).get("outcome_class") or ""
        if not outcome_class:
            if status == WON:
                outcome_class = "winner"
            elif status == LOST:
                outcome_class = "loser"
            elif r_mult is not None and r_mult == 0:
                outcome_class = "break_even"

        is_winner = status == WON or (outcome_row or {}).get("profit") is True
        is_loser = status == LOST or (outcome_row or {}).get("loss") is True
        is_be = (outcome_row or {}).get("break_even") is True or (
            r_mult is not None and r_mult == 0 and not is_winner and not is_loser
        )

        labels: dict[str, Any] = {
            LabelName.WINNER.value: 1 if is_winner else 0,
            LabelName.LOSER.value: 1 if is_loser else 0,
            LabelName.BREAK_EVEN.value: 1 if is_be else 0,
            LabelName.R_MULTIPLE.value: float(r_mult) if r_mult is not None else None,
            LabelName.BINARY_WIN.value: (1 if (r_mult is not None and r_mult > 0) else
                                         0 if r_mult is not None else None),
            LabelName.OUTCOME_CLASS.value: outcome_class or None,
        }
        return labels

    def extract_batch(self, trade_rows: list[dict],
                      outcomes: dict[str, dict] | None = None) -> list[dict[str, Any]]:
        outcomes = outcomes or {}
        return [
            self.extract(row, outcome_row=outcomes.get(row.get("event_id", "")))
            for row in trade_rows
        ]

    def schema_version(self) -> str:
        versions = sorted({l.version for l in self._labels.values()})
        return versions[-1] if versions else "1.0.0"
