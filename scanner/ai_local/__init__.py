# -*- coding: utf-8 -*-
"""Local AI infrastructure — Ollama + Qwen (AIA-06)."""
from __future__ import annotations

from .config import EXECUTION_MODES, LocalAIConfig, load_local_config
from .health import check_ollama_health, test_ollama_connection
from .routing import ReviewExecutionResult, execute_review

__all__ = [
    "EXECUTION_MODES",
    "LocalAIConfig",
    "ReviewExecutionResult",
    "check_ollama_health",
    "execute_review",
    "load_local_config",
    "test_ollama_connection",
]
