# -*- coding: utf-8 -*-
"""Model persistence — save, load, list, archive, delete."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .model_metadata import ModelMetadata, ModelStatus
from .plugins.base import PredictiveModel
from .plugins.lightgbm import LightGBMPlugin
from .trainer import ModelArtifact

DEFAULT_STORE = Path("data/predictive/models")

PLUGIN_LOADERS: dict[str, type[PredictiveModel]] = {
    "lightgbm": LightGBMPlugin,
}


class ModelStore:
    """Deterministic model storage layout.

    data/predictive/models/{model_id}/
        model.pkl
        metadata.json
    """

    def __init__(self, base_path: Path | str = DEFAULT_STORE) -> None:
        self.base_path = Path(base_path)

    def _model_dir(self, model_id: str) -> Path:
        return self.base_path / model_id

    def save(self, artifact: ModelArtifact) -> str:
        mdir = self._model_dir(artifact.model_id)
        mdir.mkdir(parents=True, exist_ok=True)

        model_path = mdir / "model.pkl"
        artifact.model.save(str(model_path))

        meta_path = mdir / "metadata.json"
        meta_path.write_text(
            json.dumps(artifact.metadata.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return artifact.model_id

    def load_metadata(self, model_id: str) -> ModelMetadata:
        meta_path = self._model_dir(model_id) / "metadata.json"
        if not meta_path.exists():
            raise KeyError(f"model not found: {model_id}")
        return ModelMetadata.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))

    def load_model(self, model_id: str) -> ModelArtifact:
        meta = self.load_metadata(model_id)
        plugin_cls = PLUGIN_LOADERS.get(meta.plugin)
        if plugin_cls is None:
            raise ValueError(f"Unknown plugin: {meta.plugin}")

        model_path = self._model_dir(model_id) / "model.pkl"
        model = plugin_cls.load(str(model_path))

        return ModelArtifact(
            model_id=model_id,
            model=model,
            metadata=meta,
            feature_columns=list(meta.feature_columns),
            label_column=meta.label_column,
            task_type=meta.task_type,
        )

    def list_models(self, *, include_archived: bool = False) -> list[ModelMetadata]:
        if not self.base_path.exists():
            return []
        out: list[ModelMetadata] = []
        for mdir in sorted(self.base_path.iterdir()):
            if not mdir.is_dir():
                continue
            meta_path = mdir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                meta = ModelMetadata.from_dict(
                    json.loads(meta_path.read_text(encoding="utf-8")))
                if not include_archived and meta.status == ModelStatus.ARCHIVED.value:
                    continue
                out.append(meta)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return out

    def archive(self, model_id: str) -> None:
        meta = self.load_metadata(model_id)
        meta.status = ModelStatus.ARCHIVED.value
        meta_path = self._model_dir(model_id) / "metadata.json"
        meta_path.write_text(json.dumps(meta.to_dict(), indent=2), encoding="utf-8")

    def delete(self, model_id: str) -> None:
        mdir = self._model_dir(model_id)
        if mdir.exists():
            shutil.rmtree(mdir)

    def exists(self, model_id: str) -> bool:
        return (self._model_dir(model_id) / "metadata.json").exists()
