# -*- coding: utf-8 -*-
"""AIA-13 real Arabic analyst verification via configured Qwen/Ollama.

Uses the live provider — not mocks. Temporarily enables local AI for this
script only (does not persist settings). If Ollama/Qwen is unavailable,
exits non-zero with a clear FAILED status.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    print("=" * 40)
    print("AIA-13 ARABIC AI ANALYST")
    print("=" * 40)

    from scanner.ai_local.config import LocalAIConfig, load_local_config
    from scanner.ai_advisor.prompt_builder import PromptBuilder
    from scanner.ai_advisor.analyst.normalize import extract_analyst_fields, normalize_analyst_response
    from scanner.ai_advisor.response_validator import ResponseValidator
    from scanner.ai_advisor.unified_package import UnifiedDecisionPackage, EvidenceTrace
    from scanner.ai_advisor.explainability.localized_presentation import build_presentation
    from scanner.ai_advisor.provider_config import load_config
    from scanner.ai_local.ollama_provider import OllamaProvider

    saved = load_local_config()
    model = saved.local_default_model or "qwen3:8b"
    # Force-enable for verification only — does not write appsettings
    local = LocalAIConfig(
        local_enabled=True,
        ollama_enabled=True,
        ollama_base_url=saved.ollama_base_url,
        local_default_model=model,
        execution_mode="local_only",
    )
    provider_name = "Qwen"
    print(f"Provider:\n{provider_name}")
    print(f"Model:\n{model}")
    print("Language:\nArabic")

    symbol = "BTCUSDT"
    timeframe = "1h"
    print(f"Symbol:\n{symbol}")
    print(f"Timeframe:\n{timeframe}")

    evidence = (
        EvidenceTrace(
            evidence_id="ev_trend", source_layer="knowledge", section="knowledge",
            field="trend", label="trend", value="bullish",
            timestamp="2025-08-01T12:00:00+00:00", confidence=0.8,
        ),
        EvidenceTrace(
            evidence_id="ev_rvol", source_layer="features", section="feature_snapshot",
            field="rvol", label="rvol", value=1.4,
            timestamp="2025-08-01T12:00:00+00:00",
        ),
        EvidenceTrace(
            evidence_id="ev_pred", source_layer="prediction", section="prediction",
            field="available", label="prediction_available", value=False,
            timestamp="2025-08-01T12:00:00+00:00",
        ),
    )
    package = UnifiedDecisionPackage(
        package_id="pkg_aia13_verify",
        event_id="evt_aia13_verify",
        shadow_mode=True,
        recommendation={
            "side": "buy", "action": "pending", "confidence": 72,
            "grade": "B", "rr": 2.0,
        },
        prediction={"available": False, "reason": "no_active_model"},
        knowledge={"available": True, "trend": "bullish"},
        similarity={"available": False},
        research={"available": False},
        feature_snapshot={"available": True, "coverage": 0.85},
        evidence_index=evidence,
        metadata={"symbol": symbol, "market": "crypto", "timeframe": timeframe,
                  "context_profile": "standard"},
    )

    prompt = PromptBuilder().build(
        package, version="advisor_prompt_v4", context_profile="standard",
    )

    provider = OllamaProvider(_config=load_config(), _local=local)

    t0 = time.monotonic()
    try:
        raw = provider.analyze(prompt, package=package)
    except Exception as exc:
        print("Current View:\n—")
        print("Recommendation:\n—")
        print("3–7 Day Outlook:\n—")
        print("Advisor Confidence:\n—")
        print("Prediction:\nUNAVAILABLE")
        print("Fusion:\nPREDICTION_UNAVAILABLE")
        print(f"Grounding:\nFAILED provider call: {exc}")
        print("Hallucination:\n—")
        print("Tokens:\n—")
        print(f"Latency:\n{round((time.monotonic() - t0) * 1000)} ms")
        print("Review ID:\n—")
        print("=" * 40)
        print("\nReal Qwen verification FAILED — ensure Ollama is running with the model.")
        print(f"(Saved settings local_enabled={saved.local_enabled}; "
              f"this script forced enable for the call only.)")
        return 1
    latency_ms = round((time.monotonic() - t0) * 1000, 1)

    from scanner.ai_advisor.response_parser import ResponseParser
    try:
        parsed = ResponseParser().parse(raw)
    except Exception as exc:
        print(f"Grounding:\nparse failed: {exc}")
        print(f"Latency:\n{latency_ms} ms")
        print("=" * 40)
        return 1

    parsed = normalize_analyst_response(parsed)

    # البوّابة كما تُطبَّق في المحرّك تماماً — لا نسخة ألطف للعرض.
    # هذا السطر هو ما يجعل التحقّق ذا معنى: يُظهر ما إذا كان النموذج
    # الحقيقي حاول اختراع احتمال في هذه الجولة بالذات.
    from scanner.ai_advisor.analyst.gate import gate_prediction
    parsed, gate_violations = gate_prediction(
        parsed, getattr(package, "prediction", None)
    )

    validation = ResponseValidator().validate(parsed, package)
    analyst = extract_analyst_fields(parsed)
    pres = build_presentation({**parsed, "symbol": symbol, "timeframe": timeframe,
                               "recommendation": package.recommendation}, "ar")

    usage = getattr(provider, "last_usage", {}) or {}
    tokens = usage.get("total_tokens") or (
        int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)
    )

    print(f"Current View:\n{pres.get('current_market_view')}")
    print(f"Recommendation:\n{pres.get('advisor_decision')}")
    print(f"3–7 Day Outlook:\n{pres.get('near_term_outlook')}")
    print(f"Advisor Confidence:\n{pres.get('advisor_confidence_display')}")
    print("Prediction:\nUNAVAILABLE" if not analyst.get("statistical_prediction", {}).get("available")
          else "AVAILABLE")
    print("Fusion:\nPREDICTION_UNAVAILABLE")
    if gate_violations:
        print(f"Prediction Gate:\nBLOCKED {len(gate_violations)}")
        for v in gate_violations:
            print(f"  - {v}")
    else:
        print("Prediction Gate:\nCLEAN")
    print(f"Grounding:\n{'PASS' if validation.valid and not validation.rejected else 'FAIL'}")
    print(f"Hallucination:\n{len(validation.hallucinations) + len(gate_violations)}")
    print(f"Tokens:\n{tokens or '—'}")
    print(f"Latency:\n{latency_ms} ms")
    print(f"Review ID:\nverify_aia13_{int(time.time())}")
    print("=" * 40)

    summary = str(parsed.get("summary") or "")
    arabic_chars = sum(1 for ch in summary if "\u0600" <= ch <= "\u06FF")
    print(f"\nArabic chars in summary: {arabic_chars}")
    print(f"Provider model reported: {provider.model_name()}")
    print(f"Prompt version: {prompt.version}")
    if arabic_chars < 5:
        print("WARNING: summary has little Arabic — check model instruction following.")
    if validation.rejected:
        print("WARNING: validation rejected —", validation.to_dict())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
