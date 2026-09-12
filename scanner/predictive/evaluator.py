# -*- coding: utf-8 -*-
"""Deterministic model evaluation — no hidden calculations."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    """Structured evaluation output."""

    classification: dict[str, Any] = field(default_factory=dict)
    regression: dict[str, Any] = field(default_factory=dict)
    trading: dict[str, Any] = field(default_factory=dict)
    sample_size: int = 0
    task_type: str = "classification"

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": dict(self.classification),
            "regression": dict(self.regression),
            "trading": dict(self.trading),
            "sample_size": self.sample_size,
            "task_type": self.task_type,
        }


class Evaluator:
    """Compute explainable evaluation metrics."""

    def evaluate(self, *,
                 y_true: list[float],
                 y_pred: list[float],
                 y_proba: list[float] | None = None,
                 r_multiples: list[float] | None = None,
                 task_type: str = "classification",
                 threshold: float = 0.5) -> dict[str, Any]:
        result = EvaluationResult(sample_size=len(y_true), task_type=task_type)

        if task_type == "classification":
            binary_true = [int(t >= 0.5) for t in y_true]
            if y_proba:
                binary_pred = [int(p >= threshold) for p in y_proba]
            else:
                binary_pred = [int(p >= 0.5) for p in y_pred]
            result.classification = self._classification_metrics(binary_true, binary_pred, y_proba)
        else:
            result.regression = self._regression_metrics(y_true, y_pred)

        if r_multiples:
            result.trading = self._trading_metrics(r_multiples, y_pred, y_proba, threshold)

        return result.to_dict()

    def _classification_metrics(self, y_true: list[int], y_pred: list[int],
                                y_proba: list[float] | None) -> dict[str, Any]:
        n = len(y_true)
        if n == 0:
            return {}

        tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
        tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)

        accuracy = (tp + tn) / n
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if (precision + recall) > 0 else 0.0)

        metrics: dict[str, Any] = {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "true_negatives": tn,
        }

        if y_proba and len(set(y_true)) == 2:
            auc = self._roc_auc(y_true, y_proba)
            if auc is not None:
                metrics["roc_auc"] = round(auc, 4)

        return metrics

    def _regression_metrics(self, y_true: list[float],
                            y_pred: list[float]) -> dict[str, Any]:
        n = len(y_true)
        if n == 0:
            return {}
        errors = [p - t for t, p in zip(y_true, y_pred)]
        abs_errors = [abs(e) for e in errors]
        sq_errors = [e ** 2 for e in errors]
        mean_true = sum(y_true) / n
        ss_res = sum((t - p) ** 2 for t, p in zip(y_true, y_pred))
        ss_tot = sum((t - mean_true) ** 2 for t in y_true)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return {
            "rmse": round(math.sqrt(sum(sq_errors) / n), 4),
            "mae": round(sum(abs_errors) / n, 4),
            "r_squared": round(r2, 4),
        }

    def _trading_metrics(self, r_multiples: list[float],
                         y_pred: list[float],
                         y_proba: list[float] | None,
                         threshold: float) -> dict[str, Any]:
        """Trading metrics on trades where model predicted positive."""
        if y_proba:
            taken = [r for r, p in zip(r_multiples, y_proba) if p >= threshold]
        else:
            taken = [r for r, p in zip(r_multiples, y_pred) if p >= 0.5]

        if not taken:
            return {"expectancy": None, "profit_factor": None,
                    "avg_r": None, "win_rate": None, "trades_taken": 0}

        wins = [r for r in taken if r > 0]
        losses = [r for r in taken if r < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))

        return {
            "expectancy": round(sum(taken) / len(taken), 4),
            "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else None,
            "avg_r": round(sum(taken) / len(taken), 4),
            "win_rate": round(len(wins) / len(taken) * 100, 2),
            "trades_taken": len(taken),
        }

    @staticmethod
    def _roc_auc(y_true: list[int], y_proba: list[float]) -> float | None:
        """Deterministic ROC AUC via trapezoidal rule."""
        if len(set(y_true)) < 2:
            return None
        pairs = sorted(zip(y_proba, y_true), reverse=True)
        tp = fp = 0
        tp_total = sum(y_true)
        fp_total = len(y_true) - tp_total
        if tp_total == 0 or fp_total == 0:
            return None
        prev_fpr = prev_tpr = 0.0
        auc = 0.0
        for prob, label in pairs:
            if label == 1:
                tp += 1
            else:
                fp += 1
            tpr = tp / tp_total
            fpr = fp / fp_total
            auc += (fpr - prev_fpr) * (tpr + prev_tpr) / 2
            prev_fpr, prev_tpr = fpr, tpr
        return auc
