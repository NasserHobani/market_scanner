# -*- coding: utf-8 -*-
"""Explicit knowledge graph relationships between snapshots."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .schemas import KnowledgeRecord, SnapshotKind


class RelationKind(str, Enum):
    PRODUCES = "produces"
    INFORMS = "informs"
    TRIGGERS = "triggers"
    EXECUTES = "executes"
    CLOSES_AS = "closes_as"
    EVALUATED_BY = "evaluated_by"
    TRAINED_BY = "trained_by"
    DERIVED_FROM = "derived_from"


# Canonical lifecycle chain for traversal
LIFECYCLE_CHAIN: list[tuple[SnapshotKind, SnapshotKind, RelationKind]] = [
    (SnapshotKind.MARKET, SnapshotKind.FEATURE, RelationKind.PRODUCES),
    (SnapshotKind.ENVIRONMENT, SnapshotKind.MARKET, RelationKind.DERIVED_FROM),
    (SnapshotKind.FEATURE, SnapshotKind.RECOMMENDATION, RelationKind.INFORMS),
    (SnapshotKind.RECOMMENDATION, SnapshotKind.TRADE, RelationKind.TRIGGERS),
    (SnapshotKind.TRADE, SnapshotKind.OUTCOME, RelationKind.CLOSES_AS),
    (SnapshotKind.OUTCOME, SnapshotKind.EXPERIMENT, RelationKind.EVALUATED_BY),
    (SnapshotKind.EXPERIMENT, SnapshotKind.MODEL, RelationKind.TRAINED_BY),
]


@dataclass(frozen=True)
class KnowledgeRelationship:
    source_id: str
    source_kind: str
    target_id: str
    target_kind: str
    relation: str
    event_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_id": self.target_id,
            "target_kind": self.target_kind,
            "relation": self.relation,
            "event_id": self.event_id,
        }

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> KnowledgeRelationship:
        return cls(
            source_id=row["source_id"],
            source_kind=row["source_kind"],
            target_id=row["target_id"],
            target_kind=row["target_kind"],
            relation=row["relation"],
            event_id=row["event_id"],
        )


@dataclass
class KnowledgeNode:
    node_id: str
    kind: str
    event_id: str
    payload_ref: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "event_id": self.event_id,
            "payload_ref": self.payload_ref,
        }


@dataclass
class KnowledgeGraph:
    """Traversable relationship graph for one knowledge event."""

    event_id: str
    nodes: list[KnowledgeNode] = field(default_factory=list)
    edges: list[KnowledgeRelationship] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def successors(self, node_id: str) -> list[KnowledgeRelationship]:
        return [e for e in self.edges if e.source_id == node_id]

    def predecessors(self, node_id: str) -> list[KnowledgeRelationship]:
        return [e for e in self.edges if e.target_id == node_id]

    def walk_chain(self, start_kind: str) -> list[KnowledgeNode]:
        """Follow lifecycle edges from a starting kind."""
        by_kind = {n.kind: n for n in self.nodes}
        chain: list[KnowledgeNode] = []
        current = by_kind.get(start_kind)
        if not current:
            return chain
        chain.append(current)
        for src_kind, tgt_kind, _rel in LIFECYCLE_CHAIN:
            if src_kind.value != current.kind:
                continue
            nxt = by_kind.get(tgt_kind.value)
            if nxt:
                chain.append(nxt)
                current = nxt
        return chain


def _snapshot_id_from_payload(kind: SnapshotKind, payload: dict[str, Any]) -> str:
    key_map = {
        SnapshotKind.MARKET: "snapshot_id",
        SnapshotKind.FEATURE: "snapshot_id",
        SnapshotKind.RECOMMENDATION: "snapshot_id",
        SnapshotKind.TRADE: "snapshot_id",
        SnapshotKind.OUTCOME: "snapshot_id",
        SnapshotKind.ENVIRONMENT: "environment_id",
        SnapshotKind.EXPERIMENT: "experiment_id",
        SnapshotKind.MODEL: "model_id",
    }
    return str(payload.get(key_map.get(kind, "snapshot_id")) or "")


def build_graph_from_history(event_id: str,
                             records: list[KnowledgeRecord]) -> KnowledgeGraph:
    """Construct graph from stored records using canonical lifecycle rules."""
    graph = KnowledgeGraph(event_id=event_id)
    latest: dict[SnapshotKind, KnowledgeRecord] = {}
    for rec in records:
        latest[rec.kind] = rec

    for kind, rec in latest.items():
        payload = rec.payload
        node_id = _snapshot_id_from_payload(kind, payload) or rec.record_id
        graph.nodes.append(KnowledgeNode(
            node_id=node_id, kind=kind.value, event_id=event_id,
            payload_ref=rec.record_id,
        ))

    def _add_edge(src: SnapshotKind, tgt: SnapshotKind, rel: RelationKind) -> None:
        src_rec = latest.get(src)
        tgt_rec = latest.get(tgt)
        if not src_rec or not tgt_rec:
            return
        graph.edges.append(KnowledgeRelationship(
            source_id=_snapshot_id_from_payload(src, src_rec.payload) or src_rec.record_id,
            source_kind=src.value,
            target_id=_snapshot_id_from_payload(tgt, tgt_rec.payload) or tgt_rec.record_id,
            target_kind=tgt.value,
            relation=rel.value,
            event_id=event_id,
        ))

    for src, tgt, rel in LIFECYCLE_CHAIN:
        _add_edge(src, tgt, rel)

    return graph


def build_explicit_relationships(event_id: str, ids: dict[str, str]) -> list[KnowledgeRelationship]:
    """Build relationships from capture_scan/capture_lifecycle ID map."""
    edges: list[KnowledgeRelationship] = []
    pairs = [
        ("environment_id", SnapshotKind.ENVIRONMENT.value,
         "market_snapshot_id", SnapshotKind.MARKET.value, RelationKind.DERIVED_FROM),
        ("market_snapshot_id", SnapshotKind.MARKET.value,
         "feature_snapshot_id", SnapshotKind.FEATURE.value, RelationKind.PRODUCES),
        ("feature_snapshot_id", SnapshotKind.FEATURE.value,
         "recommendation_snapshot_id", SnapshotKind.RECOMMENDATION.value, RelationKind.INFORMS),
        ("recommendation_snapshot_id", SnapshotKind.RECOMMENDATION.value,
         "trade_snapshot_id", SnapshotKind.TRADE.value, RelationKind.TRIGGERS),
        ("trade_snapshot_id", SnapshotKind.TRADE.value,
         "outcome_snapshot_id", SnapshotKind.OUTCOME.value, RelationKind.CLOSES_AS),
    ]
    for src_key, src_kind, tgt_key, tgt_kind, rel in pairs:
        src_id = ids.get(src_key)
        tgt_id = ids.get(tgt_key)
        if src_id and tgt_id:
            edges.append(KnowledgeRelationship(
                source_id=src_id, source_kind=src_kind,
                target_id=tgt_id, target_kind=tgt_kind,
                relation=rel.value, event_id=event_id,
            ))
    return edges
