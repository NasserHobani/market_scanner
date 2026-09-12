"""سجل تجارب append-only لمنع تحيز الناجي."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


REGISTRY = Path("data/experiments/registry.jsonl")


@dataclass
class ExperimentRecord:
    experiment_id: str
    hypothesis: str
    dataset: dict[str, Any]
    config_hash: str
    seed: int
    stage: str
    metrics: dict[str, Any]
    decision: str
    timestamp: str
    meta: dict[str, Any]


def _stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def create_id(name: str, dataset: dict, config: dict, seed: int) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    digest = _stable_hash({"name": name, "dataset": dataset, "config": config, "seed": seed})
    return f"exp_{stamp}_{digest}"


def append_record(record: ExperimentRecord, path: Path = REGISTRY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")


def read_registry(path: Path = REGISTRY) -> list[dict]:
    """Load all experiment records from append-only registry."""
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def summarize_experiments(path: Path = REGISTRY) -> list[dict]:
    """One row per experiment_id with latest stage metrics."""
    rows = read_registry(path)
    by_id: dict[str, dict] = {}
    for row in rows:
        eid = row.get("experiment_id") or ""
        if not eid:
            continue
        cur = by_id.get(eid, {})
        cur.update({
            "experiment_id": eid,
            "hypothesis": row.get("hypothesis") or cur.get("hypothesis", ""),
            "dataset": row.get("dataset") or cur.get("dataset", {}),
            "seed": row.get("seed", cur.get("seed")),
            "last_stage": row.get("stage"),
            "last_decision": row.get("decision"),
            "last_timestamp": row.get("timestamp"),
            "metrics": row.get("metrics") or {},
        })
        stages = cur.setdefault("stages", [])
        stages.append({"stage": row.get("stage"), "decision": row.get("decision"),
                       "metrics": row.get("metrics"), "timestamp": row.get("timestamp")})
        by_id[eid] = cur

    table: list[dict] = []
    for eid, rec in by_id.items():
        metrics = rec.get("metrics") or {}
        overall = metrics.get("overall") if isinstance(metrics.get("overall"), dict) else metrics
        exp = overall.get("expectancy") if isinstance(overall, dict) else None
        closed = overall.get("closed") if isinstance(overall, dict) else metrics.get("closed")
        baselines = metrics.get("baselines") if isinstance(metrics, dict) else []
        delta = None
        if baselines and exp is not None:
            best = max((b.get("expectancy") for b in baselines
                        if b.get("expectancy") is not None), default=None)
            if best is not None:
                delta = round(exp - best, 3)
        decision = rec.get("last_decision") or "pending"
        if decision in ("pass", "ok", "accept", "accepted"):
            accepted = "yes"
        elif decision in ("reject", "rejected", "fail"):
            accepted = "no"
        elif exp is not None and delta is not None and exp > 0 and delta > 0:
            accepted = "yes"
        else:
            accepted = "—"
        status = "running" if decision == "running" else (
            "completed" if decision not in ("reject", "rejected", "fail") else "rejected")
        table.append({
            "experiment_id": eid,
            "hypothesis": rec.get("hypothesis") or eid,
            "status": status,
            "trades": closed,
            "expectancy": exp,
            "baseline_delta": delta,
            "accepted": accepted,
            "timestamp": rec.get("last_timestamp"),
            "stages": rec.get("stages") or [],
        })
    table.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return table


def log_event(*, experiment_id: str, hypothesis: str, dataset: dict, config: dict,
              seed: int, stage: str, metrics: dict, decision: str,
              meta: dict | None = None) -> None:
    rec = ExperimentRecord(
        experiment_id=experiment_id,
        hypothesis=hypothesis,
        dataset=dataset,
        config_hash=_stable_hash(config),
        seed=seed,
        stage=stage,
        metrics=metrics,
        decision=decision,
        timestamp=datetime.now(timezone.utc).isoformat(),
        meta=meta or {},
    )
    append_record(rec)
