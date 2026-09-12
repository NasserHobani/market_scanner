# -*- coding: utf-8 -*-
"""Prediction Dataset V3 — point-in-time snapshots + independent labels."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from scanner.ml.label_store import LabelName
from scanner.tracking import LOST, WON

from .feature_registry import FEATURE_VERSION_V3, V3_COLUMNS, columns_for_version
from .trade_dataset import (
    LEAKAGE_FIELDS,
    _count_reasons,
    _now,
    chronological_split,
    new_dataset_id,
    persist_dataset_manifest,
)


def _label_from_trade(trade: dict[str, Any]) -> dict[str, Any]:
    status = trade.get("status")
    r_mult = trade.get("r_multiple")
    is_win = status in (WON, "won") or (r_mult is not None and float(r_mult) > 0)
    return {
        LabelName.BINARY_WIN.value: 1 if is_win else 0,
        LabelName.R_MULTIPLE.value: float(r_mult) if r_mult is not None else 0.0,
    }


def encode_row_v3(trade: dict[str, Any], *,
                  pit_snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Build one dataset row from trade + point-in-time snapshot."""
    status = trade.get("status")
    if status not in (WON, LOST, "won", "lost"):
        return None
    if not pit_snapshot or not pit_snapshot.get("snapshot_id"):
        return None

    features = dict(pit_snapshot.get("features") or {})
    provenance = pit_snapshot.get("provenance") or []
    if not features or not provenance:
        return None

    labels = _label_from_trade(trade)
    cols = set(V3_COLUMNS)
    clean_feats = {k: float(v) for k, v in features.items() if k in cols}

    # ═══ الغائب يُسجَّل ولا يُحذف ═══
    #
    # حذفُ العمود يجعل صفّاً بلا سابقة تشابه وصفّاً بعشرين سابقة
    # يبدوان سواءً للنموذج. وتعبئتُه بصفر أسوأ: «معدّل فوز
    # المشابهات = 0٪» ادّعاءٌ لم يقله أحد.
    #
    # فيُكتب ``None`` — و‎LightGBM‎ يشقّ عليه شقّاً مستقلاً. ويُرفَع
    # معه عمود مؤشّر ``<name>__missing`` كي يتعلّم النموذج من
    # **واقعة الغياب** نفسها لا من قيمةٍ مفترضة.
    from scanner.feature_snapshots import tiers

    for name in tiers.OPTIONAL_FEATURES:
        if name in cols:
            clean_feats.setdefault(name, None)
            clean_feats[f"{name}__missing"] = float(
                clean_feats.get(name) is None)

    return {
        "trade_id": str(trade.get("trade_id") or ""),
        "event_id": pit_snapshot.get("event_id") or trade.get("event_id") or "",
        "signal_at": str(trade.get("signal_at") or pit_snapshot.get("decision_timestamp") or ""),
        "decision_timestamp": pit_snapshot.get("decision_timestamp", ""),
        "feature_timestamp": pit_snapshot.get("feature_timestamp", ""),
        "features": clean_feats,
        "provenance": provenance,
        "pit_snapshot_id": pit_snapshot.get("snapshot_id", ""),
        **labels,
        "labels": labels,
        "_meta": {
            "symbol": trade.get("symbol"),
            "market": trade.get("market"),
            "timeframe": trade.get("timeframe"),
            "status": trade.get("status"),
            "legacy_snapshot_id": trade.get("feature_snapshot_id") or "",
            "snapshot_status": pit_snapshot.get("status", ""),
            "coverage": pit_snapshot.get("coverage", 0),
        },
    }


def build_dataset_v3(trades: list[dict[str, Any]], *,
                     reconstruct: bool = True,
                     validate_leakage: bool = True) -> dict[str, Any]:
    from scanner.feature_snapshots import tiers
    from scanner.feature_snapshots.historical import batch_reconstruct
    from scanner.feature_snapshots.store import get_by_id, get_by_legacy, load_index

    did = new_dataset_id()
    if reconstruct:
        batch_reconstruct(trades)

    idx = load_index()
    eligible: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []

    for trade in trades:
        fs_id = trade.get("feature_snapshot_id") or ""
        explicit_pit = trade.get("pit_snapshot_id") or ""
        pit_id = explicit_pit or (idx.get("by_legacy") or {}).get(fs_id, "")
        pit = get_by_id(pit_id) if pit_id else None
        if not pit and fs_id:
            pit = get_by_legacy(fs_id)
        # Exclude unreconstructable legacy — do not fabricate
        if pit and getattr(pit, "status", "") == "HISTORICAL_SNAPSHOT_UNAVAILABLE":
            rejected.append({
                "trade_id": str(trade.get("trade_id", "")),
                "reason": "historical_snapshot_unavailable",
            })
            continue
        row = encode_row_v3(trade, pit_snapshot=pit.to_dict() if pit else None)
        if row:
            # ═══ الأهلية على الميزات الأساسية لا على الجميع ═══
            #
            # كان الشرط ``coverage >= 0.70`` على الستّ والثلاثين.
            # وقِيست ٣٣٣٣ لقطة: ١٧٥١ منها عند ‎0.556‎ بالضبط — أي
            # الأساسية وحدها بلا إثراء. فكانت تُرفض جميعاً، لا
            # لأنّ التقاطها فشل بل لأنّه لم توجد صفقاتٌ مشابهة
            # ولا تجربة بحثٍ مصادَقة.
            #
            # وغيابُ «معدّل فوز المشابهات» ليس خللاً بل معلومة:
            # إشارةٌ بلا سابقة تختلف عن إشارةٍ لها عشرون. فتُسجَّل
            # ``None`` ويتعلّم منها النموذج — و‎LightGBM‎ يعالج
            # الغائب أصلاً.
            feats = (pit.to_dict().get("features") or {}) if pit else {}
            core_cov = tiers.core_coverage(feats)
            if core_cov < tiers.CORE_MIN_COVERAGE:
                rejected.append({
                    "trade_id": str(trade.get("trade_id", "")),
                    "reason": "low_core_coverage",
                    "missing": ",".join(tiers.missing_core(feats)[:5]),
                })
                continue
            viols = []
            if validate_leakage:
                from .leakage_detector import validate_row_features, validate_provenance
                viols = validate_row_features(row, feature_columns=V3_COLUMNS,
                                              decision_ts=row.get("decision_timestamp", ""))
                viols.extend(validate_provenance(row.get("provenance") or [],
                                                 decision_ts=row.get("decision_timestamp", "")))
            if viols:
                rejected.append({
                    "trade_id": str(trade.get("trade_id", "")),
                    "reason": "leakage:" + ";".join(viols[:3]),
                })
            else:
                eligible.append(row)
        else:
            reason = "no_pit_snapshot" if (fs_id or explicit_pit) else "historical_snapshot_unavailable"
            rejected.append({"trade_id": str(trade.get("trade_id", "?")), "reason": reason})

    eligible.sort(key=lambda r: r.get("signal_at") or "")

    leakage_report = {"passed": True, "rows_checked": len(eligible)}
    if validate_leakage and eligible:
        from .leakage_detector import validate_dataset
        leakage_report = validate_dataset(
            eligible, feature_version=FEATURE_VERSION_V3, fail_loud=False)

    cols = columns_for_version(FEATURE_VERSION_V3)
    symbols = sorted({r["_meta"]["symbol"] for r in eligible if r["_meta"].get("symbol")})
    timeframes = sorted({r["_meta"]["timeframe"] for r in eligible if r["_meta"].get("timeframe")})
    dates = [r["signal_at"][:10] for r in eligible if r.get("signal_at")]
    date_range = {"start": dates[0], "end": dates[-1]} if dates else {}

    schema_hash = hashlib.sha256(json.dumps(cols, sort_keys=True).encode()).hexdigest()[:16]
    fingerprint = hashlib.sha256(
        json.dumps(
            [{"t": r["trade_id"], "s": r["signal_at"], "p": r.get("pit_snapshot_id")} for r in eligible],
            sort_keys=True,
        ).encode(),
    ).hexdigest()[:24]

    wins = sum(1 for r in eligible if r.get(LabelName.BINARY_WIN.value) == 1)
    label_dist = {
        "wins": wins,
        "losses": len(eligible) - wins,
        "win_rate": round(wins / len(eligible), 4) if eligible else 0.0,
    }

    manifest = {
        "dataset_id": did,
        "dataset_version": FEATURE_VERSION_V3,
        "created_at": _now(),
        "feature_schema": {
            "columns": cols,
            "feature_version": FEATURE_VERSION_V3,
            "feature_schema_hash": f"fsh_{schema_hash}",
            "leakage_excluded": sorted(LEAKAGE_FIELDS),
            "source": "point_in_time_snapshots",
        },
        "label_definition": {
            "primary": LabelName.BINARY_WIN.value,
            "description": "Independent outcome label — never in feature columns",
            "deterministic": True,
        },
        "leakage_validation": leakage_report,
        "row_count": len(eligible),
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "sample_count": len(eligible),
        "rejection_reasons": _count_reasons(rejected),
        "symbols": symbols,
        "timeframes": timeframes,
        "date_range": date_range,
        "label_distribution": label_dist,
        "fingerprint": f"dsfp_{fingerprint}",
        "rows": eligible,
    }
    return manifest


def dataset_v3_quality(manifest: dict[str, Any]) -> dict[str, Any]:
    from .dataset_quality import dataset_quality_report
    from .feature_audit import audit_features_v3

    base = dataset_quality_report(manifest)
    audit = audit_features_v3(manifest.get("rows") or [])
    rows = manifest.get("rows") or []
    symbols = [r["_meta"].get("symbol") for r in rows if r.get("_meta")]
    concentration_warning = False
    if symbols:
        from collections import Counter
        top_sym, top_n = Counter(symbols).most_common(1)[0]
        if top_n / len(symbols) >= 0.9:
            concentration_warning = True
            base["concentration"] = {
                "warning": "DATASET_CONCENTRATION_WARNING",
                "symbol": top_sym,
                "pct": round(top_n / len(symbols) * 100, 1),
            }

    dupes = len(rows) - len({r["trade_id"] for r in rows})
    return {
        **base,
        "feature_audit": audit,
        "duplicate_rows": dupes,
        "concentration_warning": concentration_warning,
        "snapshot_coverage": round(
            sum(1 for r in rows if r.get("pit_snapshot_id")) / len(rows), 4
        ) if rows else 0.0,
    }


def run_v3_experiment(manifest: dict[str, Any]) -> dict[str, Any]:
    """Compare baselines + LightGBM V3 with walk-forward validation."""
    from .baselines import run_all_baselines
    from .feature_registry import FEATURE_VERSION_V3, columns_for_version
    from .model_evaluation import walk_forward_report
    from .predictive_engine import PredictiveEngine, ValidationMode
    from .quality_gates import evaluate_promotion, naive_baseline_metrics
    from .trainer import Trainer, TrainingConfig
    from .trade_dataset import chronological_split
    from scanner.ml.label_store import LabelName

    rows = manifest.get("rows") or []
    if len(rows) < 20:
        return {"status": "INSUFFICIENT_DATA", "row_count": len(rows)}

    splits = chronological_split(rows)
    test_rows = splits["test"] or splits["validation"] or rows[-10:]
    train_rows = splits["train"] or rows[:-10]
    naive = naive_baseline_metrics(test_rows)
    baselines = run_all_baselines(test_rows)

    feature_cols = columns_for_version(FEATURE_VERSION_V3)
    cfg = TrainingConfig(
        feature_columns=feature_cols,
        label_column=LabelName.BINARY_WIN.value,
        feature_version=FEATURE_VERSION_V3,
        dataset_id=manifest.get("dataset_id", ""),
    )

    model_eval: dict[str, Any] = {}
    wf_dict: dict[str, Any] = {}
    cal: dict[str, Any] = {}
    try:
        engine = PredictiveEngine()
        wf = engine.walk_forward(
            rows, cfg, mode=ValidationMode.WALK_FORWARD.value,
            train_size=max(15, len(rows) // 4), test_size=max(5, len(rows) // 10),
        )
        wf_dict = wf.to_dict()
        from .plugins.lightgbm import LightGBMPlugin
        trainer = Trainer(plugins={"lightgbm": LightGBMPlugin})
        artifact = trainer.train(train_rows, cfg)
        X_test, y_test, r_mults = Trainer._extract(test_rows, cfg)
        preds = artifact.model.predict(X_test, feature_names=feature_cols)
        proba = artifact.model.predict_proba(X_test, feature_names=feature_cols)
        from .evaluator import Evaluator
        model_eval = Evaluator().evaluate(
            y_true=[float(v) for v in y_test],
            y_pred=preds,
            y_proba=proba,
            r_multiples=r_mults,
            task_type="classification",
        )
        from .calibration import calibration_report
        cal = calibration_report([int(v) for v in y_test], proba)
    except Exception as exc:  # noqa: BLE001
        model_eval = {"error": str(exc)[:200], "classification": naive.get("classification", {})}

    gate = evaluate_promotion(
        test_metrics=model_eval,
        baseline_metrics=naive,
        walk_forward=wf_dict,
        calibration=cal,
    )
    return {
        "baselines": baselines,
        "naive_baseline": naive,
        "v3_test": model_eval,
        "walk_forward": walk_forward_report(wf_dict),
        "calibration": cal,
        "quality_gate": gate,
        "split_counts": {k: len(v) for k, v in splits.items()},
    }
