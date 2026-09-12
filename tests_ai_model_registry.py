# -*- coding: utf-8 -*-
"""Unit tests for local model registry — run: python tests_ai_model_registry.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_local.model_registry import (
    get_model,
    list_models,
    model_choices,
    resolve_model,
)
from scanner.ai_advisor.models_catalog import ollama_model_choices, resolve_ollama_model

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


models = list_models()
check("registry not empty", len(models) >= 2)
check("qwen3:4b registered", get_model("qwen3:4b") is not None)
check("qwen3:8b registered", get_model("qwen3:8b") is not None)
check("qwen3:8b context", get_model("qwen3:8b").context_window == 32768)
check("resolve known", resolve_model("qwen3:4b") == "qwen3:4b")
# السجلّ دليلٌ لا حارس: الاسم غير المسجَّل يُحترم كما كُتب، ووجوده
# فعلاً يفحصه Ollama نفسه. الاستبدال الصامت هو الذي كان يُفشل فحص
# الاتصال بينما Ollama يعمل. الفراغ وحده هو الذي يستدعي افتراضاً.
check("resolve unknown is respected", resolve_model("llama3.1:8b") == "llama3.1:8b")
check("resolve empty falls back", resolve_model("") in ("qwen3:8b", "qwen3:4b"))
check("resolve strips whitespace", resolve_model("  qwen3:4b  ") == "qwen3:4b")
check("model choices", len(model_choices()) >= 2)
check("catalog ollama choices", len(ollama_model_choices()) >= 2)
check("catalog resolve", resolve_ollama_model("qwen3:8b") == "qwen3:8b")

m4 = get_model("qwen3:4b")
check("model to_dict", "model_id" in m4.to_dict() and m4.local is True)

passed = sum(1 for ok, _, _ in results if ok)
failed = len(results) - passed
for ok, name, extra in results:
    print(("PASS" if ok else "FAIL"), name, extra)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if failed == 0 else 1)
