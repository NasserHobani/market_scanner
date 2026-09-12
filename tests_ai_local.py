# -*- coding: utf-8 -*-
"""Local AI infrastructure tests — run: python tests_ai_local.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.review import AdvisorReview
from scanner.ai_local.config import EXECUTION_MODES, LocalAIConfig, load_local_config
from scanner.ai_local.health import check_ollama_health
from scanner.ai_local.history import LocalAIHistory
from scanner.ai_local.metrics import compute_metrics
from scanner.ai_local.routing import execute_review

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


check("execution modes", set(EXECUTION_MODES) == {
    "claude_only", "local_only", "local_first", "compare",
})
check("default config safe", load_local_config().execution_mode == "claude_only")
check("default local disabled", load_local_config().local_enabled is False)

# Health — disabled
h = check_ollama_health(LocalAIConfig(local_enabled=False))
check("health disabled", h.get("enabled") is False)
check("health not reachable when disabled", h.get("ollama_reachable") is False)

# Health — mock reachable
cfg = LocalAIConfig(local_enabled=True, ollama_enabled=True, local_default_model="qwen3:8b")
mock_get = MagicMock(return_value={"models": [{"name": "qwen3:8b"}]})
h2 = check_ollama_health(cfg, http_get=mock_get)
check("health reachable", h2.get("ollama_reachable") is True)
check("model available", h2.get("model_available") is True)

# History append-only
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "hist.jsonl"
    hist = LocalAIHistory(path)
    hist.append({"review_id": "r1", "provider": "ollama", "model": "qwen3:8b"})
    hist.append({"review_id": "r2", "provider": "ollama", "model": "qwen3:8b"})
    check("history count", hist.count() == 2)
    recent = hist.list_recent(1)
    check("history recent", recent[0]["review_id"] == "r2")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    check("append only", len(lines) == 2)

    hist.append({"review_id": "r3", "validation_passed": True, "confidence": 70,
                   "latency_ms": 500, "total_tokens": 100, "agreement": "agree"})
    m = compute_metrics(hist)
    check("metrics total", m["total_reviews"] == 3)
    check("metrics success", m["successful_reviews"] >= 1)

# Local-only failure isolation
from scanner.ai_local.ollama_provider import OllamaError


def _review(rid, provider, accepted=True, confidence=80):
    return AdvisorReview(
        review_id=rid, package_id="p1", event_id="e1", provider_id=provider,
        model_name="m", prompt_version="advisor_prompt_v1",
        agreement="agree", confidence=confidence,
        accepted=accepted, summary="s", reasoning="r",
    )


from scanner.ai_advisor.unified_package import UnifiedDecisionPackage
pkg = UnifiedDecisionPackage(
    package_id="p1", event_id="e1",
    metadata={"symbol": "ETHUSDT", "timeframe": "1h"},
)

svc = MagicMock()
svc.build_package.return_value = pkg
svc.review.side_effect = OllamaError("down")
svc._engine.last_call_metrics = {}
svc._engine.last_package_diagnostics = {}

with patch("scanner.ai_local.routing.LocalAIHistory"):
    r = execute_review(svc, {"event_id": "e1"},
                        local_cfg=LocalAIConfig(
                            local_enabled=True, ollama_enabled=True,
                            execution_mode="local_only"))
    check("local_only failure", r.accepted is False)
    check("local_only error", bool(r.error))

# Local-first escalation
svc3 = MagicMock()
svc3.build_package.return_value = pkg
svc3._engine.last_call_metrics = {"grounding_score": 30, "latency_ms": 400}
svc3._engine.last_package_diagnostics = {}

def lf_review(package, provider_id="", prompt_version=""):
    if provider_id == "ollama":
        return _review("loc", "ollama", confidence=30)
    return _review("cl", "claude", confidence=85)

svc3.review.side_effect = lf_review
with patch("scanner.ai_local.routing.LocalAIHistory"):
    r3 = execute_review(svc3, {"event_id": "e1"},
                        local_cfg=LocalAIConfig(
                            local_enabled=True, ollama_enabled=True,
                            execution_mode="local_first",
                            escalate_min_confidence=40))
    check("local_first escalated", r3.escalated is True)
    check("local_first claude primary", r3.provider_id == "claude")

passed = sum(1 for ok, _, _ in results if ok)
failed = len(results) - passed
for ok, name, extra in results:
    print(("PASS" if ok else "FAIL"), name, extra)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if failed == 0 else 1)
