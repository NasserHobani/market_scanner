# -*- coding: utf-8 -*-
"""Pipeline interfaces — protocols for DI and testing."""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

from .events import DomainEvent
from .state import PipelineExecution, StageResult


@runtime_checkable
class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> None: ...

    def subscribe(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None: ...


@runtime_checkable
class StageExecutor(Protocol):
    @property
    def name(self) -> str: ...

    def execute(self, context: dict[str, Any]) -> dict[str, Any]: ...

    def validate_input(self, context: dict[str, Any]) -> list[str]: ...

    def validate_output(self, output: dict[str, Any]) -> list[str]: ...


@runtime_checkable
class PipelineRepository(Protocol):
    def save(self, execution: PipelineExecution) -> str: ...

    def load(self, execution_id: str) -> PipelineExecution: ...

    def history(self, *, limit: int = 50,
                pipeline_type: str | None = None,
                event_id: str | None = None) -> list[PipelineExecution]: ...


@runtime_checkable
class PipelineCoordinator(Protocol):
    def execute(self, pipeline_type: str, context: dict[str, Any]) -> PipelineExecution: ...

    def retry(self, execution_id: str, *,
              stage: str | None = None) -> PipelineExecution: ...

    def status(self, execution_id: str) -> PipelineExecution: ...

    def history(self, **kwargs: Any) -> list[PipelineExecution]: ...
