# -*- coding: utf-8 -*-
"""Package generation cache — reuse when recommendation unchanged."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .unified_package import UnifiedDecisionPackage

CACHE_TTL_SECONDS = 3600


# الطبقات التي تحمل حالة السوق. تغيّر أيٍّ منها يعني حزمة مختلفة.
_EVIDENCE_LAYER_KEYS = (
    "knowledge_context", "reasoning_review", "similarity_context",
    "research_report", "feature_analysis", "feature_snapshot",
    "prediction", "optimization", "decision_ai",
)


def _layers_digest(layers: dict | None) -> str:
    """مِعشار مختصر لطبقات الأدلّة — معرّف لا نسخة."""
    if not layers:
        return ""
    picked = {k: layers.get(k) for k in _EVIDENCE_LAYER_KEYS
              if layers.get(k) not in (None, "", [], {})}
    if not picked:
        return ""
    raw = json.dumps(picked, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


class PackageCache:
    """In-memory + file cache for unified packages."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = Path(__file__).resolve().parents[2] / "data" / "advisor_package_cache.json"
        self._path = Path(path)
        self._memory: dict[str, dict[str, Any]] = {}

    def fingerprint(self, *, symbol: str, market: str, timeframe: str,
                    recommendation: dict[str, Any] | None,
                    evidence_layers: dict[str, Any] | None = None) -> str:
        """بصمة الحزمة — تشمل الأدلّة لا التوصية وحدها.

        ═══ لماذا أُضيفت الطبقات ═══

        كانت البصمة تغطّي (الرمز، السوق، الفريم، التوصية) فقط. والسوق
        يتحرّك بينما التوصية ثابتة: يتغيّر الاتجاه، ويُكسر الهيكل،
        وتهبط تغطية اللقطة — والبصمة كما هي، فتُعاد **حالة سوق قديمة**
        للمراجعة.

        وأثره ليس بطئاً بل خطأً في المضمون: المستشار يحكم على وضع لم
        يعد قائماً، ثم يُسجَّل حكمه كأنه على اللحظة الراهنة — فيفسد
        قياس دقّته لاحقاً.

        الطبقات تُلخَّص بمِعشار (‏hash) لا تُدرَج كاملة: البصمة معرّف
        لا نسخة.
        """
        reco = recommendation or {}
        payload = {
            "symbol": symbol,
            "market": market,
            "timeframe": timeframe,
            "action": reco.get("action"),
            "side": reco.get("side"),
            "confidence": reco.get("confidence"),
            "grade": reco.get("grade"),
            "entry": reco.get("entry"),
            "stop": reco.get("stop"),
            "verdict": reco.get("verdict"),
            "layers": _layers_digest(evidence_layers),
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()[:24]
        return f"pkg_{digest}"

    def get(self, key: str) -> UnifiedDecisionPackage | None:
        entry = self._memory.get(key) or self._load_file().get(key)
        if not entry:
            return None
        if time.time() - entry.get("cached_at", 0) > CACHE_TTL_SECONDS:
            return None
        return _deserialize(entry.get("package"))

    def put(self, key: str, package: UnifiedDecisionPackage) -> None:
        self._memory[key] = {
            "cached_at": time.time(),
            "package": package.to_dict(),
        }
        self._persist()

    def _load_file(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _persist(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._memory, f, indent=2, default=str)


def _deserialize(data: dict[str, Any] | None) -> UnifiedDecisionPackage | None:
    if not data:
        return None
    from .unified_package import EvidenceTrace, UnifiedDecisionPackage

    evidence = tuple(
        EvidenceTrace(
            evidence_id=e["evidence_id"],
            source_layer=e.get("source_layer", ""),
            section=e["section"],
            field=e["field"],
            label=e["label"],
            value=e["value"],
            timestamp=e.get("timestamp", ""),
            confidence=e.get("confidence"),
            reference=e.get("reference", ""),
        )
        for e in (data.get("evidence_index") or [])
    )
    return UnifiedDecisionPackage(
        package_id=data["package_id"],
        event_id=data["event_id"],
        metadata=data.get("metadata") or {},
        recommendation=data.get("recommendation") or {},
        knowledge=data.get("knowledge") or {},
        reasoning=data.get("reasoning") or {},
        similarity=data.get("similarity") or {},
        research=data.get("research") or {},
        feature_intelligence=data.get("feature_intelligence") or {},
        feature_snapshot=data.get("feature_snapshot") or {},
        prediction=data.get("prediction") or {},
        optimization=data.get("optimization") or {},
        decision_ai=data.get("decision_ai") or {},
        evidence_index=evidence,
        diagnostics=data.get("diagnostics") or {},
        schema_version=data.get("schema_version", ""),
        built_at=data.get("built_at", ""),
        shadow_mode=data.get("shadow_mode", True),
    )
