# -*- coding: utf-8 -*-
"""Label definition audit and comparison."""
from __future__ import annotations

from typing import Any

from scanner.ml.label_store import LabelName
from scanner.tracking import LOST, WON


def label_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit WIN/LOSS label definition."""
    win_loss = []
    pos_r = []
    disagreements = 0
    neutral_r = 0

    for r in rows:
        status = r.get("status") or (r.get("_meta") or {}).get("status")
        r_mult = r.get("label_r_multiple")
        if r_mult is None:
            r_mult = r.get("r_multiple")
        binary = int(r.get("label_binary_win") or 0)

        status_win = status in (WON, "won")
        r_win = r_mult is not None and float(r_mult) > 0
        win_loss.append(binary)
        pos_r.append(1 if r_win else 0)
        if r_mult is not None and float(r_mult) == 0:
            neutral_r += 1
        if status_win != r_win and r_mult is not None:
            disagreements += 1

    n = len(rows)
    return {
        "primary_label": LabelName.BINARY_WIN.value,
        "definition": "1 if r_multiple > 0 OR status=WON, else 0",
        "positive_class": "WIN (label_binary_win=1)",
        "negative_class": "LOSS (label_binary_win=0)",
        "neutral_handling": "r_multiple==0 counted as loss unless status=WON",
        "r_threshold": "> 0 for positive R label",
        "sample_size": n,
        "win_loss_positive_rate": round(sum(win_loss) / n, 4) if n else 0,
        "positive_r_rate": round(sum(pos_r) / n, 4) if n else 0,
        "status_vs_r_disagreements": disagreements,
        "neutral_r_count": neutral_r,
        "label_noise_estimate": round(disagreements / n, 4) if n else 0,
        "comparison": compare_labels(rows),
    }


def compare_labels(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare Model A (WIN/LOSS) vs Model B (positive R / negative R)."""
    agree = 0
    for r in rows:
        a = int(r.get("label_binary_win") or 0)
        r_mult = r.get("label_r_multiple")
        if r_mult is None:
            r_mult = r.get("r_multiple")
        b = 1 if (r_mult is not None and float(r_mult) > 0) else 0
        if a == b:
            agree += 1
    n = len(rows)
    return {
        "model_a": "WIN/LOSS (status-based with r fallback)",
        "model_b": "positive R / negative R (r_multiple > 0)",
        "agreement_rate": round(agree / n, 4) if n else 0,
        "recommendation": (
            "Labels are equivalent" if agree == n else
            f"Labels differ on {n - agree} trades — review before switching"
        ),
    }
