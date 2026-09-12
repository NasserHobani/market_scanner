# -*- coding: utf-8 -*-
"""Optimization report generation."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_report_id() -> str:
    return f"optrpt_{uuid.uuid4().hex[:12]}"


class OptimizationReportGenerator:
    """Generate optimization reports with best params, improvement, warnings."""

    def generate(self, *,
                 experiment_id: str,
                 method: str,
                 ranked_results: list[dict[str, Any]],
                 baseline: dict[str, Any] | None = None,
                 leaderboard: dict[str, Any] | None = None,
                 configuration: dict[str, Any] | None = None) -> dict[str, Any]:
        best = ranked_results[0] if ranked_results else {}
        best_params = best.get("params", {})
        warnings: list[str] = []
        limitations: list[str] = []

        closed = best.get("closed_trades") or 0
        if closed < 20:
            warnings.append(f"Low sample size: {closed} closed trades")
        if not best.get("reliable"):
            warnings.append("Win rate confidence interval is wide — results may not be reliable")
        if best.get("profit_factor") is not None and best["profit_factor"] < 1.0:
            warnings.append("Best parameter set has profit factor below 1.0")

        oos = best.get("oos_performance") or {}
        if oos:
            oos_exp = oos.get("expectancy")
            if oos_exp is not None and oos_exp < 0:
                warnings.append("Out-of-sample expectancy is negative")

        improvement: dict[str, Any] = {}
        if baseline:
            for metric in ("expectancy", "win_rate", "profit_factor", "avg_r"):
                b_val = baseline.get(metric)
                n_val = best.get(metric)
                if b_val is not None and n_val is not None and b_val != 0:
                    pct = round((float(n_val) - float(b_val)) / abs(float(b_val)) * 100, 2)
                    improvement[metric] = {"baseline": b_val, "optimized": n_val, "change_pct": pct}

        confidence = self._confidence_score(best)

        if method == "walk_forward":
            wf = best.get("walk_forward") or {}
            if wf.get("mean_oos_expectancy") is not None and wf["mean_oos_expectancy"] < 0:
                limitations.append("Walk-forward mean OOS expectancy is negative")

        return {
            "report_id": new_report_id(),
            "experiment_id": experiment_id,
            "method": method,
            "generated_at": _now(),
            "best_parameters": dict(best_params),
            "best_metrics": {
                "expectancy": best.get("expectancy"),
                "profit_factor": best.get("profit_factor"),
                "avg_r": best.get("avg_r"),
                "win_rate": best.get("win_rate"),
                "max_drawdown_r": best.get("max_drawdown_r"),
                "closed_trades": closed,
                "trade_count": best.get("trade_count"),
            },
            "oos_metrics": dict(oos) if oos else None,
            "improvement": improvement,
            "confidence": confidence,
            "warnings": warnings,
            "limitations": limitations,
            "leaderboard_summary": {
                "total_evaluated": (leaderboard or {}).get("total_evaluated", len(ranked_results)),
                "top_count": len((leaderboard or {}).get("top_strategies", ranked_results[:5])),
            },
            "configuration": dict(configuration or {}),
            "walk_forward": best.get("walk_forward"),
        }

    def _confidence_score(self, result: dict[str, Any]) -> dict[str, Any]:
        score = 0.0
        factors: list[str] = []
        closed = result.get("closed_trades") or 0
        if closed >= 50:
            score += 0.35
            factors.append("adequate_sample")
        elif closed >= 20:
            score += 0.20
            factors.append("moderate_sample")
        else:
            factors.append("low_sample")

        if result.get("reliable"):
            score += 0.25
            factors.append("reliable_win_rate")

        pf = result.get("profit_factor")
        if pf is not None and pf >= 1.5:
            score += 0.20
            factors.append("strong_profit_factor")
        elif pf is not None and pf >= 1.0:
            score += 0.10
            factors.append("positive_profit_factor")

        oos = result.get("oos_performance") or {}
        if oos.get("expectancy") is not None and float(oos["expectancy"]) > 0:
            score += 0.20
            factors.append("positive_oos")

        label = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
        return {"score": round(min(score, 1.0), 3), "label": label, "factors": factors}
