# -*- coding: utf-8 -*-
"""Pattern detector — evidence-backed recurring patterns."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

PATTERN_VERSION = "1.0.0"

ACCURACY_DROP_THRESHOLD = 50.0
SIMILARITY_THRESHOLD = 0.5
CONFIDENCE_OVERCONFIDENCE = 85.0
HALLUCINATION_REPEAT_MIN = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PatternDetector:
    """Detect recurring patterns from evaluations and optional context data."""

    def detect(self, evaluations: list[dict[str, Any]],
               context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        context = context or {}
        patterns: list[dict[str, Any]] = []

        patterns.extend(self._advisor_accuracy_drops(evaluations))
        patterns.extend(self._hallucination_patterns(evaluations))
        patterns.extend(self._timeframe_failures(evaluations))
        patterns.extend(self._strategy_failures(evaluations))
        patterns.extend(self._provider_failures(evaluations))
        patterns.extend(self._confidence_overconfidence(evaluations))

        research = context.get("research_results") or []
        patterns.extend(self._research_disagreement(research))

        optimization = context.get("optimization_results") or []
        patterns.extend(self._similarity_below_threshold(optimization, evaluations))

        trades = context.get("trade_outcomes") or []
        patterns.extend(self._low_liquidity_failures(trades, evaluations))

        predictions = context.get("prediction_results") or []
        patterns.extend(self._prediction_overconfidence(predictions, evaluations))

        return patterns

    def _advisor_accuracy_drops(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        by_provider: dict[str, list] = {}
        for e in evaluations:
            by_provider.setdefault(e.get("provider", "unknown"), []).append(e)

        patterns = []
        for provider, items in by_provider.items():
            if len(items) < 3:
                continue
            correct = sum(1 for e in items if e.get("advisor_correct"))
            acc = correct / len(items) * 100
            if acc < ACCURACY_DROP_THRESHOLD:
                patterns.append(self._pattern(
                    pattern_type="advisor_accuracy_drop",
                    title=f"Advisor accuracy drop: {provider}",
                    description=f"{provider} accuracy is {acc:.1f}% over {len(items)} evaluations.",
                    evidence=[e.get("evaluation_id", "") for e in items[:5]],
                    sample_size=len(items),
                    confidence=round(min(90, len(items) * 10), 1),
                    dimensions={"providers": [provider]},
                ))
        return patterns

    def _hallucination_patterns(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        hall = [e for e in evaluations if e.get("hallucination")]
        if len(hall) < HALLUCINATION_REPEAT_MIN:
            return []
        by_provider = Counter(e.get("provider", "unknown") for e in hall)
        top_prov, count = by_provider.most_common(1)[0]
        return [self._pattern(
            pattern_type="repeated_hallucination",
            title=f"Repeated hallucination from {top_prov}",
            description=f"{count} hallucination events detected across evaluations.",
            evidence=[e.get("evaluation_id", "") for e in hall[:5]],
            sample_size=len(hall),
            confidence=round(min(95, len(hall) * 15), 1),
            dimensions={"providers": [top_prov]},
        )]

    def _timeframe_failures(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        by_tf: dict[str, list] = {}
        for e in evaluations:
            tf = e.get("timeframe", "unknown")
            by_tf.setdefault(tf, []).append(e)

        patterns = []
        for tf, items in by_tf.items():
            if len(items) < 3:
                continue
            failures = [e for e in items if not e.get("advisor_correct")]
            fail_rate = len(failures) / len(items) * 100
            if fail_rate >= 60:
                patterns.append(self._pattern(
                    pattern_type="timeframe_specific_failure",
                    title=f"Timeframe failure cluster: {tf}",
                    description=f"{fail_rate:.0f}% failure rate on {tf} ({len(items)} trades).",
                    evidence=[e.get("evaluation_id", "") for e in failures[:5]],
                    sample_size=len(items),
                    confidence=round(min(85, len(items) * 8), 1),
                    dimensions={"timeframes": [tf]},
                ))
        return patterns

    def _strategy_failures(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        by_strat: dict[str, list] = {}
        for e in evaluations:
            s = e.get("strategy", "unknown")
            by_strat.setdefault(s, []).append(e)

        patterns = []
        for strat, items in by_strat.items():
            if len(items) < 3:
                continue
            failures = [e for e in items if not e.get("advisor_correct")]
            fail_rate = len(failures) / len(items) * 100
            if fail_rate >= 60:
                patterns.append(self._pattern(
                    pattern_type="strategy_specific_failure",
                    title=f"Strategy failure cluster: {strat}",
                    description=f"{fail_rate:.0f}% failure rate on {strat} strategy.",
                    evidence=[e.get("evaluation_id", "") for e in failures[:5]],
                    sample_size=len(items),
                    confidence=round(min(85, len(items) * 8), 1),
                    dimensions={"strategies": [strat]},
                ))
        return patterns

    def _provider_failures(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        return self._advisor_accuracy_drops(evaluations)

    def _confidence_overconfidence(self, evaluations: list[dict[str, Any]]) -> list[dict]:
        high_conf_wrong = [
            e for e in evaluations
            if (e.get("advisor_confidence") or 0) >= CONFIDENCE_OVERCONFIDENCE
            and not e.get("advisor_correct")
        ]
        if len(high_conf_wrong) < 2:
            return []
        return [self._pattern(
            pattern_type="prediction_overconfidence",
            title="High-confidence advisor failures",
            description=f"{len(high_conf_wrong)} evaluations with confidence ≥{CONFIDENCE_OVERCONFIDENCE}% were incorrect.",
            evidence=[e.get("evaluation_id", "") for e in high_conf_wrong[:5]],
            sample_size=len(high_conf_wrong),
            confidence=round(min(90, len(high_conf_wrong) * 12), 1),
            dimensions={},
        )]

    def _research_disagreement(self, research: list[dict[str, Any]]) -> list[dict]:
        disagreements = [
            r for r in research
            if r.get("verdict") in ("disagree", "conflict", "rejected")
            or r.get("agreement_score", 1.0) < 0.5
        ]
        if not disagreements:
            return []
        return [self._pattern(
            pattern_type="research_disagreement",
            title="Research disagreement detected",
            description=f"{len(disagreements)} research results show disagreement with platform.",
            evidence=[r.get("experiment_id", r.get("id", "")) for r in disagreements[:5]],
            sample_size=len(disagreements),
            confidence=70.0,
            dimensions={},
        )]

    def _similarity_below_threshold(self, optimization: list[dict[str, Any]],
                                    evaluations: list[dict[str, Any]]) -> list[dict]:
        low_sim = [
            o for o in optimization
            if (o.get("similarity_score") or o.get("average_similarity") or 1.0) < SIMILARITY_THRESHOLD
        ]
        if not low_sim:
            return []
        return [self._pattern(
            pattern_type="similarity_below_threshold",
            title="Similarity below threshold",
            description=f"{len(low_sim)} optimization results show similarity below {SIMILARITY_THRESHOLD}.",
            evidence=[o.get("optimization_id", o.get("id", "")) for o in low_sim[:5]],
            sample_size=len(low_sim),
            confidence=75.0,
            dimensions={},
        )]

    def _low_liquidity_failures(self, trades: list[dict[str, Any]],
                                evaluations: list[dict[str, Any]]) -> list[dict]:
        low_liq = [t for t in trades if t.get("low_liquidity") or (t.get("liquidity_score") or 1) < 0.3]
        if len(low_liq) < 2:
            return []
        failed_evals = [e for e in evaluations if not e.get("advisor_correct")]
        if not failed_evals:
            return []
        return [self._pattern(
            pattern_type="low_liquidity_failure",
            title="Low liquidity trade failures",
            description=f"{len(low_liq)} low-liquidity trades correlated with advisor failures.",
            evidence=[e.get("evaluation_id", "") for e in failed_evals[:5]],
            sample_size=len(low_liq),
            confidence=65.0,
            dimensions={"markets": list({t.get("market", "") for t in low_liq if t.get("market")})},
        )]

    def _prediction_overconfidence(self, predictions: list[dict[str, Any]],
                                   evaluations: list[dict[str, Any]]) -> list[dict]:
        overconf = [
            p for p in predictions
            if (p.get("confidence") or 0) > 0.85 and p.get("correct") is False
        ]
        if not overconf:
            return []
        return [self._pattern(
            pattern_type="prediction_overconfidence",
            title="Prediction model overconfidence",
            description=f"{len(overconf)} predictions with high confidence were wrong.",
            evidence=[p.get("prediction_id", p.get("model_id", "")) for p in overconf[:5]],
            sample_size=len(overconf),
            confidence=80.0,
            dimensions={},
        )]

    @staticmethod
    def _pattern(*, pattern_type: str, title: str, description: str,
                 evidence: list[str], sample_size: int, confidence: float,
                 dimensions: dict[str, list[str]]) -> dict[str, Any]:
        return {
            "pattern_type": pattern_type,
            "title": title,
            "description": description,
            "supporting_evidence": [e for e in evidence if e],
            "sample_size": sample_size,
            "confidence": confidence,
            "affected_markets": dimensions.get("markets", []),
            "affected_strategies": dimensions.get("strategies", []),
            "affected_providers": dimensions.get("providers", []),
            "affected_timeframes": dimensions.get("timeframes", []),
            "detected_at": _now(),
            "pattern_version": PATTERN_VERSION,
        }
