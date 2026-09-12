# -*- coding: utf-8 -*-
"""Unit tests for Claude provider — run: python tests_ai_claude_provider.py"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.provider_config import AIAdvisorConfig, config_to_public_dict
from scanner.ai_advisor.models_catalog import claude_model_choices, list_claude_models
from scanner.ai_advisor.providers.claude_provider import ClaudeProvider, ProviderError
from scanner.ai_advisor.provider_factory import create_claude_provider
from scanner.ai_advisor.prompt_builder import PromptBuilder
from scanner.ai_advisor.decision_package import DecisionPackageBuilder

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


KNOWLEDGE = {
    "event_id": "evt_claude_001",
    "symbol": "BTCUSDT",
    "market": "crypto",
    "timeframe": "4h",
    "market_snapshot": {"symbol": "BTCUSDT", "trend_direction": "bullish"},
    "recommendation_snapshot": {"action": "now", "side": "buy", "confidence": 0.75},
    "strategy_statistics": {"closed_trades": 50, "win_rate": 65.0},
}

REASONING = {
    "verdict": "aligned",
    "evidence": {"items": [
        {"evidence_id": "ev_trend", "label": "Bullish", "category": "trend",
         "direction": "supports", "confidence": 0.8, "source": "market", "facts": [], "trace": ""},
    ]},
    "contradictions": {"items": []},
    "warnings": [],
    "missing_information": [],
}

VALID_JSON = json.dumps({
    "agreement": "agree",
    "confidence": 80,
    "summary": "Evidence supports decision.",
    "reasoning": "Trend aligns per ev_trend.",
    "supporting_evidence": [
        {"evidence_id": "ev_trend", "section": "reasoning", "field": "trend", "note": "bullish"},
    ],
    "contradicting_evidence": [],
    "risks": ["volatility"],
    "missing_information": [],
    "suggested_experiment": None,
    "shadow_mode_acknowledged": True,
})

INVALID_JSON = "Here is my analysis: not json"


def _make_provider(*, enabled=True, retry_count=1, response_text=VALID_JSON,
                   side_effect=None) -> ClaudeProvider:
    config = AIAdvisorConfig(
        claude_enabled=enabled,
        claude_model="claude-sonnet-test",
        retry_count=retry_count,
        timeout=30.0,
    )

    mock_client = MagicMock()
    if side_effect:
        mock_client.messages.create.side_effect = side_effect
    else:
        block = MagicMock()
        block.text = response_text
        mock_response = MagicMock()
        mock_response.content = [block]
        mock_client.messages.create.return_value = mock_response

    return ClaudeProvider(
        _config=config,
        _client_factory=lambda: mock_client,
    )


pkg = DecisionPackageBuilder().build(
    event_id="evt_claude_001",
    knowledge_context=KNOWLEDGE,
    reasoning_review=REASONING,
)
prompt = PromptBuilder().build(pkg)


# ── Provider interface ───────────────────────────────────────────────────────

provider = _make_provider()
check("provider_name", provider.provider_name() == "claude")
check("provider_id", provider.provider_id == "claude")
check("model_name", provider.model_name() == "claude-sonnet-test")
features = provider.supported_features()
check("supported json_mode", features.get("json_mode") is True)
check("supported shadow_mode", features.get("shadow_mode") is True)


# ── Configuration ────────────────────────────────────────────────────────────

check("models from catalog", len(claude_model_choices()) >= 2)
check("models not empty", len(list_claude_models()) >= 2)
public = config_to_public_dict(AIAdvisorConfig(claude_model="claude-sonnet-test"))
check("config no api key in public", "ANTHROPIC" not in json.dumps(public))
check("config has api_key_configured flag", "api_key_configured" in public)


# ── Analyze success ──────────────────────────────────────────────────────────

old_key = os.environ.get("ANTHROPIC_API_KEY")
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"

try:
    result = provider.analyze(prompt, package=pkg)
    check("analyze returns dict", isinstance(result, dict))
    check("analyze agreement", result.get("agreement") == "agree")
    check("analyze confidence", result.get("confidence") == 80)

    health = provider.health()
    check("health after success", health.get("total_requests", 0) >= 1)
    check("health has latency", health.get("average_response_time_ms") is not None)
    check("health error rate", "error_rate" in health)

    # ── JSON retry ───────────────────────────────────────────────────────────

    call_count = {"n": 0}

    def _json_then_valid(*args, **kwargs):
        call_count["n"] += 1
        block = MagicMock()
        block.text = VALID_JSON if call_count["n"] > 1 else INVALID_JSON
        resp = MagicMock()
        resp.content = [block]
        return resp

    retry_provider = _make_provider(retry_count=1)
    retry_provider._client_factory = lambda: MagicMock(
        messages=MagicMock(create=_json_then_valid),
    )
    retry_result = retry_provider.analyze(prompt, package=pkg)
    check("json retry succeeds", retry_result.get("agreement") == "agree")
    check("json retry attempted", call_count["n"] >= 2)

    # ── Retry on timeout ─────────────────────────────────────────────────────

    timeout_calls = {"n": 0}

    def _timeout_then_ok(*args, **kwargs):
        timeout_calls["n"] += 1
        if timeout_calls["n"] == 1:
            raise TimeoutError("request timeout")
        block = MagicMock()
        block.text = VALID_JSON
        resp = MagicMock()
        resp.content = [block]
        return resp

    timeout_provider = _make_provider(retry_count=2)
    timeout_provider._client_factory = lambda: MagicMock(
        messages=MagicMock(create=_timeout_then_ok),
    )
    timeout_result = timeout_provider.analyze(prompt, package=pkg)
    check("timeout retry succeeds", timeout_result.get("agreement") == "agree")

    # ── Disabled provider ──────────────────────────────────────────────────

    disabled = _make_provider(enabled=False)
    try:
        disabled.analyze(prompt, package=pkg)
        check("disabled raises", False)
    except ProviderError:
        check("disabled raises", True)

    # ── Test connection ────────────────────────────────────────────────────

    conn = provider.test_connection()
    check("test connection connected", conn.get("connected") is True)
    check("test connection latency", conn.get("latency_ms") is not None)
    check("test connection model", conn.get("model") == "claude-sonnet-test")
    check("test connection version", conn.get("provider_version") == "1.0.0")

    # ── No API key ───────────────────────────────────────────────────────────

    del os.environ["ANTHROPIC_API_KEY"]
    no_key = _make_provider()
    no_key_health = no_key.health()
    check("no key unhealthy", no_key_health.get("healthy") is False)
    check("no key mode", no_key_health.get("mode") == "no_api_key")

    no_key_test = no_key.test_connection()
    check("no key test fails", no_key_test.get("connected") is False)

    # ── Factory ────────────────────────────────────────────────────────────

    factory_provider = create_claude_provider(AIAdvisorConfig(claude_enabled=True))
    check("factory creates provider", isinstance(factory_provider, ClaudeProvider))

finally:
    if old_key:
        os.environ["ANTHROPIC_API_KEY"] = old_key
    elif "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]


# ── Settings schema ──────────────────────────────────────────────────────────

from scanner import settings_schema

check("ai settings group exists", any(g.key == "ai_advisor" for g in settings_schema.GROUPS))
ai_fields = [f.key for g in settings_schema.GROUPS if g.key == "ai_advisor" for f in g.fields]
check("ai_claude_enabled field", "ai_claude_enabled" in ai_fields)
check("ai_default_provider field", "ai_default_provider" in ai_fields)
check("ai_claude_model field", "ai_claude_model" in ai_fields)
check("ai_prompt_version field", "ai_prompt_version" in ai_fields)
check("ai_shadow_mode field", "ai_shadow_mode" in ai_fields)


# ── Registry ─────────────────────────────────────────────────────────────────

from scanner.ai_advisor.provider_registry import ProviderRegistry

reg = ProviderRegistry()
reg.register_defaults()
check("registry has claude", "claude" in [p["provider_id"] for p in reg.list_all()])
claude_health = reg.get("claude").health()
check("registry claude health dict", isinstance(claude_health, dict))


# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\n{'='*60}")
print(f"Claude Provider Tests: {passed}/{len(results)} passed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if extra:
        line += f" — {extra}"
    print(line)
if failed:
    print(f"\n{len(failed)} FAILED")
    sys.exit(1)
print("\nAll tests passed.")
