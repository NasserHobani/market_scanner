# -*- coding: utf-8 -*-
"""Widget data builders — presentation layer over scanner modules."""
from __future__ import annotations

from typing import Any

from scanner import tracking
from scanner.research.baselines_loader import baseline_comparison
from scanner.research.confidence import confidence_report
from scanner.research.contribution import factor_contributions
from scanner.research.events import count_independent_events
from scanner.research.experiments_loader import load_experiments
from scanner.research.health import health_panel
from scanner.research.trends import trends_payload

from . import trades as trade_svc


def build_health(rows: list[dict], *, market: str = "", timeframe: str = "",
                 running_experiments: int = 0,
                 baseline_pass: bool = False) -> dict[str, Any]:
    overall = tracking.summarize(rows)
    panel = health_panel(
        overall, rows,
        running_experiments=running_experiments,
        baseline_pass=baseline_pass,
    )
    # ‏health_panel لا يمرّر نسبة النجاح ولا الحصيلة، ولوحة التشغيل تعرضهما
    # كمؤشّرين أساسيين. القيم محسوبة أصلاً في overall — هذا تمرير لا حساب،
    # وإضافة فقط: لا حقل قائم يتغيّر.
    panel.setdefault("win_rate", overall.get("win_rate"))
    panel.setdefault("win_rate_low", overall.get("win_rate_low"))
    panel.setdefault("win_rate_high", overall.get("win_rate_high"))
    panel.setdefault("total_r", overall.get("total_r"))
    return panel


def build_trends(rows: list[dict]) -> dict[str, Any]:
    return trends_payload(rows)


def build_experiments() -> dict[str, Any]:
    experiments, running = load_experiments()
    return {"experiments": experiments, "running_experiments": running}


def build_factors(rows: list[dict]) -> dict[str, Any]:
    return {"contributions": factor_contributions(rows)}


def build_confidence(rows: list[dict]) -> dict[str, Any]:
    indep = count_independent_events(rows)
    return {"confidence": confidence_report(rows, indep), "independent_events": indep}


def build_baselines(rows: list[dict], *, market: str = "",
                    timeframe: str = "") -> dict[str, Any]:
    return {"baselines": baseline_comparison(
        rows, market=market or "crypto", timeframe=timeframe or "4h")}


def build_splits(rows: list[dict]) -> dict[str, Any]:
    splits = [
        ("التصنيف", tracking.split(rows, "grade", min_n=3)),
        ("الفريم", tracking.split(rows, "timeframe", min_n=3)),
        ("السوق", tracking.split(rows, "market", min_n=3)),
        ("سبب الدخول", tracking.split_multi(rows, "factors", min_n=3)),
    ]
    return {
        "splits": [{"title": t, "rows": r} for t, r in splits],
        "overall": tracking.summarize(rows),
    }


_TRADES_SORT = {
    "date_desc": "-signal_at",
    "date_asc": "signal_at",
    "opened_desc": "-opened_at",
    "opened_asc": "opened_at",
    "closed_desc": "-closed_at",
    "closed_asc": "closed_at",
}


def _trade_row(t, *, local_text, held_text) -> dict[str, Any]:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "market": t.market,
        "timeframe": t.timeframe,
        "status": t.status,
        "label": t.get_status_display(),
        "r": t.r_multiple,
        "unrealized": t.unrealized_r,
        "grade": t.grade,
        "note": t.resolution_note,
        "reasons": t.reasons or "",
        "entry": t.entry,
        "stop": t.stop,
        "target1": t.target1,
        "entry_price": t.entry_price,
        "exit_price": t.exit_price,
        "last_price": t.last_price,
        "signal_at": t.signal_at.isoformat() if t.signal_at else None,
        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "opened": local_text(t.opened_at),
        "opened_full": local_text(t.opened_at, "Y-m-d H:i"),
        "closed": local_text(t.closed_at),
        "closed_full": local_text(t.closed_at, "Y-m-d H:i"),
        "held": held_text(t),
        "candle_time": t.candle_time.strftime("%m-%d %H:%M") if t.candle_time else "",
    }


def build_trades_page(qs, *, filters: dict, page: int, page_size: str,
                      local_text, held_text, sort: str = "date_desc",
                      paginate_fn, apply_status_fn,
                      status_counts_fn) -> dict[str, Any]:
    counts = status_counts_fn(qs)

    class _Req:
        GET = {"page": str(page), "size": page_size}

    order = _TRADES_SORT.get(sort, "-signal_at")
    page_obj = paginate_fn(
        apply_status_fn(qs, filters["status"]).order_by(order), _Req())
    trades = [
        _trade_row(t, local_text=local_text, held_text=held_text)
        for t in page_obj
    ]
    # إحصاء المحسومة يُحسب على **كل** ما يطابق المرشّح لا على الصفحة
    # المعروضة: نسبة فوزٍ من خمسٍ وعشرين صفّاً ظاهراً ليست نسبة فوز.
    from .views import _settled_stats

    return {
        "trades": trades,
        "counts": counts,
        "stats": _settled_stats(qs),
        "page": {
            "number": page_obj.number,
            "num_pages": page_obj.paginator.num_pages,
            "per_page": page_obj.paginator.per_page,
            "total": page_obj.paginator.count,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "start_index": page_obj.start_index() if page_obj else 0,
            "end_index": page_obj.end_index() if page_obj else 0,
        },
    }


def build_open_trades(qs, *, local_text, held_text) -> dict[str, Any]:
    open_qs = qs.filter(status__in=("open", "pending")).order_by(
        "-signal_at")[:50]
    return {
        "trades": [
            _trade_row(t, local_text=local_text, held_text=held_text)
            for t in open_qs
        ],
        "open_count": open_qs.count(),
    }


def rows_for_request(qs) -> list[dict]:
    return trade_svc.rows_for_stats(qs)


def build_alerts(market: str = "") -> dict[str, Any]:
    from .models import SignalAlert

    qs = SignalAlert.objects.select_related("result").order_by("-fired_at")
    if market:
        qs = qs.filter(result__market=market)

    return {
        "alerts": [
            {
                "symbol": a.symbol,
                "market": a.result.market if a.result else "",
                "text": a.reasons or ("نقاط " + str(round(a.score, 1))),
                "created_at": a.fired_at.isoformat() if a.fired_at else "",
            }
            for a in qs[:10]
        ]
    }


def build_optimization_summary() -> dict[str, Any]:
    from scanner.optimization import OptimizationService

    svc = OptimizationService()
    history = svc.history(limit=20)
    latest = history[0] if history else None
    leaderboard = None
    if latest and latest.get("experiment_id"):
        leaderboard = svc.leaderboard(latest["experiment_id"])
    return {"history": history, "latest": latest, "leaderboard": leaderboard}


def build_ai_platform_summary(rows) -> dict[str, Any]:
    """Read-only presentation summary — no AI module modifications."""
    out = {
        "prediction": {"available": False, "status": "unavailable"},
        "similarity": {"available": False},
        "decision_ai": {"available": False},
        "feature_intelligence": {"available": False},
        "model_health": {"label": "غير متاح"},
        "drift": {"detected": False},
    }
    try:
        from scanner.predictive.training_orchestrator import (
            PredictionTrainingOrchestrator,
        )
        pred_status = PredictionTrainingOrchestrator().status()
        ps = pred_status.get("prediction_status") or {}
        models = pred_status.get("models") or {}
        dataset = pred_status.get("dataset") or {}
        training = pred_status.get("training") or {}
        active_id = models.get("active") or ""
        if ps.get("status") == "ACTIVE" and active_id:
            out["prediction"] = {
                "available": True,
                "status": "ACTIVE",
                "model_count": models.get("trained_count", 0),
                "latest_model": active_id,
                "oos_accuracy": ps.get("oos_accuracy"),
                "calibration": ps.get("calibration"),
                "promotion_status": ps.get("promotion_status"),
            }
            out["model_health"] = {
                "label": "نشط",
                "model_count": models.get("trained_count", 0),
            }
        else:
            ps = pred_status.get("prediction_status") or {}
            out["prediction"] = {
                "available": False,
                "status": ps.get("status", "UNAVAILABLE"),
                "reason": ps.get("reason_ar")
                          or ps.get("reason", "no trained model"),
                "current_model_id": ps.get("current_model_id"),
                "oos_accuracy": ps.get("oos_accuracy"),
                "baseline_accuracy": ps.get("baseline_accuracy"),
                "improvement": ps.get("improvement"),
                "walk_forward_status": ps.get("walk_forward_status"),
                "walk_forward_pass": ps.get("walk_forward_pass"),
                "calibration": ps.get("calibration_status")
                               or ps.get("calibration"),
                "quality_gate": ps.get("quality_gate", "NOT_PROMOTED"),
                "rejection_reasons": ps.get("rejection_reasons") or [],
                "feature_count": ps.get("feature_count"),
                "eligible_samples": ps.get("eligible_samples")
                                    or dataset.get("eligible"),
                "model_registry": ps.get("model_registry")
                                  or models.get("registry") or [],
                "dataset": dataset,
                "training": training,
                "models": models,
            }

            try:
                from scanner.predictive.dataset_readiness import build_readiness
                from scanner.feature_snapshots.config import (
                    DEFAULT_RUNTIME_CONFIG,
                )
                readiness = build_readiness(persist=True)
                out["prediction"]["readiness"] = readiness
                out["prediction"]["v3"] = {
                    "eligible": readiness.get("eligible_rows"),
                    "required": readiness.get("required_rows"),
                    "status": readiness.get("status"),
                    "status_ar": readiness.get("status_ar"),
                    "smoke_ready": (readiness.get("eligible_rows") or 0)
                                   >= DEFAULT_RUNTIME_CONFIG.v3_smoke_min_rows,
                    "train_ready": bool(readiness.get("ready_for_training")),
                    "last_result": (readiness.get("retrain_state")
                                    or {}).get("last_result") or {},
                    "runtime_coverage_pct": readiness.get(
                        "runtime_coverage_pct"),
                    "good_snapshot_count": readiness.get(
                        "good_snapshot_count"),
                    "partial_snapshot_count": readiness.get(
                        "partial_snapshot_count"),
                    "failed_snapshot_count": readiness.get(
                        "failed_snapshot_count"),
                    "linked_closed_trades": readiness.get(
                        "linked_closed_trades"),
                }

                why = list(out["prediction"].get("rejection_reasons") or [])
                if not why:
                    elig = readiness.get("eligible_rows") or 0
                    req = (readiness.get("required_rows")
                           or DEFAULT_RUNTIME_CONFIG.v3_train_min_rows)
                    if elig < req:
                        why.append(
                            f"صفوف Dataset V3 المؤهلة غير كافية ({elig}/{req})")
                    why.append("لا يوجد نموذج ACTIVE اجتاز بوابات الجودة")
                    lr = (readiness.get("retrain_state")
                          or {}).get("last_result") or {}
                    if (lr.get("improvement") is not None
                            and lr.get("baseline_accuracy") is not None):
                        why.append(
                            "OOS مقابل baseline: "
                            f"improvement={lr.get('improvement')}")
                    if lr.get("reason"):
                        why.append(str(lr["reason"]))
                out["prediction"]["rejection_reasons"] = why
                out["prediction"]["why_unavailable_ar"] = (
                    "النموذج غير متاح لأن:\n- " + "\n- ".join(why))

                out["prediction_cycle"] = {
                    "title_ar": "دورة التنبؤ",
                    "eligible_rows": readiness.get("eligible_rows"),
                    "required_rows": readiness.get("required_rows"),
                    "progress_percent": readiness.get("progress_percent"),
                    "status": readiness.get("status"),
                    "status_ar": readiness.get("status_ar"),
                    "runtime_coverage_pct": readiness.get(
                        "runtime_coverage_pct"),
                    "last_training_status": (readiness.get("retrain_state")
                                             or {}).get("last_status"),
                    "active_model_id": readiness.get("active_model_id"),
                    "prediction_reason": readiness.get("prediction_reason"),
                    "alerts": readiness.get("alerts") or [],
                }
            except Exception:  # noqa: BLE001
                pass

        out["prediction_status"] = pred_status

        try:
            from scanner.ai_fusion.fusion_metrics import compute_metrics
            from scanner.ai_fusion.fusion_report import build_comparison_report
            from scanner.ai_fusion.prediction_adapter import PredictionAdapter
            from scanner.predictive.training_orchestrator import (
                PredictionTrainingOrchestrator,
            )

            pred_st = PredictionTrainingOrchestrator().status()
            ps = pred_st.get("prediction_status") or {}
            out["ai_fusion"] = {
                "prediction_engine": (
                    "UNAVAILABLE" if ps.get("status") == "UNAVAILABLE"
                    else "ACTIVE"),
                "active_model_id":
                    PredictionAdapter().get_active_model_id() or None,
                "metrics": compute_metrics(),
                "comparison": build_comparison_report(),
                "prediction_status": ps,
            }
        except Exception:  # noqa: BLE001
            out["ai_fusion"] = {"prediction_engine": "UNAVAILABLE"}
    except Exception:  # noqa: BLE001
        pass

    try:
        from scanner.decision_ai import DecisionAIService

        out["decision_ai"] = {
            "available": True,
            "fusion_weights": DecisionAIService().fusion_weights(),
        }
    except Exception:  # noqa: BLE001
        pass

    try:
        from scanner.feature_snapshots.runtime_audit import full_runtime_report
        from scanner.predictive.trade_dataset import load_trades_from_django

        trades = []
        try:
            trades = load_trades_from_django()
        except Exception:  # noqa: BLE001
            pass
        snap_report = full_runtime_report(trades=trades)
        elig = snap_report.get("dataset_eligibility") or {}
        out["feature_snapshots"] = {
            "available": True,
            "status": snap_report.get("status"),
            "historical_coverage_pct": snap_report.get(
                "historical_coverage_pct"),
            "runtime_coverage_pct": snap_report.get("runtime_coverage_pct"),
            "average_feature_coverage_pct": snap_report.get(
                "average_feature_coverage_pct"),
            "quality": snap_report.get("quality"),
            "missing_feature_reasons": snap_report.get(
                "missing_feature_reasons"),
            "failed_snapshots": (snap_report.get("quality")
                                 or {}).get("FAILED", 0),
            "orphan_snapshots": (snap_report.get("linkage")
                                 or {}).get("orphan_count", 0),
            "leakage_events": snap_report.get("leakage_events", 0),
            "snapshot_linked_trades": (snap_report.get("linkage")
                                       or {}).get("snapshot_linked_trades", 0),
            "v3_eligible_trades": elig.get("eligible", 0),
            "v3_smoke_ready": elig.get("v3_smoke_ready", False),
            "latency": snap_report.get("latency"),
        }
    except Exception:  # noqa: BLE001
        out["feature_snapshots"] = {"available": False}

    if rows:
        overall = tracking.summarize(rows)
        out["similarity"] = {
            "available": True,
            "closed_trades": overall.get("closed", 0),
            "expectancy": overall.get("expectancy"),
        }
    return out


def build_ai_advisor_summary() -> dict[str, Any]:
    """Read-only AI Advisor presentation summary — no engine modifications."""
    try:
        from scanner.ai_advisor import AIAdvisorService

        return AIAdvisorService().to_ui_summary()
    except Exception:  # noqa: BLE001
        return {"available": False, "shadow_mode": True}


def build_ai_advisor_evaluation_summary() -> dict[str, Any]:
    """AI Advisor evaluation UI models — score, leaderboard, calibration."""
    try:
        from scanner.ai_advisor.evaluation import AdvisorEvaluationService

        return AdvisorEvaluationService().to_ui_model()
    except Exception:  # noqa: BLE001
        return {"available": False}


def build_ai_learning_summary() -> dict[str, Any]:
    """AI Learning UI models — lessons, proposals, experiments, timeline."""
    try:
        from scanner.ai_learning import LearningService

        return LearningService().to_ui_model()
    except Exception:  # noqa: BLE001
        return {"available": False, "advisory_only": True}


def build_ai_review_timeline(*, page: int, page_size: int) -> dict[str, Any]:
    """Review timeline widget — live card + recent history rows."""
    try:
        from scanner.ai_advisor.explainability import ReviewTimelineService

        svc = ReviewTimelineService()
        return {
            "available": True,
            "live": svc.get_live(),
            "timeline": svc.list_reviews(page=page, page_size=page_size),
            "providers": svc.provider_statistics(),
        }
    except Exception:  # noqa: BLE001
        return {"available": False, "live": None, "timeline": {"items": []}}