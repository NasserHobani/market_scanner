"""تدريب LightGBM على Feature Store مع تقييم OOS."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from scanner.ml.dataset import build_bundle, load_training_data


def _split_idx(n: int, ratio: float) -> tuple[np.ndarray, np.ndarray]:
    cut = max(1, int(n * ratio))
    idx = np.arange(n)
    return idx[:cut], idx[cut:]


def _fit_predict(X_train, y_train, X_test):
    try:
        from lightgbm import LGBMClassifier
        model = LGBMClassifier(
            n_estimators=180, learning_rate=0.05, num_leaves=31, random_state=42)
    except Exception:
        from sklearn.ensemble import RandomForestClassifier
        model = RandomForestClassifier(n_estimators=300, random_state=42, min_samples_leaf=5)
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    return model, proba


def _evaluate(proba: np.ndarray, y_true: np.ndarray, threshold: float) -> dict:
    pred = (proba >= threshold).astype(int)
    acc = float((pred == y_true).mean()) if len(y_true) else 0.0
    precision = float((pred[y_true == 1] == 1).mean()) if (y_true == 1).any() else 0.0
    coverage = float(pred.mean())
    return {
        "accuracy": round(acc, 4),
        "precision_pos": round(precision, 4),
        "coverage": round(coverage, 4),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Train LightGBM from feature snapshots")
    ap.add_argument("--input", default="", help="CSV labels input (optional)")
    ap.add_argument("--target", default="target_cls", choices=["target_cls", "target_reg"])
    ap.add_argument("--train-ratio", type=float, default=0.7)
    ap.add_argument("--threshold", type=float, default=0.55)
    ap.add_argument("--out", default="data/ml/lgbm_metrics.json")
    args = ap.parse_args(argv)

    df = load_training_data(args.input or None)
    if df is None or df.empty:
        print("لا توجد بيانات تدريب مرتبطة بـ feature_snapshot_id.")
        return 1
    if args.target not in df.columns:
        print(f"الهدف غير موجود: {args.target}")
        return 1

    bundle = build_bundle(df, target=args.target)
    mat = bundle.frame.dropna(subset=[bundle.target])
    if len(mat) < 100:
        print(f"العينة صغيرة جداً: {len(mat)}")
        return 1

    train_idx, test_idx = _split_idx(len(mat), args.train_ratio)
    X = mat[bundle.features].fillna(0.0).to_numpy()
    y = mat[bundle.target].to_numpy()
    if bundle.target == "target_reg":
        y = (y > 0).astype(int)
    else:
        y = y.astype(int)

    model, proba = _fit_predict(X[train_idx], y[train_idx], X[test_idx])
    eval_ml = _evaluate(proba, y[test_idx], args.threshold)
    # baseline ساذج: قبول كل الفرص
    baseline_all = {
        "accuracy": round(float((np.ones_like(y[test_idx]) == y[test_idx]).mean()), 4),
        "precision_pos": round(float(y[test_idx].mean()), 4),
        "coverage": 1.0,
    }

    passed = eval_ml["precision_pos"] > baseline_all["precision_pos"]
    payload = {
        "rows": len(mat),
        "target": args.target,
        "features": bundle.features,
        "ml_oos": eval_ml,
        "baseline_all_oos": baseline_all,
        "pass_gate": bool(passed),
        "gate_rule": "precision_pos أعلى من baseline_all على OOS",
        "model": model.__class__.__name__,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out}")
    print(f"pass_gate={payload['pass_gate']} · ml_precision={eval_ml['precision_pos']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
