# -*- coding: utf-8 -*-
"""Hypothesis engine — declarative, reproducible hypothesis testing."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Hypothesis:
    """Testable research hypothesis — no hardcoded assumptions."""

    hypothesis_id: str
    title: str
    description: str = ""
    filter_type: str = "factor"       # factor | market | timeframe | regime | custom
    filter_key: str = ""              # e.g. htf, crypto, 4h
    filter_value: Any = None
    comparison_mode: str = "with_without"  # with_without | group_vs_group
    baseline_label: str = "without"
    treatment_label: str = "with"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypothesis_id": self.hypothesis_id,
            "title": self.title,
            "description": self.description,
            "filter_type": self.filter_type,
            "filter_key": self.filter_key,
            "filter_value": self.filter_value,
            "comparison_mode": self.comparison_mode,
            "baseline_label": self.baseline_label,
            "treatment_label": self.treatment_label,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> Hypothesis:
        return cls(
            hypothesis_id=row.get("hypothesis_id") or row.get("id") or "hyp_unknown",
            title=row.get("title") or "",
            description=row.get("description") or "",
            filter_type=row.get("filter_type") or "factor",
            filter_key=row.get("filter_key") or "",
            filter_value=row.get("filter_value"),
            comparison_mode=row.get("comparison_mode") or "with_without",
            baseline_label=row.get("baseline_label") or "without",
            treatment_label=row.get("treatment_label") or "with",
        )


FilterFn = Callable[[dict], bool]


class HypothesisEngine:
    """Evaluate hypotheses against trade rows — deterministic filters only."""

    def split(self, rows: list[dict],
              hypothesis: Hypothesis) -> tuple[list[dict], list[dict]]:
        """Return (treatment, baseline) groups."""
        predicate = self._build_predicate(hypothesis)
        treatment = [r for r in rows if predicate(r)]
        baseline = [r for r in rows if not predicate(r)]
        return treatment, baseline

    def evaluate(self, rows: list[dict],
                 hypothesis: Hypothesis) -> dict[str, Any]:
        treatment, baseline = self.split(rows, hypothesis)
        return {
            "hypothesis": hypothesis.to_dict(),
            "treatment_count": len(treatment),
            "baseline_count": len(baseline),
            "treatment_label": hypothesis.treatment_label,
            "baseline_label": hypothesis.baseline_label,
            "filter_description": self._describe(hypothesis),
        }

    def _build_predicate(self, hypothesis: Hypothesis) -> FilterFn:
        ft = hypothesis.filter_type
        key = hypothesis.filter_key
        val = hypothesis.filter_value

        if ft == "factor":
            return lambda r: key in (r.get("factors") or [])
        if ft == "market":
            return lambda r: (r.get("market") or "") == key
        if ft == "timeframe":
            return lambda r: (r.get("timeframe") or "") == key
        if ft == "regime":
            return lambda r: (r.get("grade") or r.get("regime") or "") == key
        if ft == "status_won":
            return lambda r: r.get("status") == "won"
        if ft == "status_lost":
            return lambda r: r.get("status") == "lost"
        if ft == "custom_field":
            return lambda r: r.get(key) == val
        return lambda r: True

    def _describe(self, hypothesis: Hypothesis) -> str:
        return (
            f"{hypothesis.filter_type}:{hypothesis.filter_key}"
            f"={hypothesis.filter_value}" if hypothesis.filter_value is not None
            else f"{hypothesis.filter_type}:{hypothesis.filter_key}"
        )
