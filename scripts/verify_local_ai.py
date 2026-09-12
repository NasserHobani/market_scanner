#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Real runtime verification for AIA-06 local AI.

Usage: python scripts/verify_local_ai.py

States: CONFIGURED | CONNECTED | RUNNING | SUCCESSFUL REVIEW | VERIFIED
Does NOT modify trading decisions.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WEB))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()


def main() -> int:
    from scanner.ai_local.config import load_local_config
    from scanner.ai_local.health import check_ollama_health, test_ollama_connection
    from scanner.ai_local.history import LocalAIHistory
    from scanner.ai_local.routing import execute_review
    from scanner.ai_advisor import AIAdvisorService
    from scanner.ai_advisor.runtime import build_layer_outputs

    cfg = load_local_config()
    print("=== AIA-06 Local AI Verification ===\n")

    if not cfg.local_enabled:
        print("STATUS: NOT READY")
        print("Reason: ai_local_enabled is False — enable in settings.")
        return 1

    print("STATUS: CONFIGURED")
    print(f"  Execution mode: {cfg.execution_mode}")
    print(f"  Ollama URL: {cfg.ollama_base_url}")
    print(f"  Model: {cfg.local_default_model}")

    if not cfg.ollama_enabled:
        print("\nSTATUS: CONFIGURED (Ollama disabled)")
        return 1

    health = check_ollama_health(cfg)
    print(f"\nOllama reachable: {health.get('ollama_reachable')}")
    print(f"Model available: {health.get('model_available')}")
    if health.get("models"):
        print("Available models:", ", ".join(m["model"] for m in health["models"][:10]))

    if not health.get("ollama_reachable"):
        print("\nSTATUS: CONFIGURED (Ollama not reachable)")
        print(f"Error: {health.get('error', '')}")
        return 1

    print("\nSTATUS: CONNECTED")

    test = test_ollama_connection(cfg)
    if not test.get("connected"):
        print(f"Test failed: {test.get('error', '')}")
        return 1

    print("\nSTATUS: RUNNING — sending test review…")

    reco = {
        "action": "now",
        "side": "buy",
        "confidence": 0.72,
        "grade": "B",
        "entry": 100.0,
        "stop": 95.0,
        "target": 110.0,
    }
    layers = build_layer_outputs(
        symbol="BTCUSDT",
        market="crypto",
        timeframe="4h",
        recommendation=reco,
        row={"decision": "شراء", "htf": 1},
    )

    prev_mode = cfg.execution_mode
    local_cfg = type(cfg)(
        local_enabled=True,
        ollama_enabled=True,
        ollama_base_url=cfg.ollama_base_url,
        local_default_model=cfg.local_default_model,
        execution_mode="local_only",
        escalate_on_validation_failure=cfg.escalate_on_validation_failure,
        escalate_on_provider_error=cfg.escalate_on_provider_error,
        escalate_on_malformed_response=cfg.escalate_on_malformed_response,
        escalate_min_confidence=cfg.escalate_min_confidence,
        escalate_on_grounding_failure=cfg.escalate_on_grounding_failure,
        escalate_grounding_below=cfg.escalate_grounding_below,
    )

    svc = AIAdvisorService()
    try:
        result = execute_review(svc, layers, local_cfg=local_cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"\nReview failed: {exc}")
        return 1

    metrics = result.metrics or {}
    print("\n--- Review Result ---")
    print(f"Provider: {result.provider_id}")
    print(f"Model: {result.model_name}")
    print(f"Review ID: {result.review_id}")
    print(f"Accepted: {result.accepted}")
    print(f"Agreement: {result.agreement}")
    print(f"Confidence: {result.confidence}")
    print(f"Latency: {metrics.get('latency_ms')} ms")
    print(f"Tokens: {metrics.get('total_tokens')}")
    print(f"Validation: {'passed' if result.accepted else 'failed'}")
    print(f"Grounding: {metrics.get('grounding_score', '—')}")

    if not result.accepted:
        print(f"\nSTATUS: RUNNING (review not accepted)")
        print(f"Error: {result.error}")
        return 1

    last = LocalAIHistory().list_recent(1)
    persisted = last and last[0].get("review_id") == result.review_id
    print(f"Persisted: {persisted}")

    if persisted:
        print("\nSTATUS: VERIFIED")
        print(json.dumps({
            "review_id": result.review_id,
            "provider": result.provider_id,
            "model": result.model_name,
            "latency_ms": metrics.get("latency_ms"),
            "total_tokens": metrics.get("total_tokens"),
            "validation_passed": result.accepted,
        }, indent=2))
        return 0

    print("\nSTATUS: SUCCESSFUL REVIEW (not yet persisted)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
