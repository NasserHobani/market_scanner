# -*- coding: utf-8 -*-
"""Pipeline validation — no silent failures."""
from __future__ import annotations

from typing import Any


class ValidationError(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_scan_source(source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("symbol", "market", "timeframe"):
        if not source.get(field):
            errors.append(f"missing required field: {field}")
    return errors


def validate_trade_source(source: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("symbol", "market", "timeframe"):
        if not source.get(field):
            errors.append(f"missing required field: {field}")
    return errors


def validate_knowledge_output(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not output.get("event_id"):
        errors.append("knowledge output missing event_id")
    if "knowledge_ids" not in output:
        errors.append("knowledge output missing knowledge_ids")
    return errors


def validate_reasoning_output(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    review = output.get("reasoning_review")
    if not review:
        errors.append("reasoning output missing reasoning_review")
        return errors
    if not review.get("event_id"):
        errors.append("reasoning review missing event_id")
    if review.get("verdict") is None:
        errors.append("reasoning review missing verdict")
    return errors


def validate_intelligence_output(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    report = output.get("intelligence_report")
    if not report:
        errors.append("intelligence output missing intelligence_report")
        return errors
    for key in ("strategy_id", "patterns", "insights"):
        if key not in report:
            errors.append(f"intelligence report missing {key}")
    return errors


def validate_trade_rows(rows: list[dict]) -> list[str]:
    if not rows:
        return ["trade_rows is empty"]
    errors: list[str] = []
    for i, row in enumerate(rows[:5]):
        if row.get("status") not in ("won", "lost", "open", "pending", "expired"):
            errors.append(f"row[{i}] invalid status: {row.get('status')}")
    return errors


def validate_event_id(event_id: str) -> list[str]:
    if not event_id:
        return ["event_id is required"]
    if not event_id.startswith("ke_"):
        return [f"event_id has unexpected format: {event_id}"]
    return []


def raise_if_errors(errors: list[str], *, stage: str) -> None:
    if errors:
        raise ValidationError([f"[{stage}] {e}" for e in errors])
