# -*- coding: utf-8 -*-
"""Review timeline — list, search, detail, live card."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ..memory import AdvisorMemory
from ..runtime_history import AdvisorRuntimeHistory
from .evidence_links import enrich_evidence_list
from .localized_presentation import build_presentations, build_presentation
from .review_identity import identity_from
from .review_meta import ReviewMetaStore


class ReviewTimelineService:
    """Merge runtime history, memory, meta, and evaluations into inspectable reports."""

    def __init__(self) -> None:
        self._history = AdvisorRuntimeHistory()
        self._memory = AdvisorMemory()
        self._meta = ReviewMetaStore()
        self._eval_path = Path(__file__).resolve().parents[3] / "data" / "advisor_evaluations.jsonl"

    def list_reviews(self, *, page: int = 1, page_size: int = 25,
                     query: str = "", provider: str = "",
                     agreement: str = "", review_type: str = "",
                     symbol: str = "", date_from: str = "",
                     date_to: str = "") -> dict[str, Any]:
        records = self._all_history_records()
        records = self._apply_filters(
            records, query=query, provider=provider, agreement=agreement,
            review_type=review_type, symbol=symbol,
            date_from=date_from, date_to=date_to,
        )
        records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        total = len(records)
        start = max(0, (page - 1) * page_size)
        page_rows = records[start:start + page_size]
        return {
            "items": [self._table_row(r) for r in page_rows],
            "page": page,
            "page_size": page_size,
            "total": total,
            "pages": max(1, (total + page_size - 1) // page_size),
        }

    def get_live(self) -> dict[str, Any] | None:
        last = self._history.last()
        if not last:
            return None
        return self._live_card(last)

    def get_review(self, review_id: str) -> dict[str, Any] | None:
        hist = self._find_history(review_id)
        if not hist:
            return None
        mem = self._memory.load(review_id)
        meta = self._meta.get(review_id) or {}
        evaluation = self._find_evaluation(review_id)
        learning = self._learning_for_review(review_id)
        resp = (mem or {}).get("response", {})
        # كانت الافتراضات مثبَّتة على crypto/4h — فتظهر مراجعة سهم
        # أمريكي على فريم 15m كأنها كريبتو على 4h، وهو خطأ صامت
        sym, mkt, tf = identity_from(hist, meta, mem)
        mkt = mkt or "crypto"
        tf = tf or "4h"

        supporting = enrich_evidence_list(
            resp.get("supporting_evidence"), symbol=sym, market=mkt, timeframe=tf,
        )
        contradicting = enrich_evidence_list(
            resp.get("contradicting_evidence"), symbol=sym, market=mkt, timeframe=tf,
        )

        trade_result = self._trade_result(mem, evaluation)

        detail = {
            "review_id": review_id,
            "timestamp": hist.get("timestamp"),
            "review_type": meta.get("review_type", "automatic"),
            "provider": hist.get("provider"),
            "model": hist.get("model"),
            "symbol": sym,
            "market": mkt,
            "timeframe": tf,
            "latency_ms": hist.get("latency_ms"),
            "prompt_tokens": hist.get("prompt_tokens"),
            "completion_tokens": hist.get("completion_tokens"),
            "total_tokens": hist.get("total_tokens"),
            "estimated_cost": hist.get("estimated_cost"),
            "grounding_score": hist.get("grounding_score"),
            "hallucination_score": hist.get("hallucination_score"),
            "agreement": hist.get("agreement") or resp.get("agreement"),
            "confidence": hist.get("confidence") or resp.get("confidence"),
            "recommendation": meta.get("recommendation") or self._reco_from_package(mem),
            "summary": resp.get("summary", ""),
            "reasoning": resp.get("reasoning", ""),
            "supporting_evidence": supporting,
            "contradicting_evidence": contradicting,
            "risks": resp.get("risks", []),
            "missing_information": resp.get("missing_information", []),
            "suggested_experiment": resp.get("suggested_experiment"),
            "status": "accepted" if (mem or {}).get("accepted", True) else "rejected",
            "review_status": resp.get("status", "accepted"),
            "package_id": (mem or {}).get("package_id", ""),
            "event_id": hist.get("event_id") or (mem or {}).get("event_id", ""),
            "trade_result": trade_result,
            "evaluation": evaluation,
            "learning": learning,
            "package_diagnostics": self._package_diag(mem),
        }
        detail["presentations"] = build_presentations(detail)
        return detail

    def provider_statistics(self) -> list[dict[str, Any]]:
        by_provider: dict[str, dict[str, Any]] = {}
        for rec in self._all_history_records():
            pid = rec.get("provider", "unknown")
            bucket = by_provider.setdefault(pid, {
                "provider": pid, "reviews": 0, "tokens": 0, "cost": 0.0,
                "latency_sum": 0.0, "grounding_sum": 0.0,
            })
            bucket["reviews"] += 1
            bucket["tokens"] += int(rec.get("total_tokens") or 0)
            bucket["cost"] += float(rec.get("estimated_cost") or 0)
            bucket["latency_sum"] += float(rec.get("latency_ms") or 0)
            bucket["grounding_sum"] += float(rec.get("grounding_score") or 0)
        out = []
        for pid, b in by_provider.items():
            n = b["reviews"] or 1
            out.append({
                "provider": pid,
                "review_count": b["reviews"],
                "total_tokens": b["tokens"],
                "total_cost": round(b["cost"], 6),
                "avg_latency_ms": round(b["latency_sum"] / n, 1),
                "avg_grounding": round(b["grounding_sum"] / n, 1),
            })
        return sorted(out, key=lambda x: x["review_count"], reverse=True)

    def _all_history_records(self) -> list[dict[str, Any]]:
        path = self._history._path  # noqa: SLF001
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]

    def _find_history(self, review_id: str) -> dict[str, Any] | None:
        for rec in self._all_history_records():
            if rec.get("review_id") == review_id:
                return rec
        return None

    def _find_evaluation(self, review_id: str) -> dict[str, Any] | None:
        if not self._eval_path.exists():
            return None
        for line in self._eval_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("advisor_review_id") == review_id:
                return rec
        return None

    def _learning_for_review(self, review_id: str) -> dict[str, Any]:
        lessons_path = Path(__file__).resolve().parents[3] / "data" / "learning_lessons.jsonl"
        if not lessons_path.exists():
            return {"lessons": [], "generated": False}
        eval_rec = self._find_evaluation(review_id)
        eid = (eval_rec or {}).get("evaluation_id", "")
        lessons = []
        for line in lessons_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            les = json.loads(line)
            if eid and eid in (les.get("supporting_evidence") or []):
                lessons.append(les)
        return {"lessons": lessons, "generated": bool(lessons)}

    def _trade_result(self, mem: dict[str, Any] | None,
                      evaluation: dict[str, Any] | None) -> dict[str, Any]:
        perf = (mem or {}).get("later_performance") or {}
        ev = evaluation or {}
        outcome = ev.get("trade_result") or perf.get("status", "")
        return {
            "outcome": outcome,
            "r_multiple": ev.get("r_multiple") or perf.get("r_multiple"),
            "claude_agreed": ev.get("advisor_agreement") in ("agree", "partial"),
            "claude_correct": ev.get("advisor_correct"),
            "learning_generated": bool(self._learning_for_review(
                (mem or {}).get("record_id", ""),
            ).get("lessons")),
            "win_loss": outcome,
        }

    def _reco_from_package(self, mem: dict[str, Any] | None) -> dict[str, Any]:
        resp = (mem or {}).get("response") or {}
        # Best-effort: some reviews store side/action on the response envelope
        side = resp.get("direction") or resp.get("side") or ""
        action = resp.get("action") or ""
        if side or action:
            return {"side": side, "action": action}
        return {}

    def _package_diag(self, mem: dict[str, Any] | None) -> dict[str, Any]:
        """Prefer runtime-state diagnostics for the matching review_id."""
        try:
            from scanner.ai_advisor.runtime_state import AdvisorRuntimeState
            state = AdvisorRuntimeState().load()
            rid = (mem or {}).get("record_id") or (mem or {}).get("response", {}).get("review_id")
            if rid and state.get("review_id") == rid and state.get("package_diagnostics"):
                return dict(state["package_diagnostics"])
            if state.get("package_diagnostics") and not rid:
                return dict(state["package_diagnostics"])
        except Exception:  # noqa: BLE001
            pass
        return {}

    def _table_row(self, hist: dict[str, Any]) -> dict[str, Any]:
        rid = hist.get("review_id", "")
        meta = self._meta.get(rid) or {}
        ev = self._find_evaluation(rid)
        sym, mkt, tfm = identity_from(hist, meta)
        row_detail = {
            "review_id": rid,
            "symbol": sym,
            "timeframe": tfm,
            "agreement": hist.get("agreement"),
            "confidence": hist.get("confidence"),
            "recommendation": meta.get("recommendation", {}),
            "review_type": meta.get("review_type", "automatic"),
        }
        pres_ar = build_presentation(row_detail, "ar")
        return {
            "review_id": rid,
            "timestamp": hist.get("timestamp"),
            "symbol": sym,
            "pair": sym,
            "market": mkt,
            "timeframe": tfm,
            "decision": meta.get("recommendation", {}).get("side", ""),
            "verdict": pres_ar.get("final_verdict", ""),
            "verdict_ar": pres_ar.get("final_verdict", ""),
            "agreement": hist.get("agreement"),
            "agreement_label": pres_ar.get("agreement_label", ""),
            "confidence": hist.get("confidence"),
            "outcome": (ev or {}).get("trade_result", ""),
            "correct": (ev or {}).get("advisor_correct"),
            "provider": hist.get("provider"),
            "review_type": meta.get("review_type", "automatic"),
            "language": "ar",
            "latency_ms": hist.get("latency_ms"),
            "total_tokens": hist.get("total_tokens"),
            "estimated_cost": hist.get("estimated_cost"),
        }

    def _live_card(self, hist: dict[str, Any]) -> dict[str, Any]:
        rid = hist.get("review_id", "")
        detail = self.get_review(rid) or {}
        reco = detail.get("recommendation") or {}
        pres_ar = (detail.get("presentations") or {}).get("ar") or {}
        return {
            "review_id": rid,
            # البطاقة الحيّة كانت تقرأ الرمز خاماً — فتظهر «—» بينما
            # الجدول أسفلها يعرضه صحيحاً على السجلّ نفسه
            "symbol": identity_from(hist, detail)[0],
            "timeframe": detail.get("timeframe", ""),
            "side": reco.get("side", "").upper(),
            "agreement": hist.get("agreement"),
            "agreement_label": pres_ar.get("agreement_label", ""),
            "confidence": hist.get("confidence"),
            "verdict": pres_ar.get("final_verdict", ""),
            "reason": pres_ar.get("executive_summary") or detail.get("summary", "")[:300],
            "presentations": detail.get("presentations"),
            "latency_ms": hist.get("latency_ms"),
            "estimated_cost": hist.get("estimated_cost"),
            "total_tokens": hist.get("total_tokens"),
            "timestamp": hist.get("timestamp"),
        }

    def _apply_filters(self, records: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        q = (kwargs.get("query") or "").strip().lower()
        provider = kwargs.get("provider", "")
        agreement = kwargs.get("agreement", "")
        review_type = kwargs.get("review_type", "")
        symbol = (kwargs.get("symbol") or "").upper()
        date_from = kwargs.get("date_from", "")
        date_to = kwargs.get("date_to", "")

        out = []
        for rec in records:
            rid = rec.get("review_id", "")
            meta = self._meta.get(rid) or {}
            rtype = meta.get("review_type", "automatic")
            if review_type and rtype != review_type:
                continue
            if provider and rec.get("provider") != provider:
                continue
            if agreement and rec.get("agreement") != agreement:
                continue
            # الهويّة المشتقّة تُستعمل في الترشيح كما تُستعمل في العرض،
            # وإلّا بحثتَ عن رمز تراه في الجدول فلم تجده
            rec_sym, _rec_mkt, _rec_tf = identity_from(rec, meta)
            if symbol and rec_sym.upper() != symbol:
                continue
            ts = rec.get("timestamp", "")
            if date_from and ts < date_from:
                continue
            if date_to and ts > date_to:
                continue
            if q:
                hay = " ".join([
                    rid, rec_sym, rec.get("provider", ""),
                    rec.get("agreement", ""), ts, rec.get("event_id", ""),
                ]).lower()
                if q not in hay:
                    continue
            out.append(rec)
        return out
