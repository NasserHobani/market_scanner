# -*- coding: utf-8 -*-
"""تقرير البتكوين الجاهز للعرض — يجمع الحالة والنموذج والحكم.

مستقلّ عن Django عمداً: العرض يستدعيه، والاختبار يستدعيه، وسطر
الأوامر يستدعيه — بنفس الأرقام. مصدر واحد يمنع اختلاف الشاشات.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import direction, regime

TIMEFRAMES = ("15m", "1h", "4h", "1d")

# الحدّ الذي دونه لا نعرض النموذج كأنه يقرّر شيئاً
MIN_EDGE_POINTS = 2.0


def snapshot(df: pd.DataFrame) -> dict:
    """الحالة الحالية للبتكوين على فريم واحد."""
    if df is None or len(df) < 60:
        return {}
    feats = regime.build(df)
    if feats.empty:
        return {}
    last = feats.iloc[-1]
    close = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2]) if len(df) > 1 else close
    trend = last.get("trend")
    return {
        "close": close,
        "change_pct": (close / prev - 1) * 100 if prev else 0.0,
        "candle_time": df.index[-1],
        "trend": ("صاعد" if trend == 1 else
                  "هابط" if trend == -1 else "مختلط"),
        "trend_value": int(trend) if not pd.isna(trend) else 0,
        "features": {k: (None if pd.isna(last[k]) else float(last[k]))
                     for k in regime.FEATURES},
        "labels": dict(regime.FEATURES),
    }


def direction_report(df: pd.DataFrame, *, horizon: int = 1,
                     min_train: int = 500, step: int = 80) -> dict:
    """قياس النموذج مقابل خطوط الأساس — لا دقّة مجرّدة أبداً.

    ``valid`` هو الحقل الذي يجب أن تقرأه الواجهة قبل أي رقم آخر: نتيجة
    لا تتفوّق على خطّ أساس ليست توقّعاً بل ضجيجاً مصقولاً.
    """
    if df is None or len(df) < min_train + step + 50:
        return {"valid": False, "reason": "تاريخ غير كافٍ للتقييم"}

    feats = regime.build(df)
    y = regime.label_direction(df, horizon)
    x = feats.to_numpy(dtype="float64")
    res = direction.walk_forward(x, y, min_train=min_train, step=step)
    if not res.folds:
        return {"valid": False, "reason": "لم تكتمل نافذة تقييم واحدة"}

    best_name = max(res.baselines, key=res.baselines.get) if res.baselines else ""
    return {
        "valid": True,
        "model": res.name,
        "accuracy": res.accuracy * 100,
        "ci_low": res.ci_low * 100,
        "ci_high": res.ci_high * 100,
        "baselines": {k: v * 100 for k, v in res.baselines.items()},
        "best_baseline": best_name,
        "best_baseline_value": max(res.baselines.values()) * 100 if res.baselines else 0,
        "edge_points": res.edge * 100,
        "beats_baseline": res.beats_baseline,
        "n_test": res.n_test,
        "folds": len(res.folds),
        "has_lightgbm": direction.HAS_LGB,
        "usable": res.beats_baseline and res.edge * 100 >= MIN_EDGE_POINTS,
    }


def current_probability(df: pd.DataFrame, *, horizon: int = 1,
                        min_train: int = 500) -> dict:
    """احتمال صعود الشمعة القادمة — بالنموذج نفسه المقيَّم أعلاه.

    يُدرَّب على كل التاريخ حتى آخر شمعة **مغلقة**، ويتنبّأ بالتالية.
    ولا يُعرض إلا مقروناً بحكم ``direction_report`` على صلاحيته.
    """
    if df is None or len(df) < min_train + 50:
        return {}
    feats = regime.build(df)
    y = regime.label_direction(df, horizon)
    x = feats.to_numpy(dtype="float64")

    ok = ~np.isnan(y) & ~np.isnan(x).any(axis=1)
    xa, ya = x[ok], y[ok]
    if xa.shape[0] < min_train:
        return {}
    # آخر صفّ صالح للتنبّؤ: خصائصه مكتملة وإن لم تُعرف نتيجته بعد
    live = x[~np.isnan(x).any(axis=1)]
    if live.size == 0:
        return {}
    xr = live[-1:].copy()

    mu, sd = xa.mean(axis=0), xa.std(axis=0)
    sd[sd == 0] = 1.0
    if direction.HAS_LGB:
        model = direction.lgb.LGBMClassifier(   # type: ignore[union-attr]
            n_estimators=200, learning_rate=0.05, num_leaves=15,
            min_child_samples=30, verbose=-1, random_state=0)
        model.fit(xa, ya)
        p = float(model.predict_proba(xr)[0, 1])
    else:
        w = direction._logistic((xa - mu) / sd, ya)
        p = float(direction._logistic_predict(w, (xr - mu) / sd)[0])
    return {"prob_up": p * 100, "prob_down": (1 - p) * 100,
            "trained_on": int(xa.shape[0])}


def importance(df: pd.DataFrame, *, horizon: int = 1) -> list[dict]:
    feats = regime.build(df)
    y = regime.label_direction(df, horizon)
    x = feats.to_numpy(dtype="float64")
    out = direction.feature_importance(x, y, list(regime.FEATURES))
    return [{"key": k, "label": regime.FEATURES.get(k, k),
             "drop": v * 100} for k, v in out[:8]]


def build_all(load, *, timeframes=TIMEFRAMES) -> dict:
    """التقرير الكامل. ``load(tf)`` دالة تُعيد إطار شموع البتكوين.

    تُمرَّر الدالة بدل استيراد التخزين هنا، فيبقى الملف قابلاً للاختبار
    ببيانات مصطنعة بلا قرص ولا شبكة.
    """
    states: dict[str, dict] = {}
    for tf in timeframes:
        try:
            snap = snapshot(load(tf))
        except Exception:  # noqa: BLE001
            snap = {}
        if snap:
            states[tf] = snap

    # التقييم على 4h و1d فقط: الفريمان اللذان لهما تاريخ كافٍ، وقد
    # قِيس أن 1h و15m لا يتفوّقان على خطّ الأساس أصلاً
    models: dict[str, dict] = {}
    for tf in ("4h", "1d"):
        try:
            df = load(tf)
            rep = direction_report(df)
            if rep.get("valid") and rep.get("usable"):
                rep["now"] = current_probability(df)
            models[tf] = rep
        except Exception as exc:  # noqa: BLE001
            models[tf] = {"valid": False, "reason": str(exc)[:120]}

    agree = _consensus(states)
    return {"states": states, "models": models, "consensus": agree,
            "feature_labels": dict(regime.FEATURES)}


def _consensus(states: dict) -> dict:
    """توافق الفريمات على الاتجاه — عدّ لا رأي."""
    vals = [s.get("trend_value", 0) for s in states.values()]
    if not vals:
        return {}
    up = sum(1 for v in vals if v == 1)
    down = sum(1 for v in vals if v == -1)
    total = len(vals)
    if up == total:
        text = "كل الفريمات صاعدة"
    elif down == total:
        text = "كل الفريمات هابطة"
    else:
        text = f"{up} صاعد · {down} هابط · {total - up - down} مختلط"
    return {"up": up, "down": down, "mixed": total - up - down,
            "total": total, "text": text,
            "aligned": up == total or down == total}
