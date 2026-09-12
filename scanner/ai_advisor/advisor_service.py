# -*- coding: utf-8 -*-
"""Public AI Advisor service API."""
from __future__ import annotations

from typing import Any

from .advisor_engine import AdvisorEngine, DEFAULT_PROVIDER
from .advisor_score import AdvisorScore
from .decision_package import DecisionPackage, DecisionPackageBuilder, AI_ADVISOR_VERSION
from .unified_package import UnifiedDecisionPackage, UnifiedPackageBuilder, UNIFIED_PACKAGE_VERSION
from .history import AdvisorHistory
from .memory import AdvisorMemory
from .prompt_builder import PromptBuilder, DEFAULT_PROMPT_VERSION
from .provider_config import load_config, effective_provider_id
from .provider_registry import ProviderRegistry, get_registry
from .review import AdvisorReview
from .runtime_history import AdvisorRuntimeHistory
from .runtime_state import AdvisorRuntimeState


class AIAdvisorService:
    """Public facade for the AI Advisor framework.

    Shadow Mode only: the advisor reads, reviews, and comments.
    It never changes BUY, SELL, STOP, TARGET, or any calculation.
    """

    def __init__(self,
                 engine: AdvisorEngine | None = None,
                 registry: ProviderRegistry | None = None,
                 memory: AdvisorMemory | None = None,
                 score: AdvisorScore | None = None,
                 history: AdvisorHistory | None = None) -> None:
        self._registry = registry or get_registry()
        self._memory = memory or AdvisorMemory()
        self._engine = engine or AdvisorEngine(
            registry=self._registry, memory=self._memory,
        )
        self._score = score or AdvisorScore(memory=self._memory)
        self._history = history or AdvisorHistory(memory=self._memory)

    def build_package(self, event_id: str, **layer_outputs: Any) -> UnifiedDecisionPackage:
        """Build a Unified Decision Package from platform layer summaries."""
        return self._engine.build_package(event_id, **layer_outputs)

    def review(self, package: DecisionPackage | UnifiedDecisionPackage, *,
               provider_id: str = DEFAULT_PROVIDER,
               prompt_version: str = DEFAULT_PROMPT_VERSION) -> AdvisorReview:
        """Run shadow-mode advisor review on a Decision Package."""
        return self._engine.review(
            package, provider_id=provider_id, prompt_version=prompt_version,
        )

    def review_trade(self, event_id: str, *,
                     provider_id: str = DEFAULT_PROVIDER,
                     prompt_version: str = DEFAULT_PROMPT_VERSION,
                     **layer_outputs: Any) -> AdvisorReview:
        """Build package and review in one call."""
        package = self.build_package(event_id, **layer_outputs)
        return self.review(package, provider_id=provider_id,
                         prompt_version=prompt_version)

    def review_multi(self, package: DecisionPackage, *,
                     provider_ids: list[str],
                     prompt_version: str = DEFAULT_PROMPT_VERSION) -> list[AdvisorReview]:
        """Send one package to multiple providers (multi-model ready)."""
        return self._engine.review_multi(
            package, provider_ids=provider_ids, prompt_version=prompt_version,
        )

    def list_providers(self) -> list[dict[str, Any]]:
        return self._registry.list_all()

    def provider_health(self) -> dict[str, Any]:
        return self._registry.health_check_all()

    def advisor_score(self) -> dict[str, Any]:
        return self._score.compute()

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._history.recent(limit)

    def prompt_versions(self) -> list[str]:
        return PromptBuilder().list_versions()

    @staticmethod
    def _status_label(status: str) -> str:
        labels = {
            "running": "يعمل",
            "connected": "متصل",
            "disconnected": "غير متصل",
            "disabled": "معطّل",
            "failed": "فشل",
        }
        return labels.get(status or "", status or "—")

    @staticmethod
    def _agreement_label(agreement: str | None) -> str:
        labels = {
            "agree": "موافق",
            "disagree": "غير موافق",
            "partial": "جزئي",
        }
        return labels.get((agreement or "").lower(), agreement or "—")

    def _resolved_runtime_state(self) -> dict[str, Any]:
        """Merge persisted runtime state with advisor_history.jsonl truth."""
        state_store = AdvisorRuntimeState()
        runtime = state_store.load()
        hist_store = AdvisorRuntimeHistory()
        hist_count = hist_store.count()
        last_hist = hist_store.last() or {}

        if hist_count < 1:
            return runtime

        patch: dict[str, Any] = {}
        review_count = max(int(runtime.get("successful_reviews") or 0), hist_count)
        patch["successful_reviews"] = review_count

        status = runtime.get("status", "disconnected")
        if review_count > 0 and status in ("disabled", "disconnected", "connected"):
            status = "running"
            patch["status"] = status

        field_map = {
            "provider": "provider",
            "model": "model",
            "review_id": "review_id",
            "latency_ms": "latency_ms",
            "prompt_tokens": "prompt_tokens",
            "completion_tokens": "completion_tokens",
            "total_tokens": "total_tokens",
            "estimated_cost": "estimated_cost",
            "grounding_score": "grounding_score",
            "hallucination_score": "hallucination_score",
            "agreement": "agreement",
            "confidence": "confidence",
        }
        for rt_key, hist_key in field_map.items():
            if not runtime.get(rt_key) and last_hist.get(hist_key) is not None:
                patch[rt_key] = last_hist[hist_key]

        if not runtime.get("last_review_at") and last_hist.get("timestamp"):
            patch["last_review_at"] = last_hist["timestamp"]

        if patch:
            state_store.save(patch)
            runtime = {**runtime, **patch}
        return runtime

    def to_ui_summary(self) -> dict[str, Any]:
        """UI presentation model — runtime metrics and status."""
        score_data = self.advisor_score()
        health = self.provider_health()
        recent = self.history(5)
        runtime = self._resolved_runtime_state()
        last_hist = AdvisorRuntimeHistory().last() or {}
        cfg = load_config()
        eff_provider = effective_provider_id(cfg)

        status = runtime.get("status", "disconnected")
        successful = int(runtime.get("successful_reviews") or 0)

        last_review_time = ""
        if runtime.get("last_review_at"):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(runtime["last_review_at"].replace("Z", "+00:00"))
                last_review_time = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                last_review_time = runtime["last_review_at"][:19]

        return {
            "available": True,
            "shadow_mode": cfg.shadow_mode,
            "version": AI_ADVISOR_VERSION,
            "runtime_status": status,
            "runtime_status_label": self._status_label(status),
            "provider": runtime.get("provider") or eff_provider,
            "model": runtime.get("model") or cfg.effective_model(),
            "last_review_time": last_review_time,
            "latency_ms": runtime.get("latency_ms") or last_hist.get("latency_ms"),
            "prompt_tokens": runtime.get("prompt_tokens") or last_hist.get("prompt_tokens"),
            "completion_tokens": runtime.get("completion_tokens") or last_hist.get("completion_tokens"),
            "total_tokens": runtime.get("total_tokens") or last_hist.get("total_tokens"),
            "estimated_cost": runtime.get("estimated_cost") or last_hist.get("estimated_cost"),
            "grounding_score": runtime.get("grounding_score") or last_hist.get("grounding_score"),
            "hallucination_score": runtime.get("hallucination_score") or last_hist.get("hallucination_score"),
            "review_id": runtime.get("review_id") or last_hist.get("review_id", ""),
            "successful_reviews": successful,
            "agreement": runtime.get("agreement") or last_hist.get("agreement"),
            "agreement_label": self._agreement_label(
                runtime.get("agreement") or last_hist.get("agreement"),
            ),
            "confidence": runtime.get("confidence") or last_hist.get("confidence"),
            "advisor_score": score_data.get("advisor_score", 0),
            "grade": score_data.get("grade", "—"),
            "metrics": score_data.get("metrics", {}),
            "providers": {
                "total": health.get("total", 0),
                "healthy": health.get("healthy", 0),
                "list": self.list_providers(),
            },
            "recent_reviews": [
                {
                    "review_id": r.get("record_id"),
                    "event_id": r.get("event_id"),
                    "provider": r.get("provider_id"),
                    "accepted": r.get("accepted"),
                    "agreement": (r.get("response") or {}).get("agreement"),
                }
                for r in recent
            ],
            "prompt_versions": self.prompt_versions(),
            "package_diagnostics": runtime.get("package_diagnostics") or {},
            "analyst": self._analyst_card(
                runtime.get("review_id") or last_hist.get("review_id", ""),
            ),
        }

    def _analyst_card(self, review_id: str) -> dict[str, Any]:
        """Dashboard AI Analyst card — last review outlook without re-calling LLM."""
        empty = {
            "title_ar": "محلل الأسواق بالذكاء",
            "advisor_decision": "—",
            "current_market_view": "—",
            "near_term_outlook": "—",
            "advisor_confidence": "—",
            "prediction_probability": "غير متاح",
            "platform_confidence": "—",
            "provider": "—",
            "model": "—",
            "latency_ms": None,
            "tokens": None,
            "cost": None,
            "risk_level": "—",
        }
        if not review_id:
            return empty
        try:
            mem = self._memory.load(review_id)
            response = (mem or {}).get("response") or {}
            meta = (mem or {}).get("metadata") or {}
            from scanner.ai_advisor.explainability.localized_presentation import build_presentation
            p = build_presentation({**response, **{
                "provider": (mem or {}).get("provider_id") or meta.get("provider"),
                "model": (mem or {}).get("model") or meta.get("model"),
                "symbol": meta.get("symbol") or (mem or {}).get("symbol"),
                "timeframe": meta.get("timeframe") or (mem or {}).get("timeframe"),
            }}, "ar")
            risks = p.get("main_risks") or []
            risk_level = "مرتفع" if len(risks) >= 3 else ("متوسط" if risks else "منخفض")
            return {
                "title_ar": "محلل الأسواق بالذكاء",
                "advisor_decision": p.get("advisor_decision") or p.get("final_verdict") or "—",
                "current_market_view": p.get("current_market_view") or "—",
                "near_term_outlook": p.get("near_term_outlook") or "—",
                "advisor_confidence": p.get("advisor_confidence_display") or p.get("confidence_display") or "—",
                "prediction_probability": p.get("prediction_probability_display") or "غير متاح",
                "platform_confidence": p.get("platform_confidence_display") or "—",
                "provider": p.get("technical", {}).get("provider") or (mem or {}).get("provider_id") or "—",
                "model": p.get("technical", {}).get("model") or (mem or {}).get("model") or "—",
                "latency_ms": (mem or {}).get("latency_ms") or meta.get("latency_ms"),
                "tokens": (mem or {}).get("total_tokens") or meta.get("total_tokens"),
                "cost": (mem or {}).get("estimated_cost") or meta.get("estimated_cost"),
                "risk_level": risk_level,
                "review_id": review_id,
                "symbol": p.get("symbol") or "",
            }
        except Exception:  # noqa: BLE001
            return empty
