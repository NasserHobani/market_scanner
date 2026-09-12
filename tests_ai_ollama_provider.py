# -*- coding: utf-8 -*-
"""Unit tests for Ollama provider — run: python tests_ai_ollama_provider.py"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.decision_package import DecisionPackageBuilder
from scanner.ai_advisor.prompt_builder import PromptBuilder
from scanner.ai_advisor.provider_config import AIAdvisorConfig
from scanner.ai_local.config import LocalAIConfig
from scanner.ai_local.ollama_provider import OllamaError, OllamaProvider

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


VALID_JSON = json.dumps({
    "agreement": "agree",
    "confidence": 76,
    "summary": "Local review OK.",
    "reasoning": "Trend aligned.",
    "supporting_evidence": [],
    "contradicting_evidence": [],
    "risks": [],
    "missing_information": [],
    "suggested_experiment": None,
    "shadow_mode_acknowledged": True,
})

KNOWLEDGE = {
    "event_id": "evt_ollama_001",
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "recommendation_snapshot": {"action": "now", "side": "buy"},
    "market_snapshot": {"trend_direction": "bullish"},
}
REASONING = {
    "verdict": "aligned",
    "evidence": {"items": []},
    "contradictions": {"items": []},
    "warnings": [],
    "missing_information": [],
}


def _provider(*, enabled=True, ollama=True, response=None, post_side_effect=None):
    local = LocalAIConfig(
        local_enabled=enabled,
        ollama_enabled=ollama,
        local_default_model="qwen3:8b",
        ollama_base_url="http://127.0.0.1:11434",
    )
    cfg = AIAdvisorConfig(strict_json=True, retry_count=0)
    p = OllamaProvider(_config=cfg, _local=local)
    if post_side_effect:
        p._http_post = MagicMock(side_effect=post_side_effect)
    elif response is not None:
        p._http_post = MagicMock(return_value=response)
    return p


pkg = DecisionPackageBuilder().build(
    event_id="evt_ollama_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
)
prompt = PromptBuilder().build(pkg)

# Disabled
disabled = _provider(enabled=False)
try:
    disabled.analyze(prompt, package=pkg)
    check("disabled raises", False)
except OllamaError:
    check("disabled raises", True)

# Unreachable
unreach = _provider(post_side_effect=OllamaError("unreachable", retryable=False))
try:
    unreach.analyze(prompt, package=pkg)
    check("unreachable raises", False)
except OllamaError as exc:
    check("unreachable raises", True, str(exc))

# Valid response
ok_resp = {
    "message": {"role": "assistant", "content": VALID_JSON},
    "prompt_eval_count": 100,
    "eval_count": 50,
    "_latency_ms": 800,
}
provider = _provider(response=ok_resp)
parsed = provider.analyze(prompt, package=pkg)
check("valid agreement", parsed.get("agreement") == "agree")
check("valid confidence", parsed.get("confidence") == 76)
check("usage tokens", provider.last_usage.get("total_tokens") == 150)
check("provider id", provider.provider_id == "ollama")
check("model name", provider.model_name() == "qwen3:8b")

# Invalid JSON
bad = _provider(response={"message": {"content": "not json"}})
try:
    bad.analyze(prompt, package=pkg)
    check("invalid json raises", False)
except OllamaError:
    check("invalid json raises", True)

# Health mock
health_p = _provider()
health_p._http_get = MagicMock(return_value={
    "models": [{"name": "qwen3:8b"}],
})
h = health_p.health()
check("health has provider_id", h.get("provider_id") == "ollama")

passed = sum(1 for ok, _, _ in results if ok)
failed = len(results) - passed
for ok, name, extra in results:
    print(("PASS" if ok else "FAIL"), name, extra)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if failed == 0 else 1)
