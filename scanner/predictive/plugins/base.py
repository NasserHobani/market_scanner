# -*- coding: utf-8 -*-
"""Predictive model plugin base class."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrainResult:
    """Result of a training run."""

    success: bool
    model: Any = None
    train_metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "train_metrics": dict(self.train_metrics),
            "notes": list(self.notes),
        }


@dataclass
class PluginMetadata:
    """Plugin descriptor."""

    name: str
    version: str
    task_types: list[str]
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "task_types": list(self.task_types),
            "description": self.description,
        }


class PredictiveModel(ABC):
    """Base class for all predictive model plugins."""

    @property
    @abstractmethod
    def plugin_name(self) -> str: ...

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata: ...

    @abstractmethod
    def train(self, X: list[list[float]], y: list[float | int], *,
              feature_names: list[str] | None = None,
              hyperparameters: dict[str, Any] | None = None,
              task_type: str = "classification") -> TrainResult: ...

    @abstractmethod
    def predict(self, X: list[list[float]], *,
                feature_names: list[str] | None = None) -> list[float]: ...

    @abstractmethod
    def predict_proba(self, X: list[list[float]], *,
                      feature_names: list[str] | None = None) -> list[float] | None: ...

    @abstractmethod
    def evaluate(self, X: list[list[float]], y: list[float | int], *,
                 feature_names: list[str] | None = None,
                 task_type: str = "classification") -> dict[str, Any]: ...

    @abstractmethod
    def save(self, path: str) -> None: ...

    @classmethod
    @abstractmethod
    def load(cls, path: str) -> PredictiveModel: ...

    def plugin_metadata(self) -> dict[str, Any]:
        return self.metadata.to_dict()
