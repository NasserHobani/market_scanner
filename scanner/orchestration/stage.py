# -*- coding: utf-8 -*-
"""Stage engine — prepare, execute, validate, cleanup."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Callable

from .execution_context import ExecutionContext
from .result import AnalysisStatus, StageExecutionResult


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


StageHandler = Callable[[ExecutionContext], dict[str, Any]]


class Stage(ABC):
    """Base stage interface."""

    name: str = ""
    optional: bool = False
    cacheable: bool = False

    @abstractmethod
    def prepare(self, ctx: ExecutionContext) -> list[str]:
        """Validate inputs. Return list of errors (empty = ok)."""

    @abstractmethod
    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        """Run stage logic. Return output dict."""

    @abstractmethod
    def validate(self, output: dict[str, Any]) -> list[str]:
        """Validate output. Return list of errors."""

    def cleanup(self, ctx: ExecutionContext) -> None:
        """Optional cleanup — default no-op."""


class HandlerStage(Stage):
    """Stage backed by injectable handler callable."""

    def __init__(self, name: str, handler: StageHandler, *,
                 optional: bool = False,
                 cacheable: bool = False,
                 input_validator: Callable[[ExecutionContext], list[str]] | None = None,
                 output_validator: Callable[[dict], list[str]] | None = None) -> None:
        self.name = name
        self._handler = handler
        self.optional = optional
        self.cacheable = cacheable
        self._input_validator = input_validator
        self._output_validator = output_validator

    def prepare(self, ctx: ExecutionContext) -> list[str]:
        if self._input_validator:
            return self._input_validator(ctx)
        return []

    def execute(self, ctx: ExecutionContext) -> dict[str, Any]:
        return self._handler(ctx)

    def validate(self, output: dict[str, Any]) -> list[str]:
        if self._output_validator:
            return self._output_validator(output)
        if not output and not self.optional:
            return [f"{self.name}: empty output"]
        return []


class StageRunner:
    """Run a single stage with timing and result tracking."""

    def run(self, stage: Stage, ctx: ExecutionContext, *,
            cached_output: dict[str, Any] | None = None) -> tuple[ExecutionContext, StageExecutionResult]:
        started = _now()
        t0 = time.perf_counter()
        retry_count = 0

        if cached_output is not None:
            duration = (time.perf_counter() - t0) * 1000
            updated = self._apply_output(ctx, stage.name, cached_output)
            return updated, StageExecutionResult(
                stage=stage.name,
                status=AnalysisStatus.COMPLETED.value,
                started_at=started,
                completed_at=_now(),
                duration_ms=duration,
                cached=True,
                output_keys=list(cached_output.keys()),
            )

        errors = stage.prepare(ctx)
        if errors:
            if stage.optional:
                return ctx, StageExecutionResult(
                    stage=stage.name,
                    status=AnalysisStatus.SKIPPED.value,
                    started_at=started,
                    completed_at=_now(),
                    error="; ".join(errors),
                )
            return ctx, StageExecutionResult(
                stage=stage.name,
                status=AnalysisStatus.FAILED.value,
                started_at=started,
                completed_at=_now(),
                error="; ".join(errors),
            )

        try:
            output = stage.execute(ctx)
            val_errors = stage.validate(output)
            if val_errors and not stage.optional:
                return ctx, StageExecutionResult(
                    stage=stage.name,
                    status=AnalysisStatus.FAILED.value,
                    started_at=started,
                    completed_at=_now(),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    error="; ".join(val_errors),
                )
            updated = self._apply_output(ctx, stage.name, output)
            stage.cleanup(updated)
            return updated, StageExecutionResult(
                stage=stage.name,
                status=AnalysisStatus.COMPLETED.value,
                started_at=started,
                completed_at=_now(),
                duration_ms=(time.perf_counter() - t0) * 1000,
                retry_count=retry_count,
                output_keys=list(output.keys()),
            )
        except Exception as exc:
            if stage.optional:
                return ctx, StageExecutionResult(
                    stage=stage.name,
                    status=AnalysisStatus.SKIPPED.value,
                    started_at=started,
                    completed_at=_now(),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    error=str(exc),
                )
            return ctx, StageExecutionResult(
                stage=stage.name,
                status=AnalysisStatus.FAILED.value,
                started_at=started,
                completed_at=_now(),
                duration_ms=(time.perf_counter() - t0) * 1000,
                error=str(exc),
            )

    @staticmethod
    def _apply_output(ctx: ExecutionContext, stage: str,
                      output: dict[str, Any]) -> ExecutionContext:
        updates: dict[str, Any] = {"stage_outputs": {**ctx.stage_outputs, stage: output}}
        field_map = {
            "load_market": ("symbol", "market", "timeframe", "scan_source"),
            "knowledge": ("knowledge", "event_id"),
            "reasoning": ("reasoning",),
            "similarity": ("similarity",),
            "research": ("research",),
            "prediction": ("prediction",),
            "decision_ai": ("decision_review",),
        }
        for key, fields in field_map.items():
            if stage == key:
                for f in fields:
                    if f in output:
                        updates[f] = output[f]
        if stage == "knowledge" and "knowledge_context" in output:
            updates["knowledge"] = output["knowledge_context"]
        return ctx.with_updates(**updates)
