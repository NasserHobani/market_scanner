# -*- coding: utf-8 -*-
"""Feature schema registry — metadata for audit and leakage checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

FEATURE_VERSION_V1 = "1.0.0"
FEATURE_VERSION_V2 = "2.0.0"
FEATURE_VERSION_V3 = "3.0.0"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    source: str
    dtype: str
    pre_trade: bool
    leakage_risk: str  # none, low, medium, high
    category: str
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.name,
            "source": self.source,
            "type": self.dtype,
            "pre_trade": self.pre_trade,
            "leakage_risk": self.leakage_risk,
            "category": self.category,
            "description": self.description,
        }


V1_SPECS: list[FeatureSpec] = [
    FeatureSpec("score", "trade.score", "float", True, "none", "recommendation", "Platform score at signal"),
    FeatureSpec("confidence", "trade.confidence", "float", True, "none", "recommendation", "Recommendation confidence"),
    FeatureSpec("rr", "trade.rr", "float", True, "none", "recommendation", "Planned risk/reward"),
    FeatureSpec("grade_enc", "trade.grade", "int", True, "none", "recommendation", "Encoded grade A/B/C"),
    FeatureSpec("factor_htf", "trade.factors", "bool", True, "none", "structure", "HTF factor present"),
    FeatureSpec("factor_confluence", "trade.factors", "bool", True, "none", "structure", "Confluence factor"),
    FeatureSpec("factor_sweep", "trade.factors", "bool", True, "none", "structure", "Sweep factor"),
    FeatureSpec("factor_breakout", "trade.factors", "bool", True, "none", "structure", "Breakout factor"),
    FeatureSpec("market_enc", "trade.market", "int", True, "low", "market", "Market encoding"),
    FeatureSpec("timeframe_enc", "trade.timeframe", "int", True, "none", "market", "Timeframe encoding"),
    FeatureSpec("side_buy", "trade.side", "bool", True, "none", "market", "Buy=1 sell=0"),
]

V2_SPECS: list[FeatureSpec] = [
    *V1_SPECS,
    FeatureSpec("factor_count", "trade.factors", "int", True, "none", "structure", "Count of active factors"),
    FeatureSpec("snap_available", "feature_snapshot", "bool", True, "none", "meta", "Snapshot joined"),
    FeatureSpec("snap_confluence", "feature_snapshot.confluence", "int", True, "none", "structure", "Snapshot confluence"),
    FeatureSpec("snap_htf", "feature_snapshot.htf", "int", True, "none", "trend", "Snapshot HTF bias"),
    FeatureSpec("snap_score", "feature_snapshot.score", "float", True, "none", "recommendation", "Snapshot score"),
    FeatureSpec("snap_quote_volume", "feature_snapshot.quote_volume", "float", True, "none", "volume", "Quote volume"),
    FeatureSpec("liquidity_enc", "feature_snapshot.liquidity", "int", True, "none", "volume", "Liquidity tier"),
    FeatureSpec("hist_win_rate_symbol", "historical.prior_trades", "float", True, "none", "similarity",
                "Prior win rate for symbol (point-in-time)"),
    FeatureSpec("hist_win_rate_tf", "historical.prior_trades", "float", True, "none", "similarity",
                "Prior win rate for timeframe (point-in-time)"),
    FeatureSpec("hist_trade_count_symbol", "historical.prior_trades", "int", True, "none", "similarity",
                "Prior closed trades for symbol"),
    FeatureSpec("hist_expectancy_symbol", "historical.prior_trades", "float", True, "none", "similarity",
                "Prior expectancy for symbol"),
]

V1_COLUMNS = [s.name for s in V1_SPECS]
V2_COLUMNS = [s.name for s in V2_SPECS]

V3_SPECS: list[FeatureSpec] = [
    FeatureSpec("trend_direction", "scanner.scoring.engine", "float", True, "none", "trend", "Trend direction encoding"),
    FeatureSpec("trend_strength", "scanner.scoring.engine", "float", True, "none", "trend", "Normalized trend strength"),
    FeatureSpec("higher_timeframe_trend", "scanner.indicators.htf", "int", True, "none", "trend", "HTF trend bias"),
    FeatureSpec("multi_timeframe_alignment", "scanner.scoring.engine", "float", True, "none", "trend", "MTF alignment"),
    FeatureSpec("rsi", "scanner.indicators.pine", "float", True, "none", "momentum", "RSI at decision"),
    FeatureSpec("momentum_state", "scanner.scoring.engine", "float", True, "none", "momentum", "Momentum component"),
    FeatureSpec("divergence", "scanner.indicators.structure", "float", True, "none", "momentum", "Divergence flag"),
    FeatureSpec("momentum_strength", "scanner.scoring.engine", "float", True, "none", "momentum", "Momentum strength"),
    FeatureSpec("atr_pct", "scanner.indicators.pine", "float", True, "none", "volatility", "ATR percent"),
    FeatureSpec("atr_percentile", "scanner.indicators.pine", "float", True, "none", "volatility", "ATR percentile"),
    FeatureSpec("volatility_regime", "scanner.scoring.engine", "float", True, "none", "volatility", "Vol regime encoding"),
    FeatureSpec("rvol", "scanner.indicators.volume", "float", True, "none", "volume", "Relative volume"),
    FeatureSpec("volume_participation", "scanner.indicators.volume", "float", True, "none", "volume", "Volume participation"),
    FeatureSpec("volume_trend", "scanner.indicators.volume", "float", True, "none", "volume", "Volume trend"),
    FeatureSpec("bos_count", "scanner.indicators.structure", "float", True, "none", "structure", "BOS count"),
    FeatureSpec("choch_count", "scanner.indicators.structure", "float", True, "none", "structure", "CHOCH count"),
    FeatureSpec("structure_direction", "scanner.indicators.structure", "float", True, "none", "structure", "Structure direction"),
    FeatureSpec("support_distance", "scanner.analysis.recommend", "float", True, "none", "structure", "Support distance"),
    FeatureSpec("resistance_distance", "scanner.analysis.recommend", "float", True, "none", "structure", "Resistance distance"),
    FeatureSpec("match_count", "scanner.similarity", "float", True, "none", "similarity", "Similar match count"),
    FeatureSpec("similarity_score", "scanner.similarity", "float", True, "none", "similarity", "Similarity score"),
    FeatureSpec("historical_win_rate", "scanner.similarity", "float", True, "low", "similarity", "Historical win rate"),
    FeatureSpec("historical_expectancy", "scanner.similarity", "float", True, "low", "similarity", "Historical expectancy"),
    FeatureSpec("knowledge_score", "scanner.knowledge", "float", True, "none", "knowledge", "Knowledge score"),
    FeatureSpec("detected_pattern_count", "scanner.knowledge", "float", True, "none", "knowledge", "Pattern count"),
    FeatureSpec("regime", "scanner.knowledge", "float", True, "none", "knowledge", "Regime encoding"),
    FeatureSpec("knowledge_confidence", "scanner.knowledge", "float", True, "none", "knowledge", "Knowledge confidence"),
    FeatureSpec("research_signal", "scanner.research", "float", True, "medium", "research", "Validated research signal"),
    FeatureSpec("research_confidence", "scanner.research", "float", True, "medium", "research", "Research confidence"),
    FeatureSpec("research_sample_size", "scanner.research", "float", True, "medium", "research", "Research sample size"),
    FeatureSpec("score", "scanner.scoring.engine", "float", True, "none", "recommendation", "Platform score"),
    FeatureSpec("confidence", "scanner.analysis.recommend", "float", True, "none", "recommendation", "Reco confidence"),
    FeatureSpec("grade_enc", "scanner.analysis.recommend", "int", True, "none", "recommendation", "Grade encoding"),
    FeatureSpec("risk_reward", "scanner.analysis.recommend", "float", True, "none", "recommendation", "Risk/reward"),
    FeatureSpec("expected_r", "scanner.analysis.recommend", "float", True, "none", "recommendation", "Expected R"),
    FeatureSpec("side_buy", "scanner.analysis.recommend", "bool", True, "none", "recommendation", "Buy side flag"),
]

V3_COLUMNS = [s.name for s in V3_SPECS]


def v3_columns_with_missing() -> list[str]:
    """أعمدة V3 ومعها مؤشّرات الغياب.

    ═══ لماذا عمود للغياب ═══

    ميزةٌ اختيارية غائبة تُكتب ``None`` فيتعامل معها LightGBM
    كقيمة مفقودة. لكنّ **واقعة الغياب** نفسها معلومة: إشارةٌ لا
    سابقة لها ليست كإشارةٍ لها عشرون سابقة، وقد يكون هذا أنفع من
    قيمة السابقة ذاتها.

    فالعمود المؤشّر يجعل الغياب قابلاً للتعلّم صراحةً.
    """
    from scanner.feature_snapshots import tiers

    out = list(V3_COLUMNS)
    for name in tiers.OPTIONAL_FEATURES:
        if name in V3_COLUMNS:
            out.append(f"{name}__missing")
    return out


def specs_for_version(version: str) -> list[FeatureSpec]:
    if version == FEATURE_VERSION_V3:
        return V3_SPECS
    return V2_SPECS if version == FEATURE_VERSION_V2 else V1_SPECS


def columns_for_version(version: str) -> list[str]:
    if version == FEATURE_VERSION_V3:
        return V3_COLUMNS
    return V2_COLUMNS if version == FEATURE_VERSION_V2 else V1_COLUMNS
