# -*- coding: utf-8 -*-
"""Schema versioning for safe evolution of stored snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

KNOWLEDGE_SCHEMA_VERSION = "1.1"
GENERATOR_VERSION = "1.1.0"


def _platform_version() -> str:
    try:
        from scanner import __version__
        return __version__
    except Exception:  # noqa: BLE001
        return "unknown"


@dataclass
class SchemaMetadata:
    """Version metadata attached to every snapshot."""

    schema_version: str = KNOWLEDGE_SCHEMA_VERSION
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = "knowledge_builder"
    generator_version: str = GENERATOR_VERSION
    platform_version: str = field(default_factory=_platform_version)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "generator_version": self.generator_version,
            "platform_version": self.platform_version,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> SchemaMetadata:
        if not row:
            return cls(schema_version="1.0")
        created = row.get("created_at")
        return cls(
            schema_version=str(row.get("schema_version") or "1.0"),
            created_at=(datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        if created else datetime.now(timezone.utc)),
            created_by=str(row.get("created_by") or "unknown"),
            generator_version=str(row.get("generator_version") or "1.0.0"),
            platform_version=str(row.get("platform_version") or "unknown"),
        )
