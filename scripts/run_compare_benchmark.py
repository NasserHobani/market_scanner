#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AIA-06.1 — Real Claude vs Qwen compare benchmark."""
from __future__ import annotations

import json
import os
import sys
import time
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

from scanner.ai_advisor import AIAdvisorService
from scanner.ai_advisor.runtime import build_layer_outputs
from scanner.ai_local.comparisons import ComparisonStore
from scanner.ai_local.config import load_local_config
from scanner.ai_local.history import LocalAIHistory
from scanner.ai_local.metrics import compute_metrics
from scanner.ai_local.routing import execute_review, package_fingerprint

CASES = [
    ("BTCUSDT", "crypto", "4h", {"action": "now", "side": "buy", "confidence": 0.72, "grade": "B"}),
    ("ETHUSDT", "crypto", "4h", {"action": "now", "side": "buy", "confidence": 0.68, "grade": "B"}),
    ("SOLUSDT", "crypto", "1h", {"action": "wait", "side": "buy", "confidence": 0.55, "grade": "C"}),
    ("BNBUSDT", "crypto", "4h", {"action": "now", "side": "sell", "confidence": 0.61, "grade": "C"}),
    ("XRPUSDT", "crypto", "1h", {"action": "now", "side": "buy", "confidence": 0.70, "grade": "B"}),
    ("ADAUSDT", "crypto", "4h", {"action": "wait", "side": "sell", "confidence": 0.48, "grade": "D"}),
    ("DOGEUSDT", "crypto", "1h", {"action": "now", "side": "buy", "confidence": 0.65, "grade": "B"}),
    ("AVAXUSDT", "crypto", "4h", {"action": "now", "side": "buy", "confidence": 0.74, "grade": "A"}),
    ("LINKUSDT", "crypto", "4h", {"action": "now", "side": "buy", "confidence": 0.69, "grade": "B"}),
    ("DOTUSDT", "crypto", "4h", {"action": "wait", "side": "sell", "confidence": 0.52, "grade": "C"}),
]


def _strength_label(n: int) -> str:
    if n < 10:
        return "INSUFFICIENT"
    if n < 30:
        return "EMERGING"
    if n < 100:
        return "RECURRING"
    return "STRONG"


def main() -> int:
    cfg = load_local_config()
    if not cfg.local_enabled or not cfg.ollama_enabled:
        print("FAIL: Local AI not enabled")
        return 1

    svc = AIAdvisorService()
    results = []
    fingerprints_ok = 0

    print("=== AIA-06.1 Compare Benchmark ===\n")
    for i, (symbol, market, tf, reco) in enumerate(CASES, 1):
        print(f"[{i}/{len(CASES)}] {symbol} {tf} …", flush=True)
        layers = build_layer_outputs(
            symbol=symbol, market=market, timeframe=tf,
            recommendation=reco, row={"decision": reco["side"], "htf": 1},
        )
        pkg = svc.build_package(layers["event_id"], **{k: v for k, v in layers.items() if k != "event_id"})
        fp = package_fingerprint(pkg)

        t0 = time.monotonic()
        out = execute_review(svc, layers, local_cfg=cfg)
        elapsed = round((time.monotonic() - t0) * 1000)

        cmp_data = out.comparison or {}
        identical = True  # same package object used in routing
        if cmp_data.get("package_fingerprint") == fp:
            fingerprints_ok += 1

        rec = {
            "symbol": symbol,
            "timeframe": tf,
            "package_fingerprint": fp,
            "platform_decision": reco.get("side", "").upper(),
            "claude": {
                "review_id": cmp_data.get("claude_review_id", ""),
                "agreement": cmp_data.get("claude_agreement", ""),
                "confidence": cmp_data.get("claude_confidence"),
                "latency_ms": cmp_data.get("claude_latency_ms"),
                "tokens": cmp_data.get("claude_tokens"),
                "estimated_cost": cmp_data.get("claude_estimated_cost"),
                "accepted": out.claude_review.accepted if out.claude_review else None,
            },
            "ollama": {
                "review_id": cmp_data.get("local_review_id", ""),
                "agreement": cmp_data.get("local_agreement", ""),
                "confidence": cmp_data.get("local_confidence"),
                "latency_ms": cmp_data.get("local_latency_ms"),
                "tokens": cmp_data.get("local_tokens"),
                "estimated_cost": 0.0,
                "accepted": out.local_review.accepted if out.local_review else None,
            },
            "fingerprint_match": cmp_data.get("package_fingerprint") == fp,
            "total_elapsed_ms": elapsed,
            "errors": cmp_data.get("errors", []),
        }
        results.append(rec)
        print(f"  fp={fp} claude={rec['claude']['agreement']} qwen={rec['ollama']['agreement']} "
              f"({elapsed}ms total)")

    # Aggregate
    n = len(results)
    agree_match = sum(1 for r in results
                      if r["claude"]["agreement"] and r["claude"]["agreement"] == r["ollama"]["agreement"])
    claude_ok = [r for r in results if r["claude"]["accepted"]]
    ollama_ok = [r for r in results if r["ollama"]["accepted"]]

    def avg(rows, provider, field):
        vals = [r[provider].get(field) for r in rows if r[provider].get(field) is not None]
        return round(sum(vals) / len(vals), 1) if vals else 0.0

    summary = {
        "comparisons": n,
        "evidence_strength": _strength_label(n),
        "fingerprint_matches": fingerprints_ok,
        "fingerprint_identical": fingerprints_ok == n,
        "agreement_match_rate": round(agree_match / n * 100, 1) if n else 0,
        "claude_validation_rate": round(len(claude_ok) / n * 100, 1) if n else 0,
        "ollama_validation_rate": round(len(ollama_ok) / n * 100, 1) if n else 0,
        "claude_avg_confidence": avg(results, "claude", "confidence"),
        "ollama_avg_confidence": avg(results, "ollama", "confidence"),
        "confidence_difference": round(avg(results, "claude", "confidence") - avg(results, "ollama", "confidence"), 1),
        "claude_avg_latency_ms": avg(results, "claude", "latency_ms"),
        "ollama_avg_latency_ms": avg(results, "ollama", "latency_ms"),
        "claude_avg_tokens": avg(results, "claude", "tokens"),
        "ollama_avg_tokens": avg(results, "ollama", "tokens"),
        "claude_total_api_cost": round(sum(r["claude"].get("estimated_cost") or 0 for r in results), 4),
        "ollama_api_cost": 0.0,
        "note": "Observational only — no winner declared. API cost for Qwen is $0; infrastructure cost is not zero.",
    }

    out_path = ROOT / "data" / "aia061_benchmark.json"
    out_path.write_text(json.dumps({"summary": summary, "results": results}, indent=2), encoding="utf-8")

    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved: {out_path}")
    print(f"Local history records: {LocalAIHistory().count()}")
    print(f"Comparison records: {len(ComparisonStore().list_recent(100))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
