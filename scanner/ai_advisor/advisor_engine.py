# -*- coding: utf-8 -*-
"""Advisor engine — orchestrates shadow-mode LLM review."""
from __future__ import annotations

import time
from typing import Any

from .advisor_logging import log_runtime
from .decision_package import DecisionPackage, DecisionPackageBuilder
from .unified_package import UnifiedDecisionPackage
from .unified_pipeline import PackageBuildResult, build_unified_package
from .memory import AdvisorMemory
from .prompt_builder import PromptBuilder, DEFAULT_PROMPT_VERSION
from .provider_config import load_config, effective_provider_id
from .provider_registry import ProviderRegistry, get_registry
from .response_parser import ResponseParser, ResponseParseError
from .response_validator import ResponseValidator
from .review import AdvisorReview, ReviewEngine
from .runtime_history import AdvisorRuntimeHistory
from .token_cost import estimate_cost

DEFAULT_PROVIDER = "mock"


class AdvisorEngine:
    """Core orchestrator: package → prompt → provider → validate → review.

    SHADOW MODE: never modifies platform decisions.
    """

    def __init__(self,
                 package_builder: DecisionPackageBuilder | None = None,
                 prompt_builder: PromptBuilder | None = None,
                 parser: ResponseParser | None = None,
                 validator: ResponseValidator | None = None,
                 review_engine: ReviewEngine | None = None,
                 registry: ProviderRegistry | None = None,
                 memory: AdvisorMemory | None = None,
                 runtime_history: AdvisorRuntimeHistory | None = None) -> None:
        self._packages = package_builder or DecisionPackageBuilder()
        self._prompts = prompt_builder or PromptBuilder()
        self._parser = parser or ResponseParser()
        self._validator = validator or ResponseValidator()
        self._review = review_engine or ReviewEngine()
        self._registry = registry or get_registry()
        self._memory = memory or AdvisorMemory()
        self._history = runtime_history or AdvisorRuntimeHistory()
        self.last_call_metrics: dict[str, Any] = {}
        self.last_package_diagnostics: dict[str, Any] = {}

    def build_package(self, event_id: str, **layer_outputs: Any) -> UnifiedDecisionPackage:
        extras = dict(layer_outputs)
        profile = extras.pop("context_profile", None)
        budget = extras.pop("token_budget", None)
        if profile or budget:
            try:
                from scanner.ai_advisor.analyst.context_profile import resolve_budget
                budget = resolve_budget(profile, budget)
            except Exception:  # noqa: BLE001
                budget = budget or 12000
            extras.setdefault("metadata", {})
            if isinstance(extras["metadata"], dict) and profile:
                extras["metadata"] = {**extras["metadata"], "context_profile": profile}
            result = build_unified_package(
                event_id=event_id, token_budget=int(budget or 12000), **extras,
            )
        else:
            result = build_unified_package(event_id=event_id, **extras)
        self.last_package_diagnostics = result.diagnostics
        if not result.package:
            errors = (result.validation.errors if result.validation else ["validation failed"])
            raise ValueError(f"Package validation failed: {'; '.join(errors)}")
        return result.package

    def build_legacy_package(self, event_id: str, **layer_outputs: Any) -> DecisionPackage:
        """Legacy DecisionPackage builder for backward-compatible tests."""
        return (DecisionPackageBuilder()).build(event_id=event_id, **layer_outputs)

    def review(self, package: DecisionPackage | UnifiedDecisionPackage, *,
               provider_id: str = "",
               prompt_version: str = "") -> AdvisorReview:
        cfg = load_config()
        provider_id = provider_id or effective_provider_id(cfg) or DEFAULT_PROVIDER
        prompt_version = prompt_version or cfg.prompt_version or DEFAULT_PROMPT_VERSION

        provider = self._registry.get(provider_id)
        profile = ""
        if hasattr(package, "metadata"):
            profile = str((package.metadata or {}).get("context_profile") or "")
        prompt = self._prompts.build(package, version=prompt_version, context_profile=profile)

        log_runtime("Claude Request Sent")
        start = time.monotonic()
        try:
            raw_response = provider.analyze(prompt, package=package)
        except Exception as exc:
            log_runtime("Claude Request Failed")
            raise

        latency_ms = round((time.monotonic() - start) * 1000, 1)
        log_runtime("Claude Response Received")

        usage = getattr(provider, "last_usage", {}) or {}
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))

        try:
            parsed = self._parser.parse(raw_response)
        except ResponseParseError as exc:
            log_runtime("Response Parse Failed")
            return self._rejected_review(
                package, prompt, provider_id, provider.model_name(),
                reason=str(exc), raw=raw_response if isinstance(raw_response, dict) else {},
                latency_ms=latency_ms,
            )

        log_runtime("Response Parsed")
        try:
            from scanner.ai_advisor.analyst.normalize import normalize_analyst_response
            parsed = normalize_analyst_response(parsed)
        except Exception:  # noqa: BLE001
            pass

        # بوّابة الاحتمال: الموجّه *يطلب* ألّا يخترع النموذج احتمالاً،
        # وهنا يُفرَض الطلب. تُطبَّق بعد التطبيع وقبل التحقّق كي تدخل
        # المخالفات في درجة الهلوسة بدل أن تمرّ صامتة.
        gate_violations: list[str] = []
        try:
            from scanner.ai_advisor.analyst.gate import gate_prediction
            parsed, gate_violations = gate_prediction(
                parsed, getattr(package, "prediction", None)
            )
        except Exception:  # noqa: BLE001
            gate_violations = []

        validation = self._validator.validate(parsed, package)
        validation_dict = validation.to_dict()
        if gate_violations:
            validation_dict["hallucinations"] = list(
                validation_dict.get("hallucinations") or []
            ) + gate_violations
            validation_dict["hallucination_count"] = int(
                validation_dict.get("hallucination_count") or 0
            ) + len(gate_violations)
            validation_dict["prediction_gate_violations"] = list(gate_violations)
        grounding_score = self._grounding_score(validation_dict)
        hallucination_score = self._hallucination_score(validation_dict)

        self.last_call_metrics = {
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": estimate_cost(
                provider.model_name(),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            ),
            "grounding_score": grounding_score,
            "hallucination_score": hallucination_score,
        }

        review = self._review.build(
            package=package,
            prompt=prompt,
            provider_id=provider_id,
            model_name=provider.model_name(),
            parsed=parsed,
            validation=validation_dict,
            raw_response=raw_response if isinstance(raw_response, dict) else parsed,
        )

        if review.accepted:
            log_runtime("Validation Passed")
            meta = getattr(package, "metadata", {}) or {}
            sym = meta.get("symbol", "") if hasattr(package, "metadata") else package.trade.get("symbol", "")
            mkt = meta.get("market", "") if hasattr(package, "metadata") else package.trade.get("market", "")
            tf = meta.get("timeframe", "") if hasattr(package, "metadata") else package.trade.get("timeframe", "")
            tid = meta.get("trade_id", "") if hasattr(package, "metadata") else package.trade.get("trade_id", "")
            self._memory.save(
                package_id=package.package_id,
                event_id=package.event_id,
                prompt_version=prompt.version,
                provider_id=provider_id,
                model_name=provider.model_name(),
                response=review.to_dict(),
                accepted=True,
                rejected=False,
                rejection_reason="",
                review_id=review.review_id,
                trade_id=tid,
                symbol=sym,
                market=mkt,
                timeframe=tf,
            )
            self._history.save({
                "review_id": review.review_id,
                "trade_id": package.metadata.get("trade_id", "") if hasattr(package, "metadata") else package.trade.get("trade_id", ""),
                "provider": provider_id,
                "model": provider.model_name(),
                "event_id": package.event_id,
                "symbol": package.metadata.get("symbol", "") if hasattr(package, "metadata") else package.trade.get("symbol", ""),
                "latency_ms": latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "estimated_cost": self.last_call_metrics["estimated_cost"],
                "confidence": review.confidence,
                "agreement": review.agreement,
                "warnings": list(review.risks),
                "grounding_score": grounding_score,
                "hallucination_score": hallucination_score,
            })
            # البيانات الوصفية كانت تُكتب في مسار التحليل اليدوي وحده،
            # فظهر عمود «الفريم» فارغاً لكل مراجعة تلقائية — وهي أغلب
            # المراجعات. كتابتها هنا تشمل المسارين بلا تكرار، ولا
            # تكتب فوق ما سجّله المسار اليدوي (يحمل نوعاً أدقّ).
            try:
                from .explainability.review_meta import ReviewMetaStore

                store = ReviewMetaStore()
                if not store.get(review.review_id):
                    store.save(
                        review_id=review.review_id,
                        review_type="automatic",
                        symbol=sym, market=mkt, timeframe=tf,
                        recommendation=dict(
                            getattr(package, "recommendation", {}) or {}),
                    )
            except Exception:  # noqa: BLE001
                # فشل تسجيل بيانات العرض لا يُسقط مراجعة صالحة
                pass
            log_runtime("History Saved")
        else:
            log_runtime("Validation Failed")

        return review

    def review_multi(self, package: DecisionPackage | UnifiedDecisionPackage, *,
                     provider_ids: list[str],
                     prompt_version: str = DEFAULT_PROMPT_VERSION) -> list[AdvisorReview]:
        return [
            self.review(package, provider_id=pid, prompt_version=prompt_version)
            for pid in provider_ids
        ]

    def _rejected_review(self, package: DecisionPackage | UnifiedDecisionPackage, prompt: Any,
                         provider_id: str, model_name: str,
                         reason: str, raw: dict,
                         latency_ms: float = 0) -> AdvisorReview:
        validation = {"valid": False, "rejected": True, "errors": [reason]}
        review = self._review.build(
            package=package,
            prompt=prompt,
            provider_id=provider_id,
            model_name=model_name,
            parsed={"agreement": "partial", "confidence": 0,
                    "summary": "Review rejected", "reasoning": reason,
                    "supporting_evidence": [], "contradicting_evidence": [],
                    "risks": [reason], "missing_information": [],
                    "suggested_experiment": None,
                    "shadow_mode_acknowledged": True},
            validation=validation,
            raw_response=raw,
        )
        self.last_call_metrics = {
            "latency_ms": latency_ms,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost": 0.0,
            "grounding_score": 0,
            "hallucination_score": 100,
        }
        return review

    @staticmethod
    def _grounding_score(validation: dict[str, Any]) -> float:
        failures = len(validation.get("grounding_failures", []))
        hallucinations = len(validation.get("hallucinations", []))
        score = 100.0 - failures * 25 - hallucinations * 50
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _hallucination_score(validation: dict[str, Any]) -> float:
        count = validation.get("hallucination_count", 0)
        if count == 0:
            return 0.0
        return round(min(100.0, count * 50), 1)
