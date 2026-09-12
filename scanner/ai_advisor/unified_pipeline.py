# -*- coding: utf-8 -*-
"""Unified package pipeline — build, compress, optimize, validate."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .advisor_logging import log_runtime
from .package_cache import PackageCache
from .package_compression import compress_package
from .package_validator import PackageValidationResult, PackageValidator
from .token_optimizer import estimate_tokens, optimize_tokens
from .unified_package import UNIFIED_PACKAGE_VERSION, UnifiedDecisionPackage, UnifiedPackageBuilder

_builder = UnifiedPackageBuilder()
_validator = PackageValidator()
_cache = PackageCache()


@dataclass
class PackageBuildResult:
    package: UnifiedDecisionPackage | None = None
    validation: PackageValidationResult | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    cached: bool = False
    build_time_ms: float = 0.0


# حقول الهويّة: من يتحدّث النموذج عنه، لا ما يعرفه عنه.
#
# ═══ لماذا تُعاد الطباعة على الحزمة المخزَّنة ═══
#
# الذاكرة تُفهرَس ببصمة تشمل الرمز، فالإصابة تعني «الأدلّة نفسها».
# لكنّ الحزمة المستعادة تحمل **هويّة اللحظة التي بُنيت فيها**، وقد تكون
# ناقصة: نداء واحد قديم بلا رمز في بياناته الوصفية يُخزَّن، ثم ترثه كل
# مراجعة تالية لنفس البصمة.
#
# وقد وقع هذا فعلاً: ثلاث مراجعات للبتكوين تشترك في الحزمة
# ``udpkg_53e221c965f00303`` نفسها، فخرجت كلّها بلا رمز — أي أن سجلّ
# المراجعات صار غير قابل للربط بالرمز الذي راجعه، وهو أساس قياس أداء
# المستشار لكل رمز.
#
# فالقاعدة: الأدلّة تُستعاد، والهويّة تُعاد طباعتها من نداء اللحظة.
_IDENTITY_KEYS = ("symbol", "market", "timeframe", "trade_id", "scan_id")


def _restamp_identity(package, *, metadata: dict[str, Any],
                      event_id: str = ""):
    """يعيد ختم حقول الهويّة على حزمة مستعادة من الذاكرة."""
    import dataclasses

    incoming = {k: metadata.get(k) for k in _IDENTITY_KEYS
                if metadata.get(k)}
    if not incoming and not event_id:
        return package
    meta = {**(package.metadata or {}), **incoming}
    if event_id:
        meta["event_id"] = event_id
    try:
        pkg = dataclasses.replace(package, metadata=meta)
        return dataclasses.replace(pkg, event_id=event_id) if event_id else pkg
    except Exception:  # noqa: BLE001
        # ‏dataclass غير مجمَّد أو بنية مختلفة: لا نُسقط المراجعة لأجل ختم
        return package


def build_unified_package(*, event_id: str = "",
                          use_cache: bool = True,
                          token_budget: int = 12000,
                          **layer_outputs: Any) -> PackageBuildResult:
    """Full pipeline: build → compress → optimize → validate."""
    start = time.monotonic()
    result = PackageBuildResult()

    metadata = layer_outputs.get("metadata") or {}
    recommendation = layer_outputs.get("recommendation") or {}
    symbol = metadata.get("symbol") or (layer_outputs.get("knowledge_context") or {}).get("symbol", "")
    market = metadata.get("market") or (layer_outputs.get("knowledge_context") or {}).get("market", "")
    timeframe = metadata.get("timeframe") or (layer_outputs.get("knowledge_context") or {}).get("timeframe", "")

    cache_key = _cache.fingerprint(
        symbol=symbol, market=market, timeframe=timeframe,
        recommendation=recommendation or (layer_outputs.get("knowledge_context") or {}).get("recommendation_snapshot"),
        # الطبقات جزء من البصمة: السوق يتحرّك بينما التوصية ثابتة،
        # وبدونها تُعاد حزمة بحالة سوق قديمة
        evidence_layers=layer_outputs,
    )

    if use_cache:
        cached_pkg = _cache.get(cache_key)
        if cached_pkg:
            log_runtime("Unified Package Created (cached)")
            result.package = _restamp_identity(
                cached_pkg, metadata=metadata,
                event_id=event_id or layer_outputs.get("event_id", ""),
            )
            result.cached = True
            result.diagnostics = dict(cached_pkg.diagnostics)
            result.build_time_ms = round((time.monotonic() - start) * 1000, 1)
            result.validation = _validator.validate(cached_pkg)
            return result

    log_runtime("Evidence Collected")

    eid = event_id or layer_outputs.get("event_id", "")
    package = _builder.build(
        event_id=eid,
        metadata=metadata,
        recommendation=recommendation,
        knowledge_context=layer_outputs.get("knowledge_context"),
        reasoning_review=layer_outputs.get("reasoning_review"),
        similarity_context=layer_outputs.get("similarity_context"),
        research_report=layer_outputs.get("research_report"),
        feature_analysis=layer_outputs.get("feature_analysis"),
        feature_snapshot=layer_outputs.get("feature_snapshot"),
        prediction=layer_outputs.get("prediction"),
        optimization=layer_outputs.get("optimization"),
        decision_ai=layer_outputs.get("decision_ai"),
        guardrails=layer_outputs.get("guardrails"),
        fused_confidence=layer_outputs.get("fused_confidence"),
    )
    log_runtime("Unified Package Created")

    package, compression_stats = compress_package(package)
    log_runtime("Package Compressed")

    package, token_stats = optimize_tokens(package, budget=token_budget)
    log_runtime("Prompt Generated")

    token_est = estimate_tokens(package)
    diagnostics = {
        "package_version": UNIFIED_PACKAGE_VERSION,
        "package_size_bytes": compression_stats.get("compressed_size_bytes", 0),
        "token_estimate": token_est,
        "compression_ratio": compression_stats.get("compression_ratio", 1.0),
        "evidence_count": len(package.evidence_index),
        "sections_included": token_stats.get("sections_included", []),
        "sections_removed": token_stats.get("sections_removed", []),
        "grounding_pct": 100.0,
        **compression_stats,
        **token_stats,
    }
    package = UnifiedDecisionPackage(
        package_id=package.package_id,
        event_id=package.event_id,
        metadata=package.metadata,
        recommendation=package.recommendation,
        knowledge=package.knowledge,
        reasoning=package.reasoning,
        similarity=package.similarity,
        research=package.research,
        feature_intelligence=package.feature_intelligence,
        feature_snapshot=package.feature_snapshot,
        prediction=package.prediction,
        optimization=package.optimization,
        decision_ai=package.decision_ai,
        evidence_index=package.evidence_index,
        diagnostics=diagnostics,
        schema_version=package.schema_version,
        built_at=package.built_at,
        shadow_mode=package.shadow_mode,
    )

    validation = _validator.validate(package)
    result.validation = validation
    result.build_time_ms = round((time.monotonic() - start) * 1000, 1)
    result.diagnostics = diagnostics

    if validation.valid:
        if use_cache:
            _cache.put(cache_key, package)
        result.package = package
    else:
        result.package = None

    return result
