# -*- coding: utf-8 -*-
"""Convert knowledge payloads into structured evidence — no new indicators."""
from __future__ import annotations

from typing import Any

from .evidence import (
    Evidence,
    EvidenceBundle,
    EvidenceCategory,
    EvidenceDirection,
    EvidenceStrength,
)


def _strength_from_score(score: float) -> str:
    if score >= 0.75:
        return EvidenceStrength.STRONG.value
    if score >= 0.45:
        return EvidenceStrength.MODERATE.value
    if score > 0:
        return EvidenceStrength.WEAK.value
    return EvidenceStrength.UNKNOWN.value


def _sign_direction(signal: int | None, trade_side: str) -> str:
    """Map signed component to supports/contradicts for trade side."""
    if signal is None or signal == 0:
        return EvidenceDirection.NEUTRAL.value
    bullish = trade_side in ("buy", "long")
    if bullish:
        return (EvidenceDirection.SUPPORTS.value if signal > 0
                else EvidenceDirection.CONTRADICTS.value)
    return (EvidenceDirection.SUPPORTS.value if signal < 0
            else EvidenceDirection.CONTRADICTS.value)


def _trade_side(ctx: dict[str, Any]) -> str:
    reco = ctx.get("recommendation_snapshot") or {}
    return (reco.get("direction") or reco.get("side") or "buy").lower()


def _ev_id(category: str, key: str) -> str:
    return f"ev_{category}_{key}"


class EvidenceEngine:
    """Builds EvidenceBundle from a knowledge context dict."""

    def build(self, context: dict[str, Any]) -> EvidenceBundle:
        event_id = context.get("event_id") or ""
        side = _trade_side(context)
        items: list[Evidence] = []

        items.extend(self._from_market(context, side))
        items.extend(self._from_environment(context, side))
        items.extend(self._from_features(context, side))
        items.extend(self._from_history(context, side))
        items.extend(self._from_recommendation(context))

        return EvidenceBundle(items=items, event_id=event_id)

    def _from_market(self, ctx: dict[str, Any], side: str) -> list[Evidence]:
        market = ctx.get("market_snapshot") or {}
        if not market:
            return [Evidence(
                evidence_id=_ev_id("trend", "missing"),
                label="Market snapshot unavailable",
                category=EvidenceCategory.TREND.value,
                direction=EvidenceDirection.MISSING.value,
                weight=0.0, strength=EvidenceStrength.UNKNOWN.value,
                confidence=0.0, source="market_snapshot",
            )]

        trend = (market.get("trend_direction") or "").lower()
        htf = market.get("htf_bias")
        bullish = trend == "bullish" or htf == 1
        bearish = trend == "bearish" or htf == -1
        wants_bull = side in ("buy", "long")

        if bullish:
            direction = (EvidenceDirection.SUPPORTS.value if wants_bull
                         else EvidenceDirection.CONTRADICTS.value)
            label = "Bullish Trend Evidence"
        elif bearish:
            direction = (EvidenceDirection.SUPPORTS.value if not wants_bull
                         else EvidenceDirection.CONTRADICTS.value)
            label = "Bearish Trend Evidence"
        else:
            direction = EvidenceDirection.NEUTRAL.value
            label = "Neutral Trend Evidence"

        conf = 0.7 if (bullish or bearish) else 0.3
        return [Evidence(
            evidence_id=_ev_id("trend", "direction"),
            label=label,
            category=EvidenceCategory.TREND.value,
            direction=direction,
            weight=0.30,
            strength=_strength_from_score(conf),
            confidence=conf,
            source="market_snapshot",
            facts=(f"trend_direction={trend}", f"htf_bias={htf}"),
            trace="market_snapshot.trend_direction + htf_bias",
            raw_key="trend_direction",
        )]

    def _from_environment(self, ctx: dict[str, Any], side: str) -> list[Evidence]:
        env = ctx.get("market_environment") or {}
        if not env:
            return []

        regime = env.get("market_regime") or ""
        score = env.get("market_breadth")
        trend_state = env.get("trend_state") or ""
        wants_bull = side in ("buy", "long")

        direction = EvidenceDirection.NEUTRAL.value
        if env.get("regime_score") == 1 or "صاعد" in regime:
            direction = (EvidenceDirection.SUPPORTS.value if wants_bull
                           else EvidenceDirection.CONTRADICTS.value)
        elif env.get("regime_score") == -1 or "هابط" in regime:
            direction = (EvidenceDirection.SUPPORTS.value if not wants_bull
                         else EvidenceDirection.CONTRADICTS.value)

        conf = 0.6 if regime else 0.2
        if score is not None and score >= 55:
            conf = min(0.9, conf + 0.1)

        return [Evidence(
            evidence_id=_ev_id("regime", "environment"),
            label=f"Market Regime: {regime or trend_state or 'unknown'}",
            category=EvidenceCategory.REGIME.value,
            direction=direction,
            weight=0.15,
            strength=_strength_from_score(conf),
            confidence=conf,
            source="market_environment",
            facts=(f"regime={regime}", f"breadth={score}", f"trend_state={trend_state}"),
            trace="market_environment.market_regime",
            raw_key="market_regime",
        )]

    def _from_features(self, ctx: dict[str, Any], side: str) -> list[Evidence]:
        features = ctx.get("feature_snapshot") or {}
        if not features:
            return []

        groups = features.get("groups") or {}
        components = features.get("raw_components") or {}
        out: list[Evidence] = []

        # Liquidity
        liq = groups.get("liquidity") or {}
        liq_class = liq.get("class") or "unknown"
        sweeps = liq.get("sweeps") or []
        liq_conf = 0.8 if liq_class in ("high", "mid") else 0.4
        out.append(Evidence(
            evidence_id=_ev_id("liquidity", "class"),
            label=f"Liquidity Class: {liq_class}",
            category=EvidenceCategory.LIQUIDITY.value,
            direction=(EvidenceDirection.SUPPORTS.value
                         if liq_class in ("high", "mid")
                         else EvidenceDirection.NEUTRAL.value),
            weight=0.20,
            strength=_strength_from_score(liq_conf),
            confidence=liq_conf,
            source="feature_snapshot.groups.liquidity",
            facts=(f"class={liq_class}", f"sweeps={len(sweeps)}"),
            trace="feature_snapshot.groups.liquidity",
            raw_key="liquidity.class",
        ))

        # Volume
        vol = groups.get("volume") or {}
        rvol = vol.get("rvol")
        spike = vol.get("spike_signal") or components.get("spike", 0)
        vol_conf = 0.5
        if rvol is not None:
            vol_conf = min(0.9, 0.4 + float(rvol) * 0.2)
        out.append(Evidence(
            evidence_id=_ev_id("volume", "participation"),
            label="Volume Participation Evidence",
            category=EvidenceCategory.VOLUME.value,
            direction=_sign_direction(int(spike) if spike else None, side),
            weight=0.15,
            strength=_strength_from_score(vol_conf),
            confidence=vol_conf,
            source="feature_snapshot.groups.volume",
            facts=(f"rvol={rvol}", f"spike_signal={spike}"),
            trace="feature_snapshot.groups.volume.rvol",
            raw_key="rvol",
        ))

        # Structure
        struct = groups.get("market_structure") or {}
        bos = struct.get("bos") or []
        choch = struct.get("choch") or []
        struct_conf = 0.7 if bos else 0.35
        struct_dir = EvidenceDirection.NEUTRAL.value
        if bos and not choch:
            struct_dir = EvidenceDirection.SUPPORTS.value
        elif choch:
            struct_dir = EvidenceDirection.CONTRADICTS.value
        out.append(Evidence(
            evidence_id=_ev_id("structure", "events"),
            label="Market Structure Evidence",
            category=EvidenceCategory.STRUCTURE.value,
            direction=struct_dir,
            weight=0.20,
            strength=_strength_from_score(struct_conf),
            confidence=struct_conf,
            source="feature_snapshot.groups.market_structure",
            facts=(f"bos_count={len(bos)}", f"choch_count={len(choch)}"),
            trace="feature_snapshot.groups.market_structure",
            raw_key="market_structure",
        ))

        # Momentum
        mom = groups.get("momentum") or {}
        rsi_sig = components.get("rsi") or mom.get("rsi_signal")
        div_sig = components.get("div")
        mom_conf = 0.55
        mom_dir = _sign_direction(int(rsi_sig) if rsi_sig is not None else None, side)
        if div_sig is not None and int(div_sig) != 0:
            div_dir = _sign_direction(int(div_sig), side)
            if div_dir == EvidenceDirection.CONTRADICTS.value:
                mom_dir = EvidenceDirection.CONTRADICTS.value
                mom_conf = 0.65
        out.append(Evidence(
            evidence_id=_ev_id("momentum", "rsi_div"),
            label="Momentum Evidence",
            category=EvidenceCategory.MOMENTUM.value,
            direction=mom_dir,
            weight=0.10,
            strength=_strength_from_score(mom_conf),
            confidence=mom_conf,
            source="feature_snapshot.groups.momentum",
            facts=(f"rsi_signal={rsi_sig}", f"divergence_signal={div_sig}"),
            trace="feature_snapshot.raw_components.rsi + div",
            raw_key="momentum",
        ))

        # Confluence
        conf_g = groups.get("confluence") or {}
        reasons = conf_g.get("reasons") or []
        count = conf_g.get("count") or len(reasons)
        conf_score = min(0.95, 0.3 + int(count or 0) * 0.1) if count else 0.2
        out.append(Evidence(
            evidence_id=_ev_id("confluence", "alignment"),
            label="Confluence Alignment Evidence",
            category=EvidenceCategory.CONFLUENCE.value,
            direction=(EvidenceDirection.SUPPORTS.value if count and count >= 2
                         else EvidenceDirection.NEUTRAL.value),
            weight=0.10,
            strength=_strength_from_score(conf_score),
            confidence=conf_score,
            source="feature_snapshot.groups.confluence",
            facts=tuple(str(r) for r in reasons[:5]),
            trace="feature_snapshot.groups.confluence",
            raw_key="confluence",
        ))

        # Risk — resistance / premium zone
        sr = groups.get("support_resistance") or {}
        premium = sr.get("premium_discount") or ""
        zones = sr.get("zones") or []
        supply = [z for z in zones if z.get("kind") == "supply"]
        risk_dir = EvidenceDirection.NEUTRAL.value
        if premium and ("premium" in str(premium).lower() or "عليا" in str(premium)):
            risk_dir = EvidenceDirection.CONTRADICTS.value if side in ("buy", "long") else EvidenceDirection.SUPPORTS.value
        elif supply and side in ("buy", "long"):
            risk_dir = EvidenceDirection.CONTRADICTS.value
        out.append(Evidence(
            evidence_id=_ev_id("risk", "location"),
            label="Risk Location Evidence",
            category=EvidenceCategory.RISK.value,
            direction=risk_dir,
            weight=0.10,
            strength=_strength_from_score(0.6 if risk_dir != EvidenceDirection.NEUTRAL.value else 0.3),
            confidence=0.6 if risk_dir != EvidenceDirection.NEUTRAL.value else 0.3,
            source="feature_snapshot.groups.support_resistance",
            facts=(f"premium_discount={premium}", f"supply_zones={len(supply)}"),
            trace="feature_snapshot.groups.support_resistance",
            raw_key="support_resistance",
        ))

        return out

    def _from_history(self, ctx: dict[str, Any], side: str) -> list[Evidence]:
        items: list[Evidence] = []
        sim = ctx.get("similarity_context") or {}
        items.extend(self._from_similarity(sim, side))

        stats = ctx.get("strategy_statistics") or {}
        recent = ctx.get("recent_performance") or {}
        closed = stats.get("closed_trades") or 0
        exp = stats.get("expectancy")
        reliable = stats.get("reliable")

        if not closed:
            return items + [Evidence(
                evidence_id=_ev_id("history", "insufficient"),
                label="Insufficient Historical Sample",
                category=EvidenceCategory.HISTORY.value,
                direction=EvidenceDirection.MISSING.value,
                weight=0.15,
                strength=EvidenceStrength.UNKNOWN.value,
                confidence=0.0,
                source="strategy_statistics",
                facts=("closed_trades=0",),
                trace="strategy_statistics.closed_trades",
            )]

        direction = EvidenceDirection.NEUTRAL.value
        if exp is not None:
            direction = (EvidenceDirection.SUPPORTS.value if exp > 0
                         else EvidenceDirection.CONTRADICTS.value)
        conf = 0.5
        if reliable:
            conf = min(0.85, 0.5 + closed / 40)
        r30 = recent.get("rolling_30")
        if r30 is not None and r30 < 0:
            direction = EvidenceDirection.CONTRADICTS.value
            conf = max(conf, 0.55)

        return items + [Evidence(
            evidence_id=_ev_id("history", "performance"),
            label="Historical Performance Evidence",
            category=EvidenceCategory.HISTORY.value,
            direction=direction,
            weight=0.15,
            strength=_strength_from_score(conf),
            confidence=conf,
            source="strategy_statistics",
            facts=(f"closed={closed}", f"expectancy={exp}", f"reliable={reliable}"),
            trace="strategy_statistics.expectancy",
            raw_key="expectancy",
        )]

    def _from_similarity(self, sim: dict[str, Any], side: str) -> list[Evidence]:
        """Historical similarity evidence — not a decision, evidence only."""
        if not sim or not sim.get("available"):
            return [Evidence(
                evidence_id=_ev_id("similarity", "none"),
                label="No Historical Evidence",
                category=EvidenceCategory.HISTORY.value,
                direction=EvidenceDirection.MISSING.value,
                weight=0.10,
                strength=EvidenceStrength.UNKNOWN.value,
                confidence=0.0,
                source="similarity_context",
                facts=tuple(sim.get("historical_evidence") or ("No Historical Evidence",)),
                trace="similarity_context.available=false",
            )]

        match_count = sim.get("match_count") or 0
        avg_r = sim.get("average_r")
        win_rate = sim.get("average_win_rate")
        direction = EvidenceDirection.NEUTRAL.value
        if avg_r is not None:
            direction = (EvidenceDirection.SUPPORTS.value if avg_r > 0
                         else EvidenceDirection.CONTRADICTS.value)
        conf = min(0.85, 0.3 + match_count / 20)

        facts = list(sim.get("historical_evidence") or [])
        warnings = sim.get("historical_warnings") or []
        if warnings:
            facts.extend(f"warning:{w}" for w in warnings)

        return [Evidence(
            evidence_id=_ev_id("similarity", "matches"),
            label="Historical Similarity Evidence",
            category=EvidenceCategory.HISTORY.value,
            direction=direction,
            weight=0.10,
            strength=_strength_from_score(conf),
            confidence=conf,
            source="similarity_context",
            facts=tuple(str(f) for f in facts),
            trace="similarity_context.match_count",
            raw_key="similarity",
        )]

    def _from_recommendation(self, ctx: dict[str, Any]) -> list[Evidence]:
        reco = ctx.get("recommendation_snapshot") or {}
        if not reco:
            return []

        action = reco.get("action") or "none"
        grade = reco.get("grade") or "—"
        conf = float(reco.get("confidence") or 0.0)
        rr = reco.get("risk_reward")

        facts = [f"action={action}", f"grade={grade}", f"rr={rr}"]
        direction = EvidenceDirection.NEUTRAL.value
        if action in ("now", "pending"):
            direction = EvidenceDirection.SUPPORTS.value

        return [Evidence(
            evidence_id=_ev_id("recommendation", "plan"),
            label="Recommendation Plan Evidence",
            category=EvidenceCategory.RECOMMENDATION.value,
            direction=direction,
            weight=0.0,
            strength=_strength_from_score(conf),
            confidence=conf,
            source="recommendation_snapshot",
            facts=tuple(str(f) for f in facts),
            trace="recommendation_snapshot",
            raw_key="recommendation",
        )]


class EvidenceProvider(EvidenceEngine):
    """Alias implementing EvidenceProvider protocol."""

    pass
