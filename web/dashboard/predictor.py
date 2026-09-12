# -*- coding: utf-8 -*-
"""بناء المجموعتين، والتدريب، وبوّابة الترقية.

المحاكاة تُدرّب والحقيقة تحكم. وكل رقمٍ هنا مقيسٌ لا مفترَض.
"""
from __future__ import annotations

import logging

log = logging.getLogger("dashboard.predictor")

# ═══ حدّ العيّنة الحقيقية للحكم ═══
#
# الحكم على ثلاثة عشر صفّاً ليس حكماً: فاصل الثقة يبتلع كل فرق.
# فدون هذا الحدّ تُرفض الترقية صراحةً بسبب العيّنة لا بسبب الأداء —
# وفرقٌ بين «فشل» و«لا نعرف».
MIN_REAL_FOR_GATE = 40

# أقلّ تفوّق يُعتدّ به على خطّ الأساس
MIN_EDGE = 0.02


def engine_name() -> dict[str, str]:
    """أيّ مكتبةٍ ستدرّب فعلاً — لا ما نتمنّاه.

    السلسلة: ``lightgbm`` ← ``sklearn`` ← مصنّفٌ بسيط مكتوب بيد.
    والثالث يعمل ويُنتج «نموذجاً»، فتقول الشاشة «نشط» ويظنّه
    القارئ LightGBM. فيُقال الاسم.
    """
    try:
        import lightgbm  # noqa: F401

        return {"name": "lightgbm", "note": "المكتبة المقصودة"}
    except ImportError:
        pass
    try:
        import sklearn  # noqa: F401

        return {"name": "sklearn_rf",
                "note": "غابة عشوائية — بديلٌ معقول، أضعف من LightGBM"}
    except ImportError:
        pass
    return {"name": "simple_fallback",
            "note": "مصنّفٌ بسيط مكتوب بيد — للتشغيل لا للإنتاج"}


def _scan_rows() -> list[dict]:
    from .models import ScanResult

    return list(
        ScanResult.objects.exclude(pit_snapshot_id="")
        .exclude(entry__isnull=True).exclude(stop__isnull=True)
        .exclude(target1__isnull=True)
        .order_by("candle_time")
        .values("symbol", "market", "timeframe", "candle_time",
                "entry", "stop", "target1", "pit_snapshot_id")
    )


def _real_rows() -> dict:
    """صفوف الصفقات الحقيقية — الحَكَم."""
    from scanner.predictive.dataset_v3 import build_dataset_v3

    from .models import Trade

    trades = []
    for t in Trade.objects.filter(status__in=("won", "lost")).values(
            "id", "symbol", "market", "timeframe", "status", "r_multiple",
            "signal_at", "feature_snapshot_id", "pit_snapshot_id"):
        d = dict(t)
        d["trade_id"] = d.pop("id")
        trades.append(d)
    man = build_dataset_v3(trades, reconstruct=False, validate_leakage=True)
    rows = man.get("rows") or man.get("eligible") or []
    wins = sum(1 for r in rows if float(r.get("label_binary_win") or 0) > 0)
    return {
        "label_source": "real_trades",
        "eligible_count": len(rows),
        "win_rate": round(100 * wins / len(rows), 1) if rows else None,
        "rows": rows,
        "skipped": man.get("rejection_reasons") or {},
    }


def build_datasets() -> dict:
    from scanner.predictive import dataset_sim

    sim = dataset_sim.build(list(_scan_rows()))
    return {"simulated": sim, "real": _real_rows()}


def _matrix(rows: list[dict]) -> tuple[list[list], list[int], list[str]]:
    """صفوف → مصفوفة ميزات ووسوم، بترتيب أعمدة ثابت.

    الترتيب من العقد لا من أوّل صفّ: قاموسُ بايثون يحفظ ترتيب
    الإدراج، فصفٌّ ينقصه عمود يُزيح ما بعده — ويتدرّب النموذج على
    أعمدةٍ مختلطة بلا أن يفشل شيء.
    """
    from scanner.predictive.feature_registry import v3_columns_with_missing

    cols = v3_columns_with_missing()
    X, y = [], []
    for r in rows:
        f = r.get("features") or {}
        X.append([f.get(c) for c in cols])
        y.append(int(float(r.get("label_binary_win") or 0) > 0))
    return X, y, cols


def _fit(X, y):
    """يدرّب بأفضل محرّك متاح — ويعيد اسمه معه."""
    eng = engine_name()["name"]
    if eng == "lightgbm":
        from lightgbm import LGBMClassifier

        m = LGBMClassifier(n_estimators=200, num_leaves=15,
                           min_child_samples=10, learning_rate=0.05,
                           random_state=42, verbose=-1)
    elif eng == "sklearn_rf":
        from sklearn.ensemble import RandomForestClassifier

        m = RandomForestClassifier(n_estimators=200, min_samples_leaf=5,
                                   random_state=42)
        X = [[0.0 if v is None else v for v in row] for row in X]
    else:
        return _MeanClassifier().fit(X, y), eng
    m.fit(X, y)
    return m, eng


class _MeanClassifier:
    """بديلٌ نقيّ بلا مكتبات — يوثَّق بوصفه بديلاً لا نموذجاً."""

    def __init__(self) -> None:
        self.pos: list[float] = []
        self.neg: list[float] = []

    @staticmethod
    def _mean(rows: list[list], keep: list[bool]) -> list[float]:
        n = len(rows[0]) if rows else 0
        out = []
        for j in range(n):
            vals = [float(r[j]) for r, k in zip(rows, keep)
                    if k and r[j] is not None]
            out.append(sum(vals) / len(vals) if vals else 0.0)
        return out

    def fit(self, X, y):
        self.pos = self._mean(X, [v == 1 for v in y])
        self.neg = self._mean(X, [v == 0 for v in y])
        return self

    def predict_proba(self, X):
        out = []
        for row in X:
            dp = sum(abs((0.0 if v is None else float(v)) - p)
                     for v, p in zip(row, self.pos))
            dn = sum(abs((0.0 if v is None else float(v)) - p)
                     for v, p in zip(row, self.neg))
            tot = dp + dn
            p = 0.5 if tot == 0 else dn / tot
            out.append([1 - p, p])
        return out


def evaluate(model, rows: list[dict]) -> dict:
    """دقّة النموذج على صفوفٍ لم يرها."""
    if not rows:
        return {"n": 0, "accuracy": None}
    X, y, _ = _matrix(rows)
    try:
        proba = model.predict_proba(X)
    except Exception:  # noqa: BLE001
        return {"n": len(rows), "accuracy": None}
    pred = [1 if p[1] >= 0.5 else 0 for p in proba]
    hit = sum(1 for a, b in zip(pred, y) if a == b)
    return {"n": len(rows), "accuracy": round(hit / len(y), 4)}


def train_and_gate(sim: dict, real: dict, *, promote: bool = False) -> dict:
    """يدرّب على المحاكاة، ويحكم بالحقيقة.

    ═══ الحَكَم لا يُرى في التدريب ═══

    صفوف الصفقات الحقيقية لا تدخل التدريب إطلاقاً. ونموذجٌ يُقاس
    على ما تدرّب عليه يعطي رقماً جميلاً لا معنى له.
    """
    log_lines: list[str] = []
    rows = sim.get("rows") or []
    X, y, cols = _matrix(rows)
    model, eng = _fit(X, y)
    log_lines.append(f"دُرِّب على {len(rows)} صفّ محاكاة · {len(cols)} عموداً"
                     f" · محرّك {eng}")

    real_rows = real.get("rows") or []
    # خطّ الأساس: التخمين بالفئة الأكثر شيوعاً في الحقيقي
    if real_rows:
        _, ry, _ = _matrix(real_rows)
        major = 1 if sum(ry) * 2 >= len(ry) else 0
        baseline = sum(1 for v in ry if v == major) / len(ry)
    else:
        baseline = 0.0

    ev = evaluate(model, real_rows)
    acc = ev.get("accuracy")
    n = ev.get("n") or 0
    log_lines.append(f"قِيس على {n} صفّاً حقيقياً لم يرها")

    delta = (acc - baseline) if acc is not None else 0.0
    passed, reason = True, ""
    if n < MIN_REAL_FOR_GATE:
        passed = False
        reason = (f"العيّنة الحقيقية {n} دون {MIN_REAL_FOR_GATE} — "
                  "لا يُحكم بها")
    elif acc is None:
        passed, reason = False, "تعذّر القياس"
    elif delta < MIN_EDGE:
        passed = False
        reason = f"لم يتجاوز الأساس بـ{MIN_EDGE:+.2f}"

    out = {
        "gate": {
            "baseline": round(baseline, 4),
            "model": acc, "delta": round(delta, 4),
            "real_n": n, "passed": passed, "reason": reason,
        },
        "engine": eng,
        "log": log_lines,
        "promoted": False,
    }
    if promote and passed:
        out["promoted"] = True
        log_lines.append("رُقّي النموذج")
    return out


__all__ = ["build_datasets", "train_and_gate", "evaluate", "engine_name",
           "MIN_REAL_FOR_GATE", "MIN_EDGE"]
