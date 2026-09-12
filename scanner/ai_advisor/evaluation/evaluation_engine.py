# -*- coding: utf-8 -*-
"""Evaluation engine — measures advisor quality after trades close."""
from __future__ import annotations

from typing import Any

from scanner.ai_advisor.memory import AdvisorMemory
from scanner.ai_learning.failure_classifier import classify_evaluation

from .advisor_dataset import AdvisorEvaluationDataset
from .advisor_metrics import AdvisorMetrics

EVALUATION_VERSION = "1.0.0"


class EvaluationEngine:
    """Trade Closed → Load → Evaluate → Store → Update Metrics."""

    def __init__(self,
                 dataset: AdvisorEvaluationDataset | None = None,
                 memory: AdvisorMemory | None = None,
                 metrics: AdvisorMetrics | None = None) -> None:
        self._dataset = dataset or AdvisorEvaluationDataset()
        self._memory = memory or AdvisorMemory()
        self._metrics = metrics or AdvisorMetrics()

    def evaluate_closed_trade(self, *,
                              trade_id: str,
                              trade_result: dict[str, Any],
                              memory_record: dict[str, Any] | None = None,
                              review_id: str = "",
                              decision_package: dict[str, Any] | None = None) -> dict[str, Any]:
        """Evaluate one closed trade against its advisor review."""
        record = memory_record or self._load_memory(review_id)
        if record is None:
            return {"error": "no_advisor_review", "trade_id": trade_id}

        response = record.get("response") or {}
        validation = response.get("validation") or record.get("validation") or {}
        pkg = decision_package or {}

        agreement = str(response.get("agreement", "partial"))
        confidence = float(response.get("confidence", 0))
        risks = list(response.get("risks") or [])
        hallucination = bool(validation.get("hallucination_count", 0) > 0
                             or validation.get("hallucinations"))

        won = self._trade_won(trade_result)
        lost = self._trade_lost(trade_result)
        r_multiple = trade_result.get("r_multiple")

        useful_warning, false_warning, missed_warning = self._warning_quality(
            risks, won, lost, r_multiple,
        )

        classification = classify_evaluation({
            "advisor_agreement": agreement,
            "won": won,
            "lost": lost,
            "hallucination": hallucination,
            "false_warning": false_warning,
            "missed_warning": missed_warning,
            "advisor_confidence": confidence,
            "trade_result": trade_result.get("status", ""),
            "r_multiple": r_multiple,
        })
        advisor_correct = classification["advisor_correct"]

        evaluation = {
            "trade_id": trade_id,
            "symbol": trade_result.get("symbol", pkg.get("symbol", "")),
            "decision_package_id": record.get("package_id", pkg.get("package_id", "")),
            "advisor_review_id": record.get("record_id", ""),
            "provider": record.get("provider_id", ""),
            "model": record.get("model_name", ""),
            "prompt_version": record.get("prompt_version", ""),
            "trade_result": trade_result.get("status", ""),
            "outcome": classification["outcome"],
            "advisor_prediction": agreement,
            "advisor_agreement": agreement,
            "advisor_confidence": confidence,
            "advisor_correct": advisor_correct,
            "evaluation_type": classification["evaluation_type"],
            "failure_type": classification.get("failure_type"),
            "secondary_type": classification.get("secondary_type"),
            "is_advisor_failure": classification.get("is_failure", False),
            "hallucination": hallucination,
            "useful_warning": useful_warning,
            "false_warning": classification.get("false_warning", false_warning),
            "missed_warning": missed_warning,
            "execution_date": trade_result.get("execution_date", trade_result.get("closed_at", "")),
            "market": trade_result.get("market", pkg.get("market", "")),
            "timeframe": trade_result.get("timeframe", pkg.get("timeframe", "")),
            "strategy": trade_result.get("strategy", pkg.get("strategy", "")),
            "trend": trade_result.get("trend", pkg.get("trend", "")),
            "direction": trade_result.get("direction", pkg.get("direction", "")),
            "expectancy": trade_result.get("expectancy"),
            "profit_factor": trade_result.get("profit_factor"),
            "r_multiple": r_multiple,
            "evaluation_version": EVALUATION_VERSION,
        }
        try:
            from scanner.ai_advisor.analyst.outlook_eval import evaluate_outlook, outlook_pattern_label
            outlook = evaluate_outlook(response, trade_result)
            evaluation.update(outlook)
            evaluation["outlook_pattern"] = outlook_pattern_label(evaluation)
        except Exception:  # noqa: BLE001
            evaluation["outlook_correct"] = None

        evaluation_id = self._dataset.save(evaluation)
        evaluation["evaluation_id"] = evaluation_id

        self._memory.update_performance(
            record.get("record_id", ""),
            {
                "outcome": "correct" if advisor_correct else "incorrect",
                "trade_result": trade_result,
                "evaluation_id": evaluation_id,
            },
        )

        return evaluation

    def evaluate_by_review_id(self, *, trade_id: str,
                              review_id: str,
                              trade_result: dict[str, Any]) -> dict[str, Any]:
        record = self._load_memory(review_id)
        return self.evaluate_closed_trade(
            trade_id=trade_id,
            trade_result=trade_result,
            memory_record=record,
        )

    def recompute_metrics(self) -> dict[str, Any]:
        records = self._dataset.list_all()
        return self._metrics.compute(records)

    def recent_evaluations(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._dataset.list_all()[-limit:]

    def _load_memory(self, review_id: str) -> dict[str, Any] | None:
        if not review_id:
            return None
        return self._memory.load(review_id)

    @staticmethod
    def _trade_won(result: dict[str, Any]) -> bool:
        status = str(result.get("status", "")).lower()
        r = result.get("r_multiple")
        if status in ("won", "win"):
            return True
        if r is not None and float(r) > 0:
            return True
        return False

    @staticmethod
    def _trade_lost(result: dict[str, Any]) -> bool:
        status = str(result.get("status", "")).lower()
        r = result.get("r_multiple")
        if status in ("lost", "loss"):
            return True
        if r is not None and float(r) < 0:
            return True
        return False

    @staticmethod
    def _is_correct(agreement: str, won: bool, lost: bool) -> bool:
        """Advisor correct if agreement aligned with outcome."""
        if agreement == "agree" and won:
            return True
        if agreement == "disagree" and lost:
            return True
        if agreement == "partial":
            return False
        if agreement == "agree" and lost:
            return False
        if agreement == "disagree" and won:
            return False
        return False

    @staticmethod
    def _warning_quality(risks: list, won: bool, lost: bool,
                         r_multiple: float | None) -> tuple[bool, bool, bool]:
        has_risks = len(risks) > 0
        big_loss = lost and r_multiple is not None and float(r_multiple) <= -1.0

        useful_warning = has_risks and lost
        false_warning = has_risks and won and (r_multiple is None or float(r_multiple) >= 1.0)
        missed_warning = (not has_risks) and big_loss
        return useful_warning, false_warning, missed_warning
