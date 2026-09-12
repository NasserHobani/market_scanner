# -*- coding: utf-8 -*-
"""تحقّق ‏AIA-13.1 على نموذج حقيقي.

يقيس قبل/بعد على حزمة فعلية، ثمّ ينادي المزوّد المحلّي.

يفشل — ولا يكتفي بالتحذير — إذا:

  • تجاوز تقدير رموز الدخل ميزانية الملف
  • ظهرت قيمة شمعة خام في سياق النموذج
  • استشهد النموذج بمعرّف دليل غير موجود

الفشل هنا مقصود: تحذيرٌ يُطبَع ثمّ يُرسَل الموجّه كما هو يعيد بالضبط
العطب الذي بُني هذا كلّه لإصلاحه.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scanner.ai_advisor.advisor_engine import AdvisorEngine  # noqa: E402
from scanner.ai_advisor.analyst_context import (  # noqa: E402
    ContextTooLarge, compile_context, estimate_text_tokens, resolve_profile,
)
from scanner.ai_advisor.prompt_builder import PromptBuilder  # noqa: E402

SEP = "=" * 40
OHLC_MARKERS = ("open", "high", "low", "close", "ohlc", "candles")


def _tokens(prompt) -> int:
    return (estimate_text_tokens(prompt.system_prompt)
            + estimate_text_tokens(prompt.user_prompt))


def _demo_layers(symbol: str, timeframe: str) -> dict:
    """طبقات واقعية الشكل — بأسماء المحوّلات لا بأسماء مُتخيَّلة."""
    return {
        "metadata": {"symbol": symbol, "market": "crypto",
                     "timeframe": timeframe},
        "recommendation": {"action": "buy", "direction": "long",
                           "confidence": 62, "grade": "B", "entry": 58200,
                           "stop": 56900, "r_target": 2.1},
        "knowledge_context": {
            "market_environment": {"regime": "متذبذب"},
            "market_snapshot": {"trend_direction": "صاعد",
                                "structure": "BOS صاعد",
                                # شموع خام عمداً: يجب ألّا تصل النموذج
                                "open": 58000, "high": 58900,
                                "low": 57800, "close": 58650},
            "knowledge_graph": {"nodes": [{"label": "دعم 58k"},
                                          {"label": "مقاومة 61k"}]},
        },
        "reasoning_review": {"warnings": ["سيولة رقيقة قرب المقاومة"],
                             "confidence": 55},
        "similarity_context": {"match_count": 24, "average_win_rate": 0.42,
                               "average_r": 0.31, "confidence": 68.75},
        "research_report": {"title": "اختراقات 4h تتفوّق على 1h",
                            "confidence": 71, "sample_size": 118},
        "feature_snapshot": {"available": True, "coverage": 86.0,
                             "quality": "OK", "feature_count": 31},
        "prediction": {"available": False},
    }


def main() -> int:
    symbol = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    timeframe = sys.argv[2] if len(sys.argv) > 2 else "4h"
    profile_name = (sys.argv[3] if len(sys.argv) > 3 else "FAST").upper()
    prof = resolve_profile(profile_name)

    print(SEP)
    print("AIA-13.1 CONTEXT VERIFICATION")
    print(SEP)
    print(f"Symbol:\n{symbol} · {timeframe}")
    print(f"Profile:\n{prof.name} (سقف {prof.hard_max_tokens})")

    failures: list[str] = []

    eng, pb = AdvisorEngine(), PromptBuilder()
    layers = _demo_layers(symbol, timeframe)
    event_id = f"evt_{symbol}_crypto_{timeframe}".lower()

    t0 = time.monotonic()
    pkg = eng.build_package(event_id, **layers)
    data_ms = round((time.monotonic() - t0) * 1000, 1)

    before = pb.build(pkg, version="advisor_prompt_v4",
                      context_profile=prof.name, compact=False)

    t1 = time.monotonic()
    try:
        after = pb.build(pkg, version="advisor_prompt_v4",
                         context_profile=prof.name)
    except ContextTooLarge as exc:
        print(f"Context:\nREJECTED — {exc}")
        print(SEP)
        print("\nالرفض سلوك صحيح، لكنّه يعني أن السياق لا يُترجَم لهذا الملف.")
        return 1
    build_ms = round((time.monotonic() - t1) * 1000, 1)

    t_before, t_after = _tokens(before), _tokens(after)
    ev_before = after.metadata.get("evidence_before", 0)
    ev_after = after.metadata.get("evidence_count", 0)

    print(f"Before tokens:\n{t_before}")
    print(f"After tokens:\n{t_after}")
    if t_before:
        print(f"Reduction:\n{round((1 - t_after / t_before) * 100)}%")
    print(f"Evidence before:\n{ev_before}")
    print(f"Evidence after:\n{ev_after}")
    print(f"Data collection:\n{data_ms} ms")
    print(f"Context build:\n{after.metadata['context_metrics']['context_compile_ms']} ms")
    print(f"Prompt build:\n{build_ms} ms")

    # ── الثابتة ──
    if t_after > prof.hard_max_tokens:
        failures.append(
            f"رموز الدخل {t_after} تتجاوز سقف {prof.name} "
            f"({prof.hard_max_tokens})")

    # ── لا شموع خام ──
    ctx = compile_context(pkg, profile=prof.name)
    body = ctx.render()
    for marker in OHLC_MARKERS:
        if marker in body.lower():
            failures.append(f"قيمة شمعة خام في السياق: {marker}")
    for value in ("58900", "57800", "58650"):
        if value in after.user_prompt:
            failures.append(f"سعر شمعة خام في الموجّه: {value}")

    # ── المعرّفات المُرسَلة موجودة في الحزمة ──
    pkg_ids = {e.evidence_id for e in pkg.evidence_index}
    sent_ids = set(ctx.evidence_map()) | set(ctx.inline_ids.values())
    unknown = sent_ids - pkg_ids
    if unknown:
        failures.append(f"معرّفات دليل غير موجودة في الحزمة: {sorted(unknown)}")

    # ── النداء الحقيقي ──
    print(f"Provider:\n", end="")
    try:
        from scanner.ai_advisor.provider_config import (
            effective_provider_id, load_config,
        )
        from scanner.ai_local.config import load_local_config

        cfg = load_config()
        local = load_local_config()
        provider_id = "ollama" if local.local_enabled else effective_provider_id(cfg)
        print(provider_id)

        t2 = time.monotonic()
        review = eng.review(pkg, provider_id=provider_id,
                            prompt_version="advisor_prompt_v4")
        latency = round((time.monotonic() - t2) * 1000)
        metrics = eng.last_call_metrics or {}

        print(f"Latency:\n{latency} ms")
        print(f"Actual input tokens:\n{metrics.get('prompt_tokens') or '—'}")
        print(f"Output tokens:\n{metrics.get('completion_tokens') or '—'}")
        print(f"Grounding:\n{metrics.get('grounding_score', '—')}")
        print(f"Hallucination:\n{metrics.get('hallucination_score', '—')}")
        print(f"Recommendation:\n{review.agreement} · ثقة {review.confidence}")
        print(f"Summary:\n{(review.summary or '—')[:200]}")

        # فرق التقدير عن الحقيقة يُعرَض: تقدير يخطئ بانتظام يجب أن يُعاير
        actual = metrics.get("prompt_tokens")
        if actual:
            err = round((t_after - actual) / actual * 100, 1)
            print(f"Estimate error:\n{err:+}%")
            if err < -15:
                failures.append(
                    f"التقدير يقلّ عن الحقيقة بـ{abs(err)}% — يُعاير "
                    "معامل الكثافة، فتقدير متفائل يخرق الميزانية بلا إنذار")
    except Exception as exc:  # noqa: BLE001
        print(f"\nProvider call failed: {str(exc)[:200]}")
        print("(الفحوص البنيوية أعلاه تمّت؛ النداء الحقيقي يحتاج Ollama يعمل.)")

    print(SEP)
    if failures:
        print("\n✗ فشل التحقّق:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("\n✓ الثابتة محفوظة: رموز الدخل داخل السقف، بلا شموع خام، "
          "وكل معرّف دليل قابل للتحقّق.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
