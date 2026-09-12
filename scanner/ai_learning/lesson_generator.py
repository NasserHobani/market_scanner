# -*- coding: utf-8 -*-
"""Lesson generator — transforms patterns and evaluations into structured lessons."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .failure_classifier import classify_evaluation
from .failure_labels import description_ar, title_ar, title_en
from .lesson_fingerprint import lesson_fingerprint
from .lesson_thresholds import recommendation_for_sample

LESSON_VERSION = "1.1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _trade_example(e: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_id": e.get("trade_id", ""),
        "symbol": e.get("symbol", ""),
        "evaluation_id": e.get("evaluation_id", ""),
        "outcome": e.get("outcome") or e.get("trade_result", ""),
        "r_multiple": e.get("r_multiple"),
        "agreement": e.get("advisor_agreement", ""),
        "confidence": e.get("advisor_confidence"),
    }


def _confidence_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    vals = [float(e.get("advisor_confidence") or 0) for e in items if e.get("advisor_confidence") is not None]
    if not vals:
        return {"avg": None, "min": None, "max": None}
    return {
        "avg": round(sum(vals) / len(vals), 1),
        "min": round(min(vals), 1),
        "max": round(max(vals), 1),
    }


class LessonGenerator:
    """Generate structured lessons from detected patterns and evaluations."""

    def generate(self, patterns: list[dict[str, Any]],
                 evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        lessons: list[dict[str, Any]] = []
        for pattern in patterns:
            lessons.append(self._from_pattern(pattern))

        lessons.extend(self._from_failure_groups(evaluations))
        lessons.extend(self._from_correct_disagreements(evaluations))
        lessons.extend(self._from_successes(evaluations))
        return lessons

    def _from_pattern(self, pattern: dict[str, Any]) -> dict[str, Any]:
        ptype = pattern.get("pattern_type", "")
        fp = lesson_fingerprint(
            pattern_type=ptype,
            provider=(pattern.get("affected_providers") or ["any"])[0],
            market=(pattern.get("affected_markets") or ["any"])[0],
            timeframe=(pattern.get("affected_timeframes") or ["any"])[0],
            strategy=(pattern.get("affected_strategies") or ["any"])[0],
        )
        sample = pattern.get("sample_size", 0)
        rec = recommendation_for_sample(sample)
        now = _now()
        return {
            "lesson_id": f"lesson_{uuid.uuid4().hex[:16]}",
            "fingerprint": fp,
            "title": pattern.get("title", "Detected pattern"),
            "title_ar": pattern.get("title_ar", pattern.get("title", "نمط مكتشف")),
            "failure_type": ptype,
            "secondary_type": None,
            "description": pattern.get("description", ""),
            "description_ar": pattern.get("description_ar", pattern.get("description", "")),
            "supporting_evidence": pattern.get("supporting_evidence", []),
            "evidence": list(pattern.get("supporting_evidence", [])),
            "trade_examples": [],
            "sample_size": sample,
            "confidence": pattern.get("confidence", 0),
            "confidence_summary": {},
            "affected_markets": pattern.get("affected_markets", []),
            "affected_symbols": pattern.get("affected_symbols", []),
            "affected_timeframes": pattern.get("affected_timeframes", []),
            "affected_strategies": pattern.get("affected_strategies", []),
            "affected_providers": pattern.get("affected_providers", []),
            "provider": (pattern.get("affected_providers") or [""])[0],
            "recommendation": rec["recommendation"],
            "recommendation_ar": rec["recommendation_ar"],
            "recommendation_strength": rec["strength"],
            "first_seen": now,
            "last_seen": now,
            "created_at": now,
            "status": "NEW",
            "source": "pattern_detection",
            "pattern_type": ptype,
            "lesson_version": LESSON_VERSION,
            "is_failure": ptype not in ("success_cluster",),
        }

    def _classified(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for e in evaluations:
            cls = classify_evaluation(e)
            merged = {**e, **cls}
            if "outcome" not in merged or not merged["outcome"]:
                merged["outcome"] = cls["outcome"]
            out.append(merged)
        return out

    def _from_failure_groups(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        classified = self._classified(evaluations)
        failures = [e for e in classified if e.get("is_failure") and e.get("failure_type")]
        groups: dict[str, list[dict[str, Any]]] = {}
        for e in failures:
            key = "|".join([
                e.get("failure_type", ""),
                e.get("provider", "any"),
                e.get("market", "any"),
                e.get("timeframe", "any"),
                e.get("strategy", "any"),
            ])
            groups.setdefault(key, []).append(e)

        lessons = []
        for _key, items in groups.items():
            lessons.append(self._build_failure_lesson(items))
        return lessons

    def _from_correct_disagreements(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        classified = self._classified(evaluations)
        items = [e for e in classified if e.get("evaluation_type") == "correct_disagreement"]
        if not items:
            return []
        groups: dict[str, list[dict[str, Any]]] = {}
        for e in items:
            key = "|".join([
                "correct_disagreement",
                e.get("provider", "any"),
                e.get("market", "any"),
                e.get("timeframe", "any"),
            ])
            groups.setdefault(key, []).append(e)
        return [self._build_success_lesson("correct_disagreement", grp) for grp in groups.values()]

    def _build_failure_lesson(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        first = items[0]
        ftype = str(first.get("failure_type") or "other_failure")
        provider = str(first.get("provider") or "")
        market = str(first.get("market") or "")
        timeframe = str(first.get("timeframe") or "")
        strategy = str(first.get("strategy") or "")
        fp = lesson_fingerprint(
            failure_type=ftype,
            provider=provider,
            market=market,
            timeframe=timeframe,
            strategy=strategy,
        )
        sample = len(items)
        rec = recommendation_for_sample(sample)
        symbols = _unique([str(e.get("symbol") or "") for e in items])
        evidence = _unique([str(e.get("evaluation_id") or "") for e in items])
        now = _now()
        sec = first.get("secondary_type")
        desc_en = title_en(ftype)
        desc_ar_text = description_ar(ftype)
        if sample == 1 and items[0].get("r_multiple") is not None:
            r = items[0]["r_multiple"]
            sign = "+" if float(r) >= 0 else ""
            desc_ar_text = (
                f"{description_ar(ftype)} "
                f"مثال: R {sign}{float(r):.2f}."
            ).strip()

        return {
            "lesson_id": f"lesson_{uuid.uuid4().hex[:16]}",
            "fingerprint": fp,
            "title": desc_en,
            "title_ar": title_ar(ftype),
            "failure_type": ftype,
            "secondary_type": sec,
            "description": desc_en,
            "description_ar": desc_ar_text or title_ar(ftype),
            "supporting_evidence": evidence[:10],
            "evidence": evidence[:20],
            "trade_examples": [_trade_example(e) for e in items[:10]],
            "sample_size": sample,
            "confidence": round(min(90, sample * 10), 1),
            "confidence_summary": _confidence_summary(items),
            "affected_markets": _unique([str(e.get("market") or "") for e in items]),
            "affected_symbols": symbols,
            "affected_timeframes": _unique([str(e.get("timeframe") or "") for e in items]),
            "affected_strategies": _unique([str(e.get("strategy") or "") for e in items]),
            "affected_providers": _unique([str(e.get("provider") or "") for e in items]),
            "provider": provider,
            "recommendation": rec["recommendation"],
            "recommendation_ar": rec["recommendation_ar"],
            "recommendation_strength": rec["strength"],
            "first_seen": now,
            "last_seen": now,
            "created_at": now,
            "status": "NEW",
            "source": "failure_analysis",
            "pattern_type": ftype,
            "lesson_version": LESSON_VERSION,
            "is_failure": True,
        }

    def _build_success_lesson(self, kind: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        first = items[0]
        provider = str(first.get("provider") or "")
        market = str(first.get("market") or "")
        timeframe = str(first.get("timeframe") or "")
        fp = lesson_fingerprint(
            failure_type=kind,
            provider=provider,
            market=market,
            timeframe=timeframe,
        )
        sample = len(items)
        rec = recommendation_for_sample(sample)
        evidence = _unique([str(e.get("evaluation_id") or "") for e in items])
        now = _now()
        return {
            "lesson_id": f"lesson_{uuid.uuid4().hex[:16]}",
            "fingerprint": fp,
            "title": title_en(kind),
            "title_ar": title_ar(kind),
            "failure_type": None,
            "secondary_type": None,
            "description": title_en(kind),
            "description_ar": description_ar(kind),
            "supporting_evidence": evidence[:10],
            "evidence": evidence[:20],
            "trade_examples": [_trade_example(e) for e in items[:10]],
            "sample_size": sample,
            "confidence": round(min(85, sample * 8), 1),
            "confidence_summary": _confidence_summary(items),
            "affected_markets": _unique([str(e.get("market") or "") for e in items]),
            "affected_symbols": _unique([str(e.get("symbol") or "") for e in items]),
            "affected_timeframes": _unique([str(e.get("timeframe") or "") for e in items]),
            "affected_strategies": _unique([str(e.get("strategy") or "") for e in items]),
            "affected_providers": _unique([str(e.get("provider") or "") for e in items]),
            "provider": provider,
            "recommendation": rec["recommendation"],
            "recommendation_ar": rec["recommendation_ar"],
            "recommendation_strength": rec["strength"],
            "first_seen": now,
            "last_seen": now,
            "created_at": now,
            "status": "NEW",
            "source": "success_analysis",
            "pattern_type": kind,
            "lesson_version": LESSON_VERSION,
            "is_failure": False,
        }

    def _from_successes(self, evaluations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        classified = self._classified(evaluations)
        successes = [
            e for e in classified
            if e.get("advisor_correct") and e.get("evaluation_type") != "correct_disagreement"
        ]
        if len(successes) < 3:
            return []

        by_market: dict[str, list] = {}
        for e in successes:
            by_market.setdefault(e.get("market", "unknown"), []).append(e)

        lessons = []
        for market, items in by_market.items():
            if len(items) < 3:
                continue
            lessons.append(self._build_success_lesson("success_cluster", items))
        return lessons
