# -*- coding: utf-8 -*-
"""Structured research reports — no natural language AI."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ResearchReport:
    """Structured research output."""

    report_id: str
    experiment_id: str
    title: str
    dataset_summary: dict[str, Any] = field(default_factory=dict)
    methodology: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    comparison: dict[str, Any] | None = None
    conclusions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "experiment_id": self.experiment_id,
            "title": self.title,
            "dataset_summary": self.dataset_summary,
            "methodology": self.methodology,
            "metrics": self.metrics,
            "comparison": self.comparison,
            "conclusions": list(self.conclusions),
            "warnings": list(self.warnings),
            "limitations": list(self.limitations),
            "generated_at": self.generated_at,
        }


class ReportGenerator:
    """Generate structured research reports from experiment results."""

    def generate(self, *,
                 experiment_id: str,
                 title: str,
                 dataset_summary: dict[str, Any],
                 methodology: dict[str, Any],
                 metrics: dict[str, Any],
                 comparison: dict[str, Any] | None = None,
                 hypothesis_eval: dict[str, Any] | None = None) -> ResearchReport:
        conclusions = self._conclusions(metrics, comparison, hypothesis_eval)
        warnings = self._warnings(metrics, comparison, dataset_summary)
        limitations = self._limitations(dataset_summary, comparison)

        return ResearchReport(
            report_id=f"rpt_{uuid.uuid4().hex[:16]}",
            experiment_id=experiment_id,
            title=title,
            dataset_summary=dataset_summary,
            methodology=methodology,
            metrics=metrics,
            comparison=comparison,
            conclusions=conclusions,
            warnings=warnings,
            limitations=limitations,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    def _conclusions(self, metrics: dict, comparison: dict | None,
                     hypothesis_eval: dict | None) -> list[str]:
        out: list[str] = []
        if comparison:
            winner = comparison.get("winner", "inconclusive")
            out.append(f"Comparison winner by expectancy: {winner}")
            stats = comparison.get("statistics") or {}
            note = stats.get("significance_note")
            if note:
                out.append(note)
        elif metrics:
            exp = metrics.get("treatment", metrics).get("expectancy")
            if exp is not None:
                out.append(f"Treatment expectancy: {exp:+.3f}R")
        if hypothesis_eval:
            out.append(
                f"Hypothesis split: {hypothesis_eval.get('treatment_count', 0)} treatment / "
                f"{hypothesis_eval.get('baseline_count', 0)} baseline"
            )
        return out

    def _warnings(self, metrics: dict, comparison: dict | None,
                  dataset_summary: dict) -> list[str]:
        warnings: list[str] = []
        n = dataset_summary.get("closed_count") or dataset_summary.get("count") or 0
        if n < 20:
            warnings.append(f"Low sample size (n={n}) — results not reliable")
        if comparison:
            for note in comparison.get("notes") or []:
                if "below reliability" in note.lower():
                    warnings.append(note)
        for group_key in ("treatment", "baseline", "all"):
            g = metrics.get(group_key) or {}
            if g and not g.get("reliable"):
                warnings.append(f"{group_key} group below reliability threshold")
        return warnings

    def _limitations(self, dataset_summary: dict,
                     comparison: dict | None) -> list[str]:
        limits = [
            "Historical performance does not guarantee future results",
            "No transaction costs or slippage modeled",
            "Wilson interval overlap used as significance proxy — not formal hypothesis test",
        ]
        if dataset_summary.get("filters_applied"):
            limits.append(
                f"Dataset filtered: {', '.join(dataset_summary['filters_applied'])}"
            )
        if comparison and not (comparison.get("statistics") or {}).get("both_reliable"):
            limits.append("Comparison groups may lack statistical power")
        return limits
