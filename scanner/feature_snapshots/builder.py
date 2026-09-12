# -*- coding: utf-8 -*-
"""Build point-in-time snapshots from scan/recommendation data."""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from . import tiers
from .contract import (
    FEATURE_SCHEMA_VERSION_V3,
    SNAPSHOT_VERSION_V3,
    FeatureProvenance,
    PointInTimeSnapshot,
    SnapshotQualityStatus,
    SnapshotStatus,
    _now,
)

log = logging.getLogger("scanner.feature_snapshots.builder")

V3_FEATURE_SPECS: list[tuple[str, str, str]] = [
    # name, source module, calc version
    ("trend_direction", "scanner.scoring.engine", "trend-v1"),
    ("trend_strength", "scanner.scoring.engine", "trend-v1"),
    ("higher_timeframe_trend", "scanner.indicators.htf", "htf-v1"),
    ("multi_timeframe_alignment", "scanner.scoring.engine", "mtf-v1"),
    ("rsi", "scanner.indicators.pine", "rsi-v2"),
    ("momentum_state", "scanner.indicators.pine", "mom-v1"),
    ("divergence", "scanner.indicators.structure", "div-v1"),
    ("momentum_strength", "scanner.scoring.engine", "mom-v1"),
    ("atr_pct", "scanner.indicators.pine", "atr-v1"),
    ("atr_percentile", "scanner.indicators.pine", "atr-v1"),
    ("volatility_regime", "scanner.scoring.engine", "vol-v1"),
    ("rvol", "scanner.indicators.volume", "rvol-v1"),
    ("volume_participation", "scanner.indicators.volume", "vol-v1"),
    ("volume_trend", "scanner.indicators.volume", "vol-v1"),
    ("bos_count", "scanner.indicators.structure", "struct-v1"),
    ("choch_count", "scanner.indicators.structure", "struct-v1"),
    ("structure_direction", "scanner.indicators.structure", "struct-v1"),
    ("support_distance", "scanner.analysis.recommend", "sr-v1"),
    ("resistance_distance", "scanner.analysis.recommend", "sr-v1"),
    ("match_count", "scanner.similarity", "sim-v1"),
    ("similarity_score", "scanner.similarity", "sim-v1"),
    ("historical_win_rate", "scanner.similarity", "sim-v1"),
    ("historical_expectancy", "scanner.similarity", "sim-v1"),
    ("knowledge_score", "scanner.knowledge", "know-v1"),
    ("detected_pattern_count", "scanner.knowledge", "pat-v1"),
    ("regime", "scanner.knowledge", "regime-v1"),
    ("knowledge_confidence", "scanner.knowledge", "know-v1"),
    ("research_signal", "scanner.research", "res-v1"),
    ("research_confidence", "scanner.research", "res-v1"),
    ("research_sample_size", "scanner.research", "res-v1"),
    ("score", "scanner.scoring.engine", "score-v1"),
    ("confidence", "scanner.analysis.recommend", "reco-v1"),
    ("grade_enc", "scanner.analysis.recommend", "reco-v1"),
    ("risk_reward", "scanner.analysis.recommend", "reco-v1"),
    ("expected_r", "scanner.analysis.recommend", "reco-v1"),
    ("side_buy", "scanner.analysis.recommend", "reco-v1"),
]

GRADE_MAP = {"A": 3, "B": 2, "C": 1, "—": 0, "-": 0, "": 0}


def _snap_id(payload: dict[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:20]
    return f"pit_{digest}"


def _f(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _enc_trend(htf: int | None, trend_comp: int | None) -> float:
    if htf == 1 or trend_comp == 1:
        return 1.0
    if htf == -1 or trend_comp == -1:
        return -1.0
    return 0.0


def _first_present(*vals: Any) -> Any:
    """Return first value that is not None (0 and False are valid)."""
    for v in vals:
        if v is not None:
            return v
    return None


def extract_v3_features(source: dict[str, Any], *,
                        decision_ts: str,
                        similarity: dict[str, Any] | None = None,
                        research: dict[str, Any] | None = None,
                        knowledge: dict[str, Any] | None = None) -> tuple[dict[str, float], list[FeatureProvenance]]:
    """Extract V3 numeric features with provenance — only from provided source."""
    components = dict(source.get("components") or {})
    ctx = dict(source.get("context") or source.get("score_context") or {})
    reco = dict(source.get("recommendation") or source.get("reco") or {})
    analysis = dict(reco.get("analysis") or source.get("analysis") or {})
    pa = dict(analysis.get("price_action") or {})
    structure = dict(source.get("structure") or {})
    extra = dict(source.get("features") or source.get("extra_features") or {})
    sim = similarity or source.get("enriched_similarity") or {}
    res = research or source.get("enriched_research") or {}
    kctx = knowledge or source.get("knowledge_context") or {}

    feats: dict[str, float] = {}
    prov: list[FeatureProvenance] = []
    missing_detail: dict[str, str] = {}

    def add(name: str, value: Any, source_name: str, calc_ver: str) -> None:
        if value is None:
            return
        fv = _f(value) if not isinstance(value, (str, bool)) else (1.0 if value else 0.0)
        if isinstance(value, str) and name not in ("regime",):
            return
        feats[name] = fv
        prov.append(FeatureProvenance(
            name=name, value=fv, source=source_name,
            source_timestamp=decision_ts, calculation_version=calc_ver,
        ))

    def mark_missing(name: str, reason: str) -> None:
        if name not in feats:
            missing_detail[name] = reason

    htf = source.get("htf")
    trend_comp = components.get("trend")
    add("trend_direction", _enc_trend(htf, trend_comp), "scanner.scoring.engine", "trend-v1")
    if source.get("score") is not None:
        add("trend_strength", abs(_f(source.get("score")) / 100.0), "scanner.scoring.engine", "trend-v1")
    else:
        mark_missing("trend_strength", "missing_trend")
    add("higher_timeframe_trend", htf, "scanner.indicators.htf", "htf-v1")
    if htf is not None and trend_comp is not None:
        add("multi_timeframe_alignment",
            1.0 if int(htf) == int(trend_comp) else 0.0,
            "scanner.scoring.engine", "mtf-v1")
    else:
        mark_missing("multi_timeframe_alignment", "missing_components")

    rsi = _first_present(extra.get("rsi"), ctx.get("rsi"), source.get("rsi"))
    add("rsi", rsi, "scanner.indicators.pine", "rsi-v2")
    if rsi is None:
        mark_missing("rsi", "missing_rsi")
    mom = _first_present(components.get("rsi"), components.get("obv_macd"))
    add("momentum_state", mom, "scanner.scoring.engine", "mom-v1")
    if mom is None:
        mark_missing("momentum_state", "missing_momentum")
    div_sig = components.get("div")
    if div_sig is None:
        div_sig = components.get("divergence")
    if div_sig is not None or pa.get("divergence") is not None:
        add("divergence", 1.0 if (div_sig or pa.get("divergence")) else 0.0,
            "scanner.indicators.structure", "div-v1")
    else:
        mark_missing("divergence", "missing_momentum")
    if components.get("rsi") is not None:
        add("momentum_strength", abs(_f(components.get("rsi"))), "scanner.scoring.engine", "mom-v1")
    else:
        mark_missing("momentum_strength", "missing_momentum")

    atr = _first_present(extra.get("atr_pct"), ctx.get("atr_pct"), source.get("atr_pct"))
    add("atr_pct", atr, "scanner.indicators.pine", "atr-v1")
    if atr is None:
        mark_missing("atr_pct", "missing_atr")
    atr_pctile = ctx.get("atr_percentile")
    add("atr_percentile", atr_pctile, "scanner.indicators.pine", "atr-v1")
    if atr_pctile is None:
        mark_missing("atr_percentile", "missing_atr")

    vol = str(ctx.get("volatility") or "").lower()
    channel = str(ctx.get("channel") or "").strip()
    ch_zone = str(ctx.get("ch_zone") or "").strip()
    real_channel = channel not in ("", "—", "-", "none", "None")
    if vol or real_channel:
        ch_l = channel.lower()
        if "high" in vol or "مرتفع" in vol or ch_l in ("falling", "هابط"):
            vol_enc = 2.0
        elif "low" in vol or ch_l in ("rising", "صاعد"):
            vol_enc = 0.0
        elif ch_zone in ("buy", "sell") or ch_l in ("flat",):
            vol_enc = 1.0
        else:
            vol_enc = 1.0
        add("volatility_regime", vol_enc, "scanner.scoring.engine", "vol-v1")
    else:
        mark_missing("volatility_regime", "missing_volatility")

    rvol = _first_present(extra.get("rvol"), ctx.get("rvol"), source.get("rvol"))
    add("rvol", rvol, "scanner.indicators.volume", "rvol-v1")
    if rvol is None:
        mark_missing("rvol", "missing_rvol")
    # components has no "volume" key — reuse existing volume factor signals
    vol_part = _first_present(
        components.get("volume"),
        components.get("spike"),
        components.get("cmf"),
        components.get("mfi"),
    )
    add("volume_participation", vol_part, "scanner.indicators.volume", "vol-v1")
    if vol_part is None:
        mark_missing("volume_participation", "missing_volume")
    add("volume_trend", components.get("obv_macd"), "scanner.indicators.volume", "vol-v1")
    if components.get("obv_macd") is None:
        mark_missing("volume_trend", "missing_volume")

    bos = _first_present(structure.get("bos_count"), pa.get("bos_count"), pa.get("bos"))
    choch = _first_present(structure.get("choch_count"), pa.get("choch_count"), pa.get("choch"))
    if bos is not None:
        add("bos_count", bos, "scanner.indicators.structure", "struct-v1")
    else:
        mark_missing("bos_count", "missing_structure")
    if choch is not None:
        add("choch_count", choch, "scanner.indicators.structure", "struct-v1")
    else:
        mark_missing("choch_count", "missing_structure")
    struct_dir = (structure.get("structure_direction")
                  or pa.get("trend") or pa.get("structure"))
    if struct_dir in ("bullish", "bearish", "up", "down"):
        add("structure_direction", 1.0 if struct_dir in ("bullish", "up") else -1.0,
            "scanner.indicators.structure", "struct-v1")
    else:
        mark_missing("structure_direction", "missing_structure")
    support = _first_present(
        structure.get("support_distance"), pa.get("support_distance"), analysis.get("support_distance"),
    )
    resist = _first_present(
        structure.get("resistance_distance"), pa.get("resistance_distance"),
        analysis.get("resistance_distance"),
    )
    add("support_distance", support, "scanner.analysis.recommend", "sr-v1")
    add("resistance_distance", resist, "scanner.analysis.recommend", "sr-v1")
    if support is None:
        mark_missing("support_distance", "missing_structure")
    if resist is None:
        mark_missing("resistance_distance", "missing_structure")

    if sim.get("similarity_status") == "unavailable":
        for n in ("match_count", "similarity_score", "historical_win_rate", "historical_expectancy"):
            mark_missing(n, "missing_similarity")
    else:
        add("match_count", _first_present(sim.get("match_count"), sim.get("historical_matches")),
            "scanner.similarity", "sim-v1")
        add("similarity_score",
            _first_present(sim.get("average_similarity"), sim.get("confidence")),
            "scanner.similarity", "sim-v1")
        add("historical_win_rate",
            _first_present(sim.get("average_win_rate"), sim.get("win_rate")),
            "scanner.similarity", "sim-v1")
        add("historical_expectancy",
            _first_present(sim.get("average_r"), sim.get("expectancy")),
            "scanner.similarity", "sim-v1")
        for n in ("match_count", "similarity_score", "historical_win_rate", "historical_expectancy"):
            if n not in feats:
                mark_missing(n, "missing_similarity")

    feat_snap = kctx.get("feature_snapshot") or {}
    groups = feat_snap.get("groups") or {}
    ks = feat_snap.get("final_score")
    if ks is not None:
        add("knowledge_score", ks, "scanner.knowledge", "know-v1")
    elif kctx and source.get("score") is not None:
        add("knowledge_score", source.get("score"), "scanner.knowledge", "know-v1")
    else:
        mark_missing("knowledge_score", "missing_knowledge")
    if kctx or groups:
        patterns = groups.get("patterns") or {}
        add("detected_pattern_count", len(patterns) if isinstance(patterns, dict) else 0,
            "scanner.knowledge", "pat-v1")
    else:
        mark_missing("detected_pattern_count", "missing_knowledge")
    regime = (kctx.get("market_environment") or {}).get("regime") or ctx.get("regime")
    if regime:
        add("regime", hash(str(regime)) % 1000 / 1000.0, "scanner.knowledge", "regime-v1")
    else:
        mark_missing("regime", "missing_knowledge")
    kconf = _first_present(
        kctx.get("knowledge_confidence"),
        (kctx.get("recommendation_snapshot") or {}).get("confidence"),
        reco.get("confidence"),
        feat_snap.get("confidence"),
    )
    add("knowledge_confidence", kconf, "scanner.knowledge", "know-v1")
    if kconf is None:
        mark_missing("knowledge_confidence", "missing_knowledge")

    stats = res.get("statistics") or {}
    if res.get("available") and stats:
        add("research_signal", 1.0 if stats.get("significant") else 0.0, "scanner.research", "res-v1")
        add("research_confidence", res.get("confidence") or stats.get("confidence"),
            "scanner.research", "res-v1")
        add("research_sample_size", stats.get("sample_size") or res.get("row_count"),
            "scanner.research", "res-v1")
    else:
        for n in ("research_signal", "research_confidence", "research_sample_size"):
            mark_missing(n, "missing_research")

    add("score", source.get("score"), "scanner.scoring.engine", "score-v1")
    if source.get("score") is None:
        mark_missing("score", "missing_platform_score")
    add("confidence", reco.get("confidence"), "scanner.analysis.recommend", "reco-v1")
    if reco.get("confidence") is None:
        mark_missing("confidence", "missing_recommendation")
    if reco.get("grade") is not None or source.get("grade") is not None:
        add("grade_enc", GRADE_MAP.get(str(reco.get("grade") or source.get("grade") or "—"), 0),
            "scanner.analysis.recommend", "reco-v1")
    else:
        mark_missing("grade_enc", "missing_recommendation")
    add("risk_reward", reco.get("rr"), "scanner.analysis.recommend", "reco-v1")
    add("expected_r", reco.get("rr"), "scanner.analysis.recommend", "reco-v1")
    if reco.get("rr") is None:
        mark_missing("risk_reward", "missing_recommendation")
        mark_missing("expected_r", "missing_recommendation")
    side_raw = reco.get("side")
    if side_raw is not None and str(side_raw).strip() != "":
        side = str(side_raw).lower()
        add("side_buy", 1.0 if side == "buy" else 0.0, "scanner.analysis.recommend", "reco-v1")
    else:
        mark_missing("side_buy", "missing_recommendation")

    # Stash missing detail on source for callers that read it
    source["_missing_feature_reasons"] = missing_detail
    return feats, prov


def build_snapshot(source: dict[str, Any], *,
                   legacy_snapshot_id: str = "",
                   similarity: dict[str, Any] | None = None,
                   research: dict[str, Any] | None = None,
                   knowledge: dict[str, Any] | None = None,
                   status: str = SnapshotStatus.CREATED.value) -> PointInTimeSnapshot:
    symbol = source.get("symbol", "")
    market = source.get("market", "")
    timeframe = source.get("timeframe", "")
    decision_ts = str(
        source.get("decision_timestamp")
        or source.get("candle_time")
        or source.get("timestamp")
        or _now()
    )
    feature_ts = str(source.get("feature_timestamp") or decision_ts)

    if feature_ts > decision_ts:
        return PointInTimeSnapshot(
            snapshot_id="",
            symbol=symbol, timeframe=timeframe, market=market,
            decision_timestamp=decision_ts, feature_timestamp=feature_ts,
            status=SnapshotStatus.REJECTED.value,
            quality_status=SnapshotQualityStatus.FAILED.value,
            failure_reason="feature_timestamp > decision_timestamp",
            created_at=_now(),
        )

    try:
        feats, prov = extract_v3_features(
            source, decision_ts=decision_ts,
            similarity=similarity, research=research, knowledge=knowledge,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("snapshot build failed %s: %s", symbol, str(exc)[:120])
        return PointInTimeSnapshot(
            snapshot_id="",
            symbol=symbol, timeframe=timeframe, market=market,
            decision_timestamp=decision_ts, feature_timestamp=feature_ts,
            status=SnapshotStatus.FAILED.value,
            quality_status=SnapshotQualityStatus.FAILED.value,
            failure_reason=str(exc)[:200],
            created_at=_now(),
        )

    expected = len(V3_FEATURE_SPECS)
    # التغطية الكلّية تبقى للشفافية — لا تُحذف ولا تُجمَّل
    coverage = round(len(feats) / expected, 4) if expected else 0.0

    # ═══ الجودة على الأساسية وحدها ═══
    #
    # كانت على الستّ والثلاثين جميعاً، فبلغ أعلى ما سُجّل ‎0.861‎
    # على ٣٣٣٣ لقطة — لأنّ خمس ميزات لا تُحسب أبداً. أي أنّ حدّ
    # «جيّدة» (‎0.90‎) كان غير قابل للبلوغ بنيوياً، وعدد الجيّدات
    # صفراً لا لعطبٍ في الالتقاط.
    #
    # والقياس الآن على ما **يجب** أن يُحسب من السعر والحجم: ثماني
    # عشرة ميزة حضورها المقيس ٨٩–١٠٠٪. وغياب الاختيارية يُسجَّل
    # في ``optional_gaps`` ولا يُحاسَب جودةً.
    core_cov = tiers.core_coverage(feats)
    quality = SnapshotQualityStatus.GOOD.value
    snap_status = status
    if core_cov < 0.70:
        quality = SnapshotQualityStatus.FAILED.value
        snap_status = SnapshotStatus.FAILED.value if status == SnapshotStatus.CREATED.value else status
    elif core_cov < tiers.CORE_MIN_COVERAGE:
        quality = SnapshotQualityStatus.PARTIAL.value
        snap_status = SnapshotStatus.PARTIAL.value if status == SnapshotStatus.CREATED.value else status

    payload = {
        "symbol": symbol, "market": market, "timeframe": timeframe,
        "decision_timestamp": decision_ts, "features": feats,
    }
    sid = _snap_id(payload)

    try:
        from scanner.knowledge.snapshot_builder import make_event_id
        event_id = make_event_id(
            symbol=symbol, market=market, timeframe=timeframe, candle_time=decision_ts)
    except Exception:  # noqa: BLE001
        event_id = source.get("event_id", "")

    missing_reasons = dict(source.get("_missing_feature_reasons") or {})
    missing_names = [name for name, _, _ in V3_FEATURE_SPECS if name not in feats]
    for name in missing_names:
        missing_reasons.setdefault(name, f"missing_{name}")
    # Inline category tally — avoid circular import with enrichment
    from .enrichment import FEATURE_CATEGORIES
    mbc = {
        cat: sum(1 for name in names if name in set(missing_names))
        for cat, names in FEATURE_CATEGORIES.items()
    }

    return PointInTimeSnapshot(
        snapshot_id=sid,
        symbol=symbol,
        timeframe=timeframe,
        market=market,
        strategy_id=source.get("strategy_id", "default"),
        recommendation_id=source.get("recommendation_id", legacy_snapshot_id),
        decision_timestamp=decision_ts,
        feature_timestamp=feature_ts,
        snapshot_version=SNAPSHOT_VERSION_V3,
        feature_schema_version=FEATURE_SCHEMA_VERSION_V3,
        source_versions={
            "scoring": "1.0",
            "knowledge": "2.0",
            "snapshot": SNAPSHOT_VERSION_V3,
        },
        features=feats,
        provenance=prov,
        coverage=coverage,
        quality_status=quality,
        status=snap_status,
        legacy_snapshot_id=legacy_snapshot_id,
        event_id=event_id,
        created_at=_now(),
        missing_features=missing_names,
        missing_by_category=mbc,
        missing_feature_reasons=missing_reasons,
        failure_reasons=sorted(set(missing_reasons.values())),
    )
