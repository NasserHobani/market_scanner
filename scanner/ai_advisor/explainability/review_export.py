# -*- coding: utf-8 -*-
"""Export advisor reviews — JSON, Markdown, PDF."""
from __future__ import annotations

import json
from typing import Any


def export_json(review: dict[str, Any]) -> str:
    return json.dumps(review, indent=2, ensure_ascii=False, default=str)


def export_markdown(review: dict[str, Any]) -> str:
    lines = [
        f"# AI Advisor Review — {review.get('review_id', '')}",
        "",
        f"**Symbol:** {review.get('symbol')} | **Provider:** {review.get('provider')} | "
        f"**Model:** {review.get('model')}",
        f"**Time:** {review.get('timestamp')} | **Type:** {review.get('review_type', 'automatic')}",
        "",
        "## Metrics",
        f"- Latency: {review.get('latency_ms')} ms",
        f"- Tokens: {review.get('total_tokens')} (prompt {review.get('prompt_tokens')}, "
        f"completion {review.get('completion_tokens')})",
        f"- Cost: ${review.get('estimated_cost')}",
        f"- Grounding: {review.get('grounding_score')} | Hallucination: {review.get('hallucination_score')}",
        f"- Agreement: {review.get('agreement')} | Confidence: {review.get('confidence')}%",
        "",
        "## Executive Summary",
        review.get("summary", ""),
        "",
        "## Full Reasoning",
        review.get("reasoning", ""),
        "",
        "## Supporting Evidence",
    ]
    for ev in review.get("supporting_evidence") or []:
        if isinstance(ev, dict):
            lines.append(f"- **{ev.get('evidence_id')}** ({ev.get('section')}): {ev.get('note', '')}")
    lines.append("")
    lines.append("## Contradicting Evidence")
    for ev in review.get("contradicting_evidence") or []:
        if isinstance(ev, dict):
            lines.append(f"- **{ev.get('evidence_id')}** ({ev.get('section')}): {ev.get('note', '')}")
    lines.append("")
    lines.append("## Risks")
    for r in review.get("risks") or []:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("## Missing Information")
    for m in review.get("missing_information") or []:
        lines.append(f"- {m}")
    exp = review.get("suggested_experiment")
    if isinstance(exp, dict) and exp.get("hypothesis"):
        lines.extend([
            "", "## Suggested Experiment",
            f"**Hypothesis:** {exp.get('hypothesis', '')}",
            f"**Method:** {exp.get('method', '')}",
            f"**Expected:** {exp.get('expected_outcome', '')}",
        ])
    tr = review.get("trade_result") or {}
    if tr.get("outcome"):
        lines.extend([
            "", "## Trade Result",
            f"- Outcome: {tr.get('outcome')}",
            f"- R: {tr.get('r_multiple')}",
            f"- Claude correct: {tr.get('claude_correct')}",
        ])
    return "\n".join(lines)


def export_pdf_bytes(review: dict[str, Any]) -> bytes:
    """Minimal PDF — text lines via simple PDF structure."""
    text = export_markdown(review)
    lines = text.replace("\r", "").split("\n")[:80]
    content_lines = ["BT /F1 10 Tf 50 750 Td"]
    y = 0
    for line in lines:
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if len(safe) > 90:
            safe = safe[:87] + "..."
        content_lines.append(f"0 -14 Td ({safe}) Tj")
        y += 14
        if y > 700:
            break
    content_lines.append("ET")
    stream = "\n".join(content_lines)
    stream_bytes = stream.encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources<< /Font<< /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        f"4 0 obj<< /Length {len(stream_bytes)} >>stream\n".encode()
        + stream_bytes + b"\nendstream endobj\n"
    )
    objects.append(
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n"
    )

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf += obj
    xref_pos = len(pdf)
    pdf += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    for off in offsets[1:]:
        pdf += f"{off:010d} 00000 n \n".encode()
    pdf += (
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode()
    return pdf
