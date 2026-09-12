# -*- coding: utf-8 -*-
"""Deterministic package compression — no AI summarization."""
from __future__ import annotations

import json
from typing import Any

from .unified_package import UnifiedDecisionPackage


def compress_package(package: UnifiedDecisionPackage) -> tuple[UnifiedDecisionPackage, dict[str, Any]]:
    """Apply deterministic compression. Returns (package, compression_stats)."""
    data = package.to_dict()
    original_size = len(json.dumps(data, default=str))
    original_evidence = len(package.evidence_index)

    data = _remove_empty_sections(data)
    data = _dedupe_evidence(data)
    data = _merge_repeated_facts(data)
    data = _summarize_repetitive_stats(data)

    compressed_size = len(json.dumps(data, default=str))
    ratio = round(compressed_size / original_size, 3) if original_size else 1.0

    stats = {
        "original_size_bytes": original_size,
        "compressed_size_bytes": compressed_size,
        "compression_ratio": ratio,
        "evidence_before": original_evidence,
        "evidence_after": len(data.get("evidence_index") or []),
    }

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

    compressed = UnifiedDecisionPackage(
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
        diagnostics={**package.diagnostics, **stats},
        schema_version=package.schema_version,
        built_at=package.built_at,
        shadow_mode=package.shadow_mode,
    )
    return compressed, stats


def _remove_empty_sections(data: dict[str, Any]) -> dict[str, Any]:
    section_keys = (
        "knowledge", "similarity", "research",
        "feature_intelligence", "feature_snapshot", "prediction", "optimization",
    )
    for key in section_keys:
        section = data.get(key)
        if isinstance(section, dict) and section.get("available") is False:
            data[key] = {"available": False}
        elif isinstance(section, dict) and not _has_content(section):
            data[key] = {"available": False}
    return data


def _has_content(section: dict) -> bool:
    for k, v in section.items():
        if k == "available":
            continue
        if v not in (None, "", [], {}):
            return True
    return False


def _dedupe_evidence(data: dict[str, Any]) -> dict[str, Any]:
    seen: set[str] = set()
    unique = []
    for item in data.get("evidence_index") or []:
        key = f"{item.get('section')}.{item.get('field')}={item.get('value')!r}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    data["evidence_index"] = unique
    return data


def _merge_repeated_facts(data: dict[str, Any]) -> dict[str, Any]:
    knowledge = data.get("knowledge") or {}
    facts = knowledge.get("knowledge_facts") or []
    if isinstance(facts, list):
        knowledge["knowledge_facts"] = list(dict.fromkeys(facts))
        data["knowledge"] = knowledge
    return data


def _summarize_repetitive_stats(data: dict[str, Any]) -> dict[str, Any]:
    for section_key in ("similarity", "research", "optimization"):
        section = data.get(section_key)
        if not isinstance(section, dict):
            continue
        stats = section.get("statistics")
        if isinstance(stats, dict) and len(json.dumps(stats)) > 500:
            section["statistics"] = {
                k: stats[k] for k in list(stats.keys())[:8]
            }
    return data
