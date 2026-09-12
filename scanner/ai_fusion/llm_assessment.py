# -*- coding: utf-8 -*-
"""Extract LLM prediction assessment from advisor response."""
from __future__ import annotations

from typing import Any


def extract_llm_assessment(review_response: dict[str, Any] | None) -> dict[str, Any]:
    """Map advisor JSON to fusion-friendly assessment."""
    if not review_response:
        return {
            "agreement": "insufficient",
            "prediction_assessment": "unavailable",
            "confidence": None,
            "reasoning": "",
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "risks": [],
        }

    resp = review_response
    assessment = str(
        resp.get("prediction_assessment")
        or resp.get("statistical_assessment")
        or ""
    ).lower()

    if not assessment:
        agreement = str(resp.get("agreement", "")).lower()
        if agreement == "agree":
            assessment = "supported"
        elif agreement == "disagree":
            assessment = "contradicted"
        elif agreement == "partial":
            assessment = "mixed"
        else:
            assessment = "unavailable"

    return {
        "agreement": resp.get("agreement", "insufficient"),
        "prediction_assessment": assessment,
        "confidence": resp.get("confidence"),
        "reasoning": resp.get("reasoning") or resp.get("summary", ""),
        "supporting_evidence": list(resp.get("supporting_evidence") or []),
        "contradicting_evidence": list(resp.get("contradicting_evidence") or []),
        "risks": list(resp.get("risks") or []),
        "missing_information": list(resp.get("missing_information") or []),
    }
