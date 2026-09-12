# -*- coding: utf-8 -*-
"""Historical knowledge retrieval engine."""
from __future__ import annotations

from typing import Any

from scanner.knowledge import KnowledgeRepository, SnapshotKind

from .filters import RetrievalFilters, apply_filters
from .fingerprint import SituationalFingerprint, build_fingerprint
from .feature_distance import FeatureDistance
from .ranking import RankingEngine
from .result import SimilarityMatch, SimilarityResult
from .similarity_score import SimilarityScorer


class RetrievalEngine:
    """Retrieve and score top-N historical situations from knowledge store."""

    def __init__(self, *,
                 repository: KnowledgeRepository | None = None,
                 scorer: SimilarityScorer | None = None,
                 ranker: RankingEngine | None = None) -> None:
        self.repository = repository or KnowledgeRepository()
        self.scorer = scorer or SimilarityScorer()
        self.ranker = ranker or RankingEngine()

    def retrieve(self, query: dict[str, Any], *,
                 top_n: int = 10,
                 filters: RetrievalFilters | None = None) -> SimilarityResult:
        filters = filters or RetrievalFilters()
        query_fp = build_fingerprint(query)
        query_event_id = query.get("event_id", "")

        candidates = self._load_candidates(filters)
        total = len(candidates)

        matches: list[SimilarityMatch] = []
        for cand in candidates:
            if not apply_filters(cand, filters):
                continue
            if query_event_id and cand.get("event_id") == query_event_id:
                continue

            feature_payload = cand.get("feature_payload") or {}
            score, distance = self.scorer.score(query, feature_payload)
            cand_fp = build_fingerprint({**feature_payload, **cand})

            evidence = [
                f"similarity={score.overall}%",
                f"matched={len(distance.matched)} features",
                f"outcome={cand.get('outcome_class', 'unknown')}",
            ]
            if cand.get("r_multiple") is not None:
                evidence.append(f"r_multiple={cand['r_multiple']}")

            matches.append(SimilarityMatch(
                event_id=cand["event_id"],
                symbol=cand.get("symbol", ""),
                market=cand.get("market", ""),
                timeframe=cand.get("timeframe", ""),
                similarity_score=score,
                feature_distance=distance,
                fingerprint=cand_fp,
                matched_features=list(distance.matched),
                different_features=list(distance.different),
                historical_outcome=cand.get("outcome_class") or cand.get("status") or "",
                expected_r=cand.get("r_multiple"),
                r_multiple=cand.get("r_multiple"),
                win_rate=cand.get("win_rate"),
                trade_count=cand.get("trade_count", 1),
                supporting_evidence=evidence,
                data_quality=cand.get("quality_score", 1.0),
                knowledge_confidence=cand.get("confidence", 0.75),
                candle_time=str(cand.get("candle_time") or ""),
                outcome_class=cand.get("outcome_class") or "",
            ))

        ranked = self.ranker.rank(matches)
        top_matches = ranked[:top_n]

        return SimilarityResult(
            query_event_id=query_event_id,
            query_fingerprint=query_fp,
            matches=top_matches,
            total_candidates=total,
            filtered_candidates=len(matches),
            top_n=top_n,
            filters_applied=filters.to_dict(),
            statistics=self._compute_statistics(top_matches),
        )

    def _load_candidates(self, filters: RetrievalFilters) -> list[dict[str, Any]]:
        records = self.repository.search(
            kind=SnapshotKind.FEATURE,
            market=filters.market,
            timeframe=filters.timeframe,
            symbol=filters.symbol,
            limit=5000,
        )

        seen: set[str] = set()
        candidates: list[dict[str, Any]] = []

        for rec in records:
            if rec.event_id in seen:
                continue
            seen.add(rec.event_id)
            payload = rec.payload
            outcome = self._load_outcome(rec.event_id)
            quality = (payload.get("quality") or {}).get("completeness_score", 1.0)

            cand = {
                "event_id": rec.event_id,
                "symbol": payload.get("symbol") or rec.payload.get("symbol"),
                "market": payload.get("market"),
                "timeframe": payload.get("timeframe"),
                "candle_time": payload.get("candle_time"),
                "feature_payload": payload,
                "quality_score": quality,
                "confidence": payload.get("final_score", 0) / 100 if payload.get("final_score") else 0.75,
                "has_outcome": outcome is not None,
            }
            if outcome:
                cand.update({
                    "outcome_class": outcome.get("outcome_class"),
                    "status": outcome.get("status"),
                    "r_multiple": outcome.get("r_multiple"),
                    "closed_at": outcome.get("closed_at"),
                })
            candidates.append(cand)

        return candidates

    def _load_outcome(self, event_id: str) -> dict[str, Any] | None:
        records = self.repository.history(event_id)
        outcomes = [r for r in records if r.kind == SnapshotKind.OUTCOME]
        if not outcomes:
            return None
        return outcomes[-1].payload

    def _compute_statistics(self, matches: list[SimilarityMatch]) -> dict[str, Any]:
        if not matches:
            return {"count": 0}
        rs = [m.r_multiple for m in matches if m.r_multiple is not None]
        winners = sum(1 for m in matches if m.outcome_class == "winner")
        return {
            "count": len(matches),
            "avg_similarity": round(
                sum(m.similarity_score.overall for m in matches) / len(matches), 2,
            ),
            "avg_r": round(sum(rs) / len(rs), 3) if rs else None,
            "win_rate": round(winners / len(matches) * 100, 2) if matches else None,
            "avg_rank_score": round(
                sum(m.rank_score for m in matches) / len(matches), 4,
            ),
        }
