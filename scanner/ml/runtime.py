"""Runtime ML voter (optional and switchable)."""
from __future__ import annotations

import json
from pathlib import Path


MODEL_META = Path("data/ml/lgbm_metrics.json")


def load_gate() -> dict | None:
    if not MODEL_META.exists():
        return None
    try:
        return json.loads(MODEL_META.read_text(encoding="utf-8"))
    except Exception:
        return None


def vote(score: float, htf: int, confluence: list[str], pa_score: int) -> tuple[float, float] | None:
    """يعيد (probability, vote_weight) أو None إن النموذج غير صالح."""
    meta = load_gate()
    if not meta or not meta.get("pass_gate"):
        return None
    # تقريب احتمالي بسيط كحارس نشر: يعتمد فقط عندما baseline gate ناجح.
    raw = 0.45 + min(0.25, max(-0.25, score / 200.0))
    raw += 0.08 if htf == 1 else (-0.08 if htf == -1 else 0.0)
    raw += min(0.12, 0.03 * len(confluence or []))
    raw += 0.05 if pa_score > 0 else (-0.05 if pa_score < 0 else 0.0)
    prob = min(0.95, max(0.05, raw))
    weight = (prob - 0.5) * 2.0
    return prob, weight
