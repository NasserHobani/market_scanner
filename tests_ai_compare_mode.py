# -*- coding: utf-8 -*-
"""Compare mode tests — run: python tests_ai_compare_mode.py"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.review import AdvisorReview
from scanner.ai_local.comparisons import ComparisonStore
from scanner.ai_local.config import LocalAIConfig
from scanner.ai_local.routing import execute_review, package_fingerprint
from scanner.ai_advisor.unified_package import UnifiedDecisionPackage

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _review(rid: str, provider: str, *, agreement="agree", confidence=80.0, accepted=True):
    return AdvisorReview(
        review_id=rid,
        package_id="pkg_test",
        event_id="evt_cmp",
        provider_id=provider,
        model_name="test-model",
        prompt_version="advisor_prompt_v1",
        agreement=agreement,
        confidence=confidence,
        accepted=accepted,
        summary="test",
        reasoning="test",
    )


pkg = UnifiedDecisionPackage(
    package_id="pkg_test",
    event_id="evt_cmp",
    metadata={"symbol": "BTCUSDT", "timeframe": "4h"},
)

fp1 = package_fingerprint(pkg)
fp2 = package_fingerprint(pkg)
check("same fingerprint", fp1 == fp2)
check("fingerprint prefix", fp1.startswith("pkg_"))

with tempfile.TemporaryDirectory() as tmp:
    hist_path = Path(tmp) / "comparisons.jsonl"
    store = ComparisonStore(hist_path)

    with patch("scanner.ai_local.routing.ComparisonStore", return_value=store):
        with patch("scanner.ai_local.routing.LocalAIHistory") as mock_hist:
            mock_hist.return_value.append = MagicMock()
            svc = MagicMock()
            svc.build_package.return_value = pkg
            svc._engine.last_call_metrics = {
                "latency_ms": 1200,
                "total_tokens": 500,
                "estimated_cost": 0.06,
            }
            svc._engine.last_package_diagnostics = {}

            claude_r = _review("claude_1", "claude", confidence=82)
            local_r = _review("local_1", "ollama", confidence=76)

            def review_side_effect(package, provider_id="", prompt_version=""):
                if provider_id == "claude":
                    return claude_r
                return local_r

            svc.review.side_effect = review_side_effect

            local_cfg = LocalAIConfig(
                local_enabled=True,
                ollama_enabled=True,
                execution_mode="compare",
            )
            result = execute_review(svc, {"event_id": "evt_cmp"}, local_cfg=local_cfg)

            check("compare accepted", result.accepted is True)
            check("has comparison", result.comparison is not None)
            check("same package fp in comparison",
                  result.comparison.get("package_fingerprint") == fp1)
            check("claude agreement", result.comparison.get("claude_agreement") == "agree")
            check("local agreement", result.comparison.get("local_agreement") == "agree")
            check("claude confidence", result.comparison.get("claude_confidence") == 82)
            check("local confidence", result.comparison.get("local_confidence") == 76)
            check("comparison id set", bool(result.comparison.get("comparison_id")))

            saved = store.list_recent(1)
            check("comparison persisted", len(saved) == 1)

# Claude-only when local disabled
svc2 = MagicMock()
svc2.build_package.return_value = pkg
svc2.review.return_value = _review("c_only", "claude")
svc2._engine.last_call_metrics = {}
svc2._engine.last_package_diagnostics = {}
r2 = execute_review(svc2, {"event_id": "evt_cmp"},
                    local_cfg=LocalAIConfig(execution_mode="claude_only"))
check("claude_only provider", r2.provider_id == "claude")
check("claude_only no comparison", r2.comparison is None)

passed = sum(1 for ok, _, _ in results if ok)
failed = len(results) - passed
for ok, name, extra in results:
    print(("PASS" if ok else "FAIL"), name, extra)
print(f"\n{passed}/{len(results)} passed")
sys.exit(0 if failed == 0 else 1)
