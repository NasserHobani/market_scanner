# -*- coding: utf-8 -*-
"""Token budget optimization — priority-based section pruning."""
from __future__ import annotations

import json
from typing import Any

from .unified_package import UnifiedDecisionPackage

DEFAULT_TOKEN_BUDGET = 12000
CHARS_PER_TOKEN = 4

# Priority: lower number = higher priority (never remove Critical)
SECTION_PRIORITY = {
    "recommendation": 0,   # Critical
    "reasoning": 0,        # Critical
    "decision_ai": 0,      # Critical (guardrails)
    "evidence_index": 0,   # Critical
    "metadata": 1,         # High
    "knowledge": 1,
    "similarity": 2,       # Medium
    "prediction": 2,
    "research": 3,         # Low
    "feature_intelligence": 3,
    "feature_snapshot": 1,
    "optimization": 3,
}


def estimate_tokens(package: UnifiedDecisionPackage) -> int:
    text = json.dumps(package.to_dict(), default=str)
    return max(1, len(text) // CHARS_PER_TOKEN)


def optimize_tokens(package: UnifiedDecisionPackage, *,
                    budget: int = DEFAULT_TOKEN_BUDGET) -> tuple[UnifiedDecisionPackage, dict[str, Any]]:
    """Prune low-priority sections when token estimate exceeds budget."""
    included = list(SECTION_PRIORITY.keys())
    removed: list[str] = []
    data = package.to_dict()

    current_tokens = estimate_tokens(package)
    if current_tokens <= budget:
        return package, {
            "token_estimate": current_tokens,
            "token_budget": budget,
            "sections_included": included,
            "sections_removed": removed,
        }

    # Remove lowest priority sections first
    for priority in sorted(set(SECTION_PRIORITY.values()), reverse=True):
        if current_tokens <= budget:
            break
        for section, pri in sorted(SECTION_PRIORITY.items(), key=lambda x: -x[1]):
            if pri != priority or section in ("recommendation", "reasoning", "decision_ai", "evidence_index"):
                continue
            if section in removed:
                continue
            if section == "evidence_index":
                continue
            if section in data and data[section].get("available") is not False:
                data[section] = {"available": False, "pruned": True}
                removed.append(section)
                current_tokens = len(json.dumps(data, default=str)) // CHARS_PER_TOKEN

    from .unified_package import EvidenceTrace, UnifiedDecisionPackage

    evidence = tuple(
        EvidenceTrace(
            evidence_id=e["evidence_id"],
            source_layer=e.get("source_layer", ""),
            section=e["section"],
            field=e["field"],
            label=e["label"],
            value=e["value"],
            timestamp=e.get("timestamp", ""),
            confidence=e.get("confidence"),
            reference=e.get("reference", ""),
        )
        for e in (data.get("evidence_index") or [])
    )

    optimized = UnifiedDecisionPackage(
        package_id=package.package_id,
        event_id=package.event_id,
        metadata=data.get("metadata") or {},
        recommendation=data.get("recommendation") or {},
        knowledge=data.get("knowledge") or {},
        reasoning=data.get("reasoning") or {},
        similarity=data.get("similarity") or {},
        research=data.get("research") or {},
        feature_intelligence=data.get("feature_intelligence") or {},
        feature_snapshot=data.get("feature_snapshot") or package.feature_snapshot or {},
        prediction=data.get("prediction") or {},
        optimization=data.get("optimization") or {},
        decision_ai=data.get("decision_ai") or {},
        evidence_index=evidence,
        diagnostics={
            **package.diagnostics,
            "token_estimate": current_tokens,
            "token_budget": budget,
            "sections_included": [s for s in included if s not in removed],
            "sections_removed": removed,
        },
        schema_version=package.schema_version,
        built_at=package.built_at,
        shadow_mode=package.shadow_mode,
    )
    return optimized, optimized.diagnostics
