# -*- coding: utf-8 -*-
"""Advisor evaluation reports — daily base report."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from .advisor_metrics import AdvisorMetrics
from .leaderboard import ProviderLeaderboard

REPORT_VERSION = "1.0.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdvisorReport:
    """Generate daily evaluation report."""

    def __init__(self) -> None:
        self._metrics = AdvisorMetrics()
        self._leaderboard = ProviderLeaderboard()

    def generate(self, records: list[dict[str, Any]], *,
                 period: str = "daily",
                 since: str = "") -> dict[str, Any]:
        filtered = self._filter_period(records, period, since)
        metrics = self._metrics.compute(filtered)
        leaderboard = self._leaderboard.compute(filtered)

        overall = metrics.get("overall_accuracy", {})
        score = overall.get("value") or 0

        return {
            "period": period,
            "report_version": REPORT_VERSION,
            "generated_at": _now(),
            "overall_advisor_score": score,
            "grade": self._grade(score),
            "provider_ranking": leaderboard,
            "best_markets": self._best_worst(metrics.get("market_accuracy", {}), best=True),
            "worst_markets": self._best_worst(metrics.get("market_accuracy", {}), best=False),
            "best_timeframes": self._best_worst(metrics.get("timeframe_accuracy", {}), best=True),
            "most_common_errors": self._common_errors(filtered),
            "hallucination_summary": self._hallucination_summary(filtered),
            "recommendations": self._recommendations(metrics, filtered),
            "metrics": metrics,
            "sample_size": len(filtered),
        }

    def _filter_period(self, records: list[dict[str, Any]],
                       period: str, since: str) -> list[dict[str, Any]]:
        if period == "all":
            return records
        if since:
            return [r for r in records if (r.get("execution_date") or "") >= since]
        if period == "daily":
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            return [r for r in records if (r.get("execution_date") or "").startswith(today)]
        return records

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        if score >= 50:
            return "C"
        if score >= 35:
            return "D"
        return "F"

    @staticmethod
    def _best_worst(group: dict[str, Any], *, best: bool) -> list[dict[str, Any]]:
        items = [
            {"name": k, "accuracy": v.get("value"), "sample_size": v.get("sample_size", 0)}
            for k, v in group.items()
            if v.get("value") is not None and v.get("sample_size", 0) > 0
        ]
        items.sort(key=lambda x: x["accuracy"] or 0, reverse=best)
        return items[:5]

    @staticmethod
    def _common_errors(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        errors = Counter()
        for r in records:
            if r.get("advisor_correct"):
                continue
            if r.get("hallucination"):
                errors["hallucination"] += 1
            elif r.get("missed_warning"):
                errors["missed_warning"] += 1
            elif r.get("false_warning"):
                errors["false_warning"] += 1
            elif r.get("advisor_agreement") == "agree":
                errors["wrong_agreement"] += 1
            elif r.get("advisor_agreement") == "disagree":
                errors["wrong_disagreement"] += 1
            else:
                errors["partial_agreement"] += 1
        return [{"error": k, "count": v} for k, v in errors.most_common()]

    @staticmethod
    def _hallucination_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(records)
        hall = sum(1 for r in records if r.get("hallucination"))
        return {
            "count": hall,
            "rate": round(hall / total * 100, 1) if total else 0,
            "sample_size": total,
        }

    @staticmethod
    def _recommendations(metrics: dict[str, Any],
                         records: list[dict[str, Any]]) -> list[str]:
        recs = []
        hall = metrics.get("hallucination_rate", {})
        if (hall.get("value") or 0) > 10:
            recs.append("Hallucination rate exceeds 10% — tighten grounding validation.")
        missed = metrics.get("missed_warnings", {})
        if (missed.get("value") or 0) > 20:
            recs.append("High missed-warning rate — prompt should emphasize risk detection.")
        cal = metrics.get("confidence_calibration", [])
        overconfident = [b for b in cal if (b.get("calibration_error") or 0) < -15]
        if overconfident:
            recs.append("Advisor is overconfident in some buckets — recalibrate confidence prompts.")
        if not records:
            recs.append("No evaluations yet — run evaluation after trades close.")
        if not recs:
            recs.append("Advisor performance within acceptable bounds.")
        return recs

    def to_ui_model(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        from .sample_reliability import annotate_metric, evaluation_ui_envelope, reliability_state

        report = self.generate(records, period="all")
        metrics = report.get("metrics", {})
        overall = metrics.get("overall_accuracy", {})
        sample_size = report.get("sample_size", len(records))
        envelope = evaluation_ui_envelope(
            sample_size=sample_size,
            overall_accuracy=overall.get("value"),
            advisor_score=report.get("overall_advisor_score"),
            grade=report.get("grade", ""),
        )
        provider_lb = []
        for entry in report.get("provider_ranking", []):
            provider_lb.append({
                **entry,
                "accuracy_metric": annotate_metric({
                    "value": entry.get("accuracy"),
                    "sample_size": entry.get("review_count") or entry.get("sample_size", 0),
                }),
            })
        return {
            "available": True,
            "advisor_score": report.get("overall_advisor_score"),
            "grade": report.get("grade"),
            "sample_size": sample_size,
            "overall_accuracy": overall.get("value"),
            "confidence_interval": overall.get("confidence_interval"),
            "reliability_state": envelope["reliability_state"],
            "reliability_label": envelope["reliability_label"],
            "reliability_label_ar": envelope["reliability_label_ar"],
            "interpretable": envelope["interpretable"],
            "accuracy_caution": envelope["accuracy_caution"],
            "provider_leaderboard": provider_lb,
            "accuracy_trend": self._accuracy_trend(records),
            "calibration_curve": metrics.get("confidence_calibration", []),
            "recent_evaluations": records[-10:],
            "hallucination_summary": annotate_metric(report.get("hallucination_summary")),
            "recommendations": report.get("recommendations"),
            "metrics": metrics,
        }

    @staticmethod
    def _accuracy_trend(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_date: dict[str, list] = {}
        for r in records:
            date = (r.get("execution_date") or r.get("evaluated_at", ""))[:10]
            if date:
                by_date.setdefault(date, []).append(r)
        trend = []
        for date in sorted(by_date):
            items = by_date[date]
            correct = sum(1 for r in items if r.get("advisor_correct"))
            trend.append({
                "date": date,
                "accuracy": round(correct / len(items) * 100, 1) if items else 0,
                "sample_size": len(items),
            })
        return trend
