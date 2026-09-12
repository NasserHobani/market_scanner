# -*- coding: utf-8 -*-
"""Adapters — map platform layer outputs to unified package sections."""
from __future__ import annotations

from typing import Any


def adapt_recommendation(reco: dict[str, Any], kctx: dict[str, Any],
                         reasoning: dict[str, Any]) -> dict[str, Any]:
    trade = kctx.get("trade_snapshot") or {}
    return {
        "action": reasoning.get("action") or reco.get("action", ""),
        "direction": reasoning.get("direction") or reco.get("side", ""),
        "confidence": reco.get("confidence"),
        "grade": reco.get("grade", ""),
        "risk": trade.get("risk") or reco.get("risk"),
        "expectancy": (kctx.get("strategy_statistics") or {}).get("expectancy"),
        "r_target": reco.get("rr") or reco.get("r_target"),
        "stop": trade.get("stop") or reco.get("stop"),
        "entry": trade.get("entry") or reco.get("entry"),
        "verdict": reasoning.get("verdict") or reco.get("verdict", ""),
    }


def adapt_knowledge(kctx: dict[str, Any]) -> dict[str, Any]:
    env = kctx.get("market_environment") or {}
    snap = kctx.get("market_snapshot") or {}
    feat = kctx.get("feature_snapshot") or {}
    graph = kctx.get("knowledge_graph") or {}
    facts = []
    for node in (graph.get("nodes") or [])[:8]:
        if isinstance(node, dict):
            facts.append(node.get("label") or node.get("id", ""))
    patterns = []
    for edge in (graph.get("edges") or [])[:5]:
        if isinstance(edge, dict):
            patterns.append(f"{edge.get('source')}→{edge.get('target')}")
    return {
        "available": bool(kctx),
        "market_regime": env.get("regime"),
        "market_structure": snap.get("structure") or env.get("structure"),
        "knowledge_facts": [f for f in facts if f],
        "detected_patterns": patterns,
        "trend_summary": snap.get("trend_direction"),
        "final_grade": feat.get("final_grade"),
        "final_score": feat.get("final_score"),
        "memory_gaps": kctx.get("memory_gaps") or [],
    }


def adapt_reasoning(reasoning: dict[str, Any]) -> dict[str, Any]:
    evidence_items = (reasoning.get("evidence") or {}).get("items") or []
    contradictions = (reasoning.get("contradictions") or {}).get("items") or []
    if isinstance(reasoning.get("contradictions"), list):
        contradictions = reasoning["contradictions"]
    return {
        "available": bool(reasoning),
        "reasoning_chain": reasoning.get("decision_tree") or reasoning.get("explanation", ""),
        "evidence": [
            {
                "evidence_id": e.get("evidence_id"),
                "label": e.get("label"),
                "direction": e.get("direction"),
                "confidence": e.get("confidence"),
                "source": e.get("source"),
            }
            for e in evidence_items[:10]
        ],
        "confidence": reasoning.get("engine_confidence") or reasoning.get("agreement_score"),
        "contradictions": contradictions[:5],
        "warnings": reasoning.get("warnings") or [],
        "verdict": reasoning.get("verdict"),
        "missing_information": reasoning.get("missing_information") or [],
    }


def adapt_similarity(ctx: dict[str, Any] | None) -> dict[str, Any]:
    if not ctx:
        return {"available": False}
    matches = ctx.get("similarity_result", {}).get("matches") if isinstance(
        ctx.get("similarity_result"), dict) else None
    if matches is None:
        matches = ctx.get("top_matches") or []
    similar_cases = []
    for m in (matches or [])[:5]:
        if isinstance(m, dict):
            similar_cases.append({
                "event_id": m.get("event_id"),
                "similarity": (m.get("similarity_score") or {}).get("overall")
                if isinstance(m.get("similarity_score"), dict)
                else m.get("similarity"),
                "outcome": m.get("outcome_class") or m.get("historical_outcome"),
            })
    return {
        "available": bool(ctx.get("available", ctx.get("match_count"))),
        "historical_matches": ctx.get("match_count") or len(matches or []),
        "win_rate": ctx.get("average_win_rate"),
        "average_r": ctx.get("average_r"),
        "similar_cases": similar_cases,
        "confidence": ctx.get("confidence"),
        "warnings": ctx.get("historical_warnings") or ctx.get("warnings") or [],
    }


def adapt_research(report: dict[str, Any] | None) -> dict[str, Any]:
    if not report:
        return {"available": False}
    metrics = report.get("metrics") or {}
    comparison = report.get("comparison") or {}
    return {
        "available": True,
        "experiment_summary": report.get("title") or report.get("hypothesis", ""),
        "research_confidence": report.get("confidence") or metrics.get("confidence"),
        "comparison_results": comparison if comparison else {
            "verdict": report.get("verdict"),
            "p_value": report.get("p_value"),
            "effect_size": report.get("effect_size"),
        },
        "hypothesis_evidence": report.get("conclusions") or report.get("hypothesis_evidence") or [],
        "sample_size": report.get("sample_size") or metrics.get("sample_size"),
        "statistics": report.get("statistics"),
    }


def adapt_feature_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {
            "available": False,
            "quality": "UNAVAILABLE",
            "reason": "no point-in-time snapshot",
        }
    if not snapshot.get("available") and not snapshot.get("snapshot_id"):
        return {
            "available": False,
            "quality": "UNAVAILABLE",
            "reason": snapshot.get("reason", "no point-in-time snapshot"),
        }
    return {
        "available": True,
        "snapshot_id": snapshot.get("snapshot_id", ""),
        "version": snapshot.get("version", ""),
        "timestamp": snapshot.get("timestamp", ""),
        "coverage": snapshot.get("coverage"),
        "quality": snapshot.get("quality", "PARTIAL"),
        "feature_count": snapshot.get("feature_count", 0),
        "status": snapshot.get("status", ""),
        "summary": snapshot.get("summary") or {},
        "evidence_id": snapshot.get("evidence_id", ""),
    }


def adapt_feature_intelligence(analysis: dict[str, Any] | None) -> dict[str, Any]:
    if not analysis:
        return {"available": False}
    ranking = analysis.get("ranking") or analysis.get("top_features") or []
    if isinstance(ranking, dict):
        ranking = ranking.get("top") or list(ranking.values())[:5]
    top = []
    for item in (ranking or [])[:5]:
        if isinstance(item, dict):
            top.append(item.get("feature") or item.get("name", str(item)))
        else:
            top.append(str(item))
    drift = analysis.get("drift") or {}
    report = analysis.get("report") or {}
    return {
        "available": True,
        "top_features": top or analysis.get("top_features", [])[:5],
        "feature_quality": report.get("quality_score") or analysis.get("quality_score"),
        "drift": drift.get("detected") if isinstance(drift, dict) else analysis.get("drift_detected"),
        "redundancy": (analysis.get("redundancy") or {}).get("count")
        if isinstance(analysis.get("redundancy"), dict) else analysis.get("redundancy_count"),
        "stability": (analysis.get("stability") or {}).get("score")
        if isinstance(analysis.get("stability"), dict) else analysis.get("stability_score"),
    }


def adapt_prediction(pred: dict[str, Any] | None) -> dict[str, Any]:
    if not pred:
        return {"available": False, "status": "UNAVAILABLE", "reason": "no prediction layer"}
    if pred.get("available") is False or pred.get("status") == "UNAVAILABLE":
        return {
            "available": False,
            "status": "UNAVAILABLE",
            "reason": pred.get("reason", "no_active_model"),
        }
    return {
        "available": True,
        "model_id": pred.get("model_id"),
        "model_version": pred.get("model_version"),
        "prediction": pred.get("prediction") or pred.get("model_output"),
        "probability_win": pred.get("probability_win") or pred.get("probability"),
        "probability_loss": pred.get("probability_loss"),
        "calibration": pred.get("calibration") or {
            "status": pred.get("calibration_status", "unknown"),
        },
        "quality": pred.get("quality", {}),
        "feature_version": pred.get("feature_version"),
        "feature_timestamp": pred.get("feature_timestamp"),
        "evidence_ids": pred.get("evidence_ids", []),
    }


def adapt_optimization(opt: dict[str, Any] | None) -> dict[str, Any]:
    if not opt:
        return {"available": False}
    report = opt.get("report") or opt
    wf = report.get("walk_forward") or opt.get("walk_forward") or {}
    best_metrics = report.get("best_metrics") or opt.get("best_metrics") or {}
    return {
        "available": True,
        "optimized_parameters": report.get("best_parameters") or opt.get("best_parameters"),
        "optimization_confidence": report.get("confidence") or opt.get("confidence"),
        "walk_forward_result": wf.get("passed") if isinstance(wf, dict) else opt.get("walk_forward_pass"),
        "baseline_comparison": report.get("improvement") or opt.get("baseline_comparison"),
        "best_expectancy": best_metrics.get("expectancy") or opt.get("best_expectancy"),
        "accepted_strategies": opt.get("accepted_count"),
        "rejected_strategies": opt.get("rejected_count"),
    }


def adapt_decision_ai(decision_ai: dict[str, Any] | None, *,
                      guardrails: dict[str, Any] | None = None,
                      fused_confidence: dict[str, Any] | None = None,
                      reasoning: dict[str, Any] | None = None) -> dict[str, Any]:
    dai = decision_ai or {}
    gr = guardrails or dai.get("guardrails") or {}
    fused = fused_confidence or dai.get("fused_confidence") or {}
    contradictions = (reasoning or {}).get("contradictions") or {}
    if isinstance(contradictions, dict):
        contradictions = contradictions.get("items") or []
    return {
        "available": bool(dai or gr or fused),
        "fused_confidence": fused.get("overall") or fused.get("fused_score"),
        "fused_components": fused.get("components") or {},
        "guardrails": {
            "passed": gr.get("passed", True),
            "violations": gr.get("violations") or [],
        },
        "warnings": (reasoning or {}).get("warnings") or dai.get("warnings") or [],
        "contradictions": contradictions[:5] if isinstance(contradictions, list) else [],
        "verdict": dai.get("verdict") or (reasoning or {}).get("verdict"),
    }
