# -*- coding: utf-8 -*-
"""Load experiment history for research dashboard."""
from __future__ import annotations

import json
from pathlib import Path

from scanner.backtest.experiments import REGISTRY, summarize_experiments
from scanner.tracking import summarize


def _backtest_cache_experiments(root: Path | None = None) -> list[dict]:
    """Infer experiments from reco backtest cache filenames."""
    root = root or Path("data/backtest")
    if not root.exists():
        return []
    out = []
    for path in sorted(root.glob("reco_*.jsonl")):
        name = path.stem
        tag = ""
        if "_nohtf" in name:
            tag = "تعطيل فلتر الفريم الأعلى"
        elif "_all" in name:
            tag = "الإعداد الافتراضي"
        rows = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                rows.extend(rec.get("rows") or [])
        except Exception:
            continue
        s = summarize(rows)
        if not s.get("closed"):
            continue
        out.append({
            "experiment_id": f"cache_{name}",
            "hypothesis": tag or name,
            "status": "completed",
            "trades": s.get("closed"),
            "expectancy": s.get("expectancy"),
            "baseline_delta": None,
            "accepted": "yes" if (s.get("expectancy") or 0) > 0 else "no",
            "timestamp": None,
            "source": "backtest_cache",
            "path": str(path),
        })
    return out


def load_experiments(*, include_cache: bool = True) -> list[dict]:
    registry = summarize_experiments(REGISTRY)
    running = sum(1 for e in registry if e.get("status") == "running")
    if include_cache and len(registry) < 2:
        seen_hyp = {e.get("hypothesis") for e in registry}
        for item in _backtest_cache_experiments():
            if item["hypothesis"] not in seen_hyp:
                registry.append(item)
    return registry, running
