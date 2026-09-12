# -*- coding: utf-8 -*-
"""Manual AI analysis — cache, pipeline wrapper, history tagging."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from scanner.ai_local.config import load_local_config
from ..memory import AdvisorMemory
from ..runtime import is_advisor_enabled, review_recommendation
from .localized_presentation import build_presentations
from .manual_formatter import format_manual_analysis
from .review_meta import ReviewMetaStore, recommendation_fingerprint
from .symbol_context import build_symbol_context

CACHE_TTL_SECONDS = 600  # 10 minutes


class ManualAnalysisService:
    """On-demand AI analysis using the same runtime pipeline as scans."""

    def __init__(self) -> None:
        self._meta = ReviewMetaStore()
        self._memory = AdvisorMemory()
        self._cache_path = Path(__file__).resolve().parents[3] / "data" / "manual_analysis_cache.json"
        self._cache: dict[str, Any] = self._load_cache()

    def analyze(self, *, symbol: str, market: str, timeframe: str | None = None,
                force: bool = False) -> dict[str, Any]:
        if not is_advisor_enabled():
            return {"ok": False, "error": "advisor_disabled",
                    "message": "AI Advisor is disabled or not configured"}

        try:
            ctx = build_symbol_context(symbol, market, timeframe)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "context_failed", "message": str(exc)[:200]}

        symbol = ctx["symbol"]
        market = ctx["market"]
        timeframe = ctx["timeframe"]
        reco = ctx["recommendation"]
        fp = recommendation_fingerprint(reco)
        cache_key = f"{market}:{symbol}:{timeframe}:{fp}"

        if not force:
            cached = self._get_cached(cache_key)
            if cached:
                cached["cached"] = True
                return self._ensure_presentations(cached)

        result = review_recommendation(
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            recommendation=reco,
            row=ctx["row"],
            trade_id="",
            context_profile="standard",
        )

        if not result or not result.get("accepted"):
            local = load_local_config()
            mode = local.execution_mode if local.local_enabled else "claude_only"
            if mode == "compare" and result and result.get("comparison"):
                return self._compare_payload(
                    symbol=symbol, market=market, timeframe=timeframe,
                    reco=reco, fp=fp, result=result,
                )
            return {
                "ok": False,
                "error": "review_failed",
                "message": "AI review was not accepted",
                "detail": result,
                "execution_mode": mode,
            }

        review_id = result["review_id"]
        mem = self._memory.load(review_id)
        review_dict = (mem or {}).get("response", {})

        self._meta.save(
            review_id=review_id,
            review_type="manual",
            symbol=symbol,
            market=market,
            timeframe=timeframe,
            recommendation=reco,
            fingerprint=fp,
        )

        payload = {
            "ok": True,
            "cached": False,
            "review_id": review_id,
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "execution_mode": load_local_config().execution_mode,
            "metrics": result.get("metrics", {}),
            "package_diagnostics": result.get("package_diagnostics", {}),
            "report": self._full_report(review_id, mem, result),
            "manual": format_manual_analysis(
                review_dict,
                recommendation=reco,
                metrics=result.get("metrics"),
                review_type="manual",
            ),
        }
        if result.get("comparison"):
            payload["comparison"] = result["comparison"]
            payload["compare"] = self._build_compare_view(result, reco)
        payload = self._ensure_presentations(payload)
        self._set_cached(cache_key, payload)
        return payload

    def _compare_payload(self, *, symbol: str, market: str, timeframe: str,
                         reco: dict[str, Any], fp: str,
                         result: dict[str, Any]) -> dict[str, Any]:
        """Compare mode may return partial success — show side-by-side."""
        cmp_data = result.get("comparison") or {}
        return {
            "ok": True,
            "cached": False,
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "execution_mode": "compare",
            "comparison": cmp_data,
            "compare": self._build_compare_view(result, reco),
            "review_id": result.get("review_id", ""),
            "metrics": result.get("metrics", {}),
            "package_diagnostics": result.get("package_diagnostics", {}),
            "platform_decision": (reco.get("side") or reco.get("decision") or "").upper(),
        }

    def _build_compare_view(self, result: dict[str, Any],
                            reco: dict[str, Any]) -> dict[str, Any]:
        cmp_data = result.get("comparison") or {}
        platform = (reco.get("side") or reco.get("decision") or "").upper()
        return {
            "platform_decision": platform,
            "package_fingerprint": cmp_data.get("package_fingerprint", ""),
            "comparison_id": cmp_data.get("comparison_id", ""),
            "claude": {
                "review_id": cmp_data.get("claude_review_id", ""),
                "agreement": cmp_data.get("claude_agreement", ""),
                "confidence": cmp_data.get("claude_confidence"),
                "latency_ms": cmp_data.get("claude_latency_ms"),
                "estimated_cost": cmp_data.get("claude_estimated_cost"),
            },
            "ollama": {
                "review_id": cmp_data.get("local_review_id", ""),
                "agreement": cmp_data.get("local_agreement", ""),
                "confidence": cmp_data.get("local_confidence"),
                "latency_ms": cmp_data.get("local_latency_ms"),
                "estimated_cost": 0.0,
            },
            "errors": cmp_data.get("errors", []),
        }

    def _ensure_presentations(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Attach localized presentations for client-side language switching."""
        if payload.get("presentations"):
            return payload
        report = payload.get("report") or {}
        if report and not report.get("presentations"):
            report["presentations"] = build_presentations(report)
            payload["report"] = report
        if report.get("presentations"):
            payload["presentations"] = report["presentations"]
        return payload

    def _full_report(self, review_id: str, mem: dict[str, Any] | None,
                     result: dict[str, Any]) -> dict[str, Any]:
        from .review_timeline_service import ReviewTimelineService
        detail = ReviewTimelineService().get_review(review_id)
        if detail:
            return detail
        resp = (mem or {}).get("response", {})
        return {
            "review_id": review_id,
            "review_type": "manual",
            "response": resp,
            "metrics": result.get("metrics", {}),
        }

    def _load_cache(self) -> dict[str, Any]:
        if not self._cache_path.exists():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._cache), encoding="utf-8")

    def _get_cached(self, key: str) -> dict[str, Any] | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("_ts", 0) > CACHE_TTL_SECONDS:
            del self._cache[key]
            self._save_cache()
            return None
        return self._ensure_presentations(dict(entry.get("payload") or {}))

    def _set_cached(self, key: str, payload: dict[str, Any]) -> None:
        self._cache[key] = {"_ts": time.time(), "payload": payload}
        self._save_cache()
