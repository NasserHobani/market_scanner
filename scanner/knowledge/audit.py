# -*- coding: utf-8 -*-
"""Audit trail for reproducible knowledge capture."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    REJECTED = "rejected"
    PARTIAL = "partial"


@dataclass
class AuditTrail:
    """Provenance and pipeline metadata for any knowledge object."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    creator: str = "knowledge_builder"
    version: str = "1.1.0"
    verification_status: str = VerificationStatus.UNVERIFIED.value
    source: str = "platform"
    pipeline_stage: str = "capture"

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at.isoformat(),
            "creator": self.creator,
            "version": self.version,
            "verification_status": self.verification_status,
            "source": self.source,
            "pipeline_stage": self.pipeline_stage,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any] | None) -> AuditTrail:
        if not row:
            return cls()
        created = row.get("created_at")
        return cls(
            created_at=(datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        if created else datetime.now(timezone.utc)),
            creator=str(row.get("creator") or "unknown"),
            version=str(row.get("version") or "1.0.0"),
            verification_status=str(row.get("verification_status")
                                   or VerificationStatus.UNVERIFIED.value),
            source=str(row.get("source") or "unknown"),
            pipeline_stage=str(row.get("pipeline_stage") or "capture"),
        )
