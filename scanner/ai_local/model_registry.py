# -*- coding: utf-8 -*-
"""Extensible local model registry — Qwen3 initial models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LocalModel:
    provider: str
    model_id: str
    display_name: str
    context_window: int
    local: bool = True
    enabled: bool = True
    capabilities: tuple[str, ...] = ("review", "json")

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "context_window": self.context_window,
            "local": self.local,
            "enabled": self.enabled,
            "capabilities": list(self.capabilities),
        }


_REGISTRY: tuple[LocalModel, ...] = (
    LocalModel("ollama", "qwen3:4b", "Qwen3 4B", context_window=32768),
    LocalModel("ollama", "qwen3:8b", "Qwen3 8B", context_window=32768),
)


def list_models(*, enabled_only: bool = True) -> list[LocalModel]:
    if enabled_only:
        return [m for m in _REGISTRY if m.enabled]
    return list(_REGISTRY)


def get_model(model_id: str) -> LocalModel | None:
    mid = (model_id or "").strip()
    for m in _REGISTRY:
        if m.model_id == mid:
            return m
    return None


def model_choices() -> tuple[tuple[str, str], ...]:
    return tuple((m.model_id, m.display_name) for m in list_models())


def resolve_model(model_id: str) -> str:
    """اسم النموذج كما يُرسَل إلى Ollama.

    كان أي اسم خارج السجلّ يُستبدل **بصمت** بـ ``qwen3:8b``. والسجلّ
    فيه نموذجان فقط، فمن ثبّت ``qwen2.5`` أو ``llama3.1`` أو حتى
    ``qwen3:latest`` كان النظام يسأل Ollama عن نموذج لا يملكه، فيفشل
    فحص الاتصال بينما Ollama يعمل تماماً — وهو بالضبط ما وقع.

    السجلّ الآن **دليل لا حارس**: الاسم المكتوب يُحترم كما هو، ووظيفة
    السجلّ أن يقترح في القائمة لا أن يفرض. وأمّا وجود النموذج فعلاً
    فيُفحص عند Ollama نفسه — وهو المرجع الوحيد الذي يعرف.
    """
    mid = (model_id or "").strip()
    if not mid:
        return _REGISTRY[1].model_id if len(_REGISTRY) > 1 else "qwen3:8b"
    return mid


def is_known(model_id: str) -> bool:
    """هل النموذج في السجلّ المقترح؟ للعرض لا للمنع."""
    return get_model((model_id or "").strip()) is not None
