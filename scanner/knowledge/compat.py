# -*- coding: utf-8 -*-
"""Backward compatibility with Sprint AI-01 snapshots."""
from __future__ import annotations

from typing import Any

from .versioning import KNOWLEDGE_SCHEMA_VERSION, SchemaMetadata


def is_legacy_snapshot(row: dict[str, Any]) -> bool:
    schema = row.get("schema") or {}
    version = schema.get("schema_version") if isinstance(schema, dict) else None
    return not version or str(version) < KNOWLEDGE_SCHEMA_VERSION


def upgrade_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Upgrade v1.0 payload to v1.1 in-memory — non-destructive."""
    if not is_legacy_snapshot(row):
        return row
    upgraded = dict(row)
    if "schema" not in upgraded:
        upgraded["schema"] = SchemaMetadata(schema_version=KNOWLEDGE_SCHEMA_VERSION).to_dict()
    else:
        upgraded["schema"] = SchemaMetadata.from_dict(upgraded["schema"]).to_dict()
        upgraded["schema"]["schema_version"] = KNOWLEDGE_SCHEMA_VERSION
    if "audit" not in upgraded:
        upgraded["audit"] = {"creator": "legacy", "pipeline_stage": "import"}
    if "quality" not in upgraded:
        upgraded["quality"] = {"completeness_score": 1.0, "warnings": ["upgraded from v1.0"]}
    if "fingerprint" not in upgraded and upgraded.get("symbol"):
        from .fingerprint import market_fingerprint
        upgraded["fingerprint"] = market_fingerprint(upgraded)
    return upgraded
