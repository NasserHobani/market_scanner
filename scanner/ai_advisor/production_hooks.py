# -*- coding: utf-8 -*-
"""Production hooks — evaluation and learning after trade settlement."""
from __future__ import annotations

import logging
from typing import Any

from .advisor_logging import log_runtime
from .memory import AdvisorMemory
from .provider_config import load_config

log = logging.getLogger("scanner.ai_advisor.hooks")


def on_trade_settled(trade: Any) -> dict[str, Any] | None:
    """Called when a trade closes — evaluate advisor and run learning cycle."""
    cfg = load_config()
    result: dict[str, Any] = {}

    if not cfg.evaluation_enabled:
        pass
    else:
        try:
            log_runtime("Evaluation Started")
            evaluation = _evaluate_closed_trade(trade)
            if evaluation and not evaluation.get("error"):
                result["evaluation"] = evaluation
                log_runtime("Evaluation Completed")
                try:
                    fusion_eval = _evaluate_fusion_outcome(trade, evaluation)
                    if fusion_eval:
                        result["fusion_evaluation"] = fusion_eval
                        evaluation["fusion"] = fusion_eval.get("fusion", {})
                except Exception as exc:  # noqa: BLE001
                    log.debug("fusion evaluation: %s", str(exc)[:120])
            else:
                log.debug("evaluation skipped: %s", evaluation)
        except Exception as exc:  # noqa: BLE001
            log.warning("evaluation failed: %s", str(exc)[:200])

    if cfg.learning_enabled and result.get("evaluation"):
        try:
            log_runtime("Learning Started")
            cycle = _run_learning_cycle()
            result["learning"] = {
                "lessons": len(cycle.get("lessons") or []),
                "proposals": len(cycle.get("proposals") or []),
                "hypotheses": len(cycle.get("hypotheses") or []),
            }
            log_runtime("Learning Completed")
        except Exception as exc:  # noqa: BLE001
            log.warning("learning cycle failed: %s", str(exc)[:200])

    try:
        from scanner.research.orchestrator import ResearchOrchestrator
        research_out = ResearchOrchestrator().on_trade_closed(trade)
        if research_out:
            result["research"] = research_out
    except Exception as exc:  # noqa: BLE001
        log.debug("research orchestrator hook: %s", str(exc)[:120])

    try:
        from scanner.predictive.training_orchestrator import PredictionTrainingOrchestrator
        pred_out = PredictionTrainingOrchestrator().on_trade_closed(trade)
        if pred_out:
            result["prediction_training"] = pred_out
    except Exception as exc:  # noqa: BLE001
        log.debug("prediction training hook: %s", str(exc)[:120])

    # AIA-12: readiness-gated V3 evaluate — async, never blocks settlement, never auto-promotes
    try:
        from scanner.predictive.v3_retrain import schedule_if_ready_async
        sched = schedule_if_ready_async()
        result["v3_retrain_scheduled"] = bool(sched.get("scheduled"))
        result["v3_readiness"] = {
            "eligible_rows": (sched.get("readiness") or {}).get("eligible_rows"),
            "ready_for_training": (sched.get("readiness") or {}).get("ready_for_training"),
            "status": (sched.get("readiness") or {}).get("status"),
        }
    except Exception as exc:  # noqa: BLE001
        log.debug("v3 retrain schedule: %s", str(exc)[:120])

    return result or None


def _evaluate_closed_trade(trade: Any) -> dict[str, Any] | None:
    from scanner.ai_advisor.evaluation import AdvisorEvaluationService

    memory = AdvisorMemory()
    record = memory.find_by_trade_id(str(trade.pk)) or memory.find_latest_for_symbol(
        symbol=trade.symbol,
        market=trade.market,
        timeframe=trade.timeframe,
    )
    if not record:
        return {"error": "no_advisor_review"}

    trade_result = {
        "status": trade.status,
        "symbol": trade.symbol,
        "r_multiple": trade.r_multiple,
        "market": trade.market,
        "timeframe": trade.timeframe,
        "direction": trade.side,
        "closed_at": trade.closed_at.isoformat() if trade.closed_at else "",
        "execution_date": trade.closed_at.isoformat() if trade.closed_at else "",
    }

    svc = AdvisorEvaluationService(memory=memory)
    return svc.evaluate_trade(
        trade_id=str(trade.pk),
        review_id=record.get("record_id", ""),
        trade_result=trade_result,
    )


def _run_learning_cycle() -> dict[str, Any]:
    from scanner.ai_learning import LearningService

    return LearningService().run_cycle(scope={"last_n": 50}, period="daily")


def _evaluate_fusion_outcome(trade: Any, evaluation: dict[str, Any]) -> dict[str, Any] | None:
    from scanner.ai_fusion.fusion_history import FusionHistory
    from scanner.ai_fusion.outcome_evaluator import evaluate_outcome

    review_id = evaluation.get("advisor_review_id", "")
    fusion_record = None
    for row in reversed(FusionHistory().list_all(limit=200)):
        if row.get("review_id") == review_id:
            fusion_record = row
            break
    if not fusion_record and not review_id:
        return None

    trade_result = {
        "trade_id": str(trade.pk),
        "status": trade.status,
        "r_multiple": trade.r_multiple,
        "symbol": trade.symbol,
        "timeframe": trade.timeframe,
    }
    return evaluate_outcome(
        trade_result=trade_result,
        fusion_record=fusion_record,
        advisor_evaluation=evaluation,
    )
