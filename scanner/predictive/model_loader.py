# -*- coding: utf-8 -*-
"""Model loader — convenience wrapper over ModelStore."""
from __future__ import annotations

from .model_store import ModelStore
from .trainer import ModelArtifact


class ModelLoader:
    """Load trained models by ID."""

    def __init__(self, store: ModelStore | None = None) -> None:
        self._store = store or ModelStore()

    def load(self, model_id: str) -> ModelArtifact:
        return self._store.load_model(model_id)

    def exists(self, model_id: str) -> bool:
        return self._store.exists(model_id)

    def list_available(self) -> list[str]:
        return [m.model_id for m in self._store.list_models()]
