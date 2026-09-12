# -*- coding: utf-8 -*-
"""Tests for explainability layer — run: python tests_ai_explainability.py"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scanner.ai_advisor.explainability.evidence_links import evidence_link, enrich_evidence_list
from scanner.ai_advisor.explainability.manual_formatter import format_manual_analysis
from scanner.ai_advisor.explainability.review_export import export_json, export_markdown
from scanner.ai_advisor.explainability.review_meta import (
    ReviewMetaStore,
    recommendation_fingerprint,
)
from scanner.ai_advisor.explainability.review_timeline_service import ReviewTimelineService
from scanner.ai_advisor.runtime_history import AdvisorRuntimeHistory

results: list[tuple[bool, str]] = []


def check(name: str, cond: bool) -> None:
    results.append((cond, name))


def test_fingerprint():
    fp1 = recommendation_fingerprint({"side": "buy", "confidence": 0.8})
    fp2 = recommendation_fingerprint({"side": "buy", "confidence": 0.8})
    fp3 = recommendation_fingerprint({"side": "sell", "confidence": 0.8})
    check("fingerprint stable", fp1 == fp2)
    check("fingerprint changes", fp1 != fp3)


def test_evidence_links():
    link = evidence_link("ev_similarity", section="similarity", symbol="BTCUSDT", market="crypto")
    check("evidence href", "/symbol/crypto/BTCUSDT" in link["href"])
    enriched = enrich_evidence_list([
        {"evidence_id": "ev_prediction", "section": "prediction", "note": "test"},
    ], symbol="ETHUSDT", market="crypto")
    check("enriched count", len(enriched) == 1)
    check("enriched href", "href" in enriched[0])


def test_manual_formatter():
    review = {
        "review_id": "adv_test",
        "agreement": "partial",
        "confidence": 65,
        "summary": "Test summary",
        "reasoning": "Trend is bullish. Momentum weak.",
        "supporting_evidence": [],
        "contradicting_evidence": [],
        "risks": ["risk1"],
        "missing_information": ["missing1"],
        "suggested_experiment": {"hypothesis": "h", "method": "m", "expected_outcome": "e"},
        "status": "accepted",
        "accepted": True,
    }
    out = format_manual_analysis(review, recommendation={"side": "buy"}, review_type="manual")
    check("overall decision", out["overall_decision"] in ("Buy", "Watch", "Strong Buy"))
    check("15 fields", "should_wait" in out and "invalidation" in out)
    check("full reasoning", "bullish" in out["detailed_analysis"]["full_reasoning"].lower())


def test_timeline_and_export(tmp: Path):
    hist = AdvisorRuntimeHistory(tmp / "history.jsonl")
    rid = hist.save({
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "symbol": "BTCUSDT",
        "latency_ms": 1000,
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150,
        "estimated_cost": 0.01,
        "agreement": "agree",
        "confidence": 80,
        "grounding_score": 100,
        "hallucination_score": 0,
    })
    meta = ReviewMetaStore(tmp / "meta.jsonl")
    meta.save(review_id=rid, review_type="manual", symbol="BTCUSDT", market="crypto")

    svc = ReviewTimelineService()
    svc._history = hist  # noqa: SLF001
    svc._meta = meta

    listing = svc.list_reviews(page_size=10)
    check("list total", listing["total"] >= 1)
    check("list items", len(listing["items"]) >= 1)

    detail = svc.get_review(rid)
    check("detail id", detail and detail["review_id"] == rid)
    check("detail type manual", detail and detail["review_type"] == "manual")
    check("presentations ar", detail and "ar" in (detail.get("presentations") or {}))

    if detail:
        check("export json", "review_id" in export_json(detail))
        check("export md", "# AI Advisor Review" in export_markdown(detail))


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        test_fingerprint()
        test_evidence_links()
        test_manual_formatter()
        test_timeline_and_export(Path(td))

    passed = sum(1 for ok, _ in results if ok)
    failed = [name for ok, name in results if not ok]
    print(f"\nExplainability Tests: {passed}/{len(results)} passed")
    for ok, name in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if failed:
        print("\nFailed:", ", ".join(failed))
        return 1
    print("\nAll tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
