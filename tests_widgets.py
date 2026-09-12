# -*- coding: utf-8 -*-
"""Unit tests for dashboard widgets — run: python tests_widgets.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
sys.path.insert(0, str(Path(__file__).parent / "web"))

import django
django.setup()

from django.test import RequestFactory

from dashboard.widget_cache import WidgetCache, TTL_HEALTH
from dashboard import widgets as widget_builders
from dashboard.widget_views import api_widget_health, api_widget_experiments

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


# ── Widget Cache ─────────────────────────────────────────────────────────────

cache = WidgetCache()
cache.set("health", {"market": "crypto"}, {"score": 80}, ttl=60)
hit = cache.get("health", {"market": "crypto"})
check("Cache hit", hit == {"score": 80})
check("Cache miss", cache.get("health", {"market": "us"}) is None)
check("Cache invalidate", cache.invalidate("health") == 1)

def compute():
    return {"value": 42}

data, was_cached = cache.get_or_compute("test", {"k": 1}, 60, compute)
check("get_or_compute miss", data == {"value": 42} and not was_cached)
data2, was_cached2 = cache.get_or_compute("test", {"k": 1}, 60, compute)
check("get_or_compute hit", data2 == {"value": 42} and was_cached2)

# ── Widget Builders ──────────────────────────────────────────────────────────

rows = [
    {"status": "won", "r_multiple": 1.5, "factors": ["htf"], "grade": "A",
     "market": "crypto", "timeframe": "4h"},
    {"status": "lost", "r_multiple": -1.0, "factors": ["confluence"], "grade": "B",
     "market": "crypto", "timeframe": "4h"},
    {"status": "won", "r_multiple": 2.0, "factors": ["htf", "confluence"], "grade": "A",
     "market": "crypto", "timeframe": "4h"},
]
health = widget_builders.build_health(rows)
check("Build health", "health_score" in health)
check("Health expectancy", health.get("expectancy") is not None)

trends = widget_builders.build_trends(rows)
check("Build trends", "equity" in trends)

splits = widget_builders.build_splits(rows)
check("Build splits", len(splits["splits"]) == 4)

exps = widget_builders.build_experiments()
check("Build experiments", "experiments" in exps)

# ── Widget API (smoke) ───────────────────────────────────────────────────────

factory = RequestFactory()
req = factory.get("/api/widgets/experiments/")
resp = api_widget_experiments(req)
check("Experiments API status", resp.status_code == 200)
import json
body = json.loads(resp.content)
check("Experiments API timing", "_timing" in body)
check("Experiments API widget", body.get("_widget") == "experiments")

# ── Summary ──────────────────────────────────────────────────────────────────

passed = sum(1 for ok, _, _ in results if ok)
failed = sum(1 for ok, _, _ in results if not ok)
print(f"\n{'='*60}")
print(f"Widget Tests: {passed} passed, {failed} failed")
print(f"{'='*60}")
for ok, name, extra in results:
    status = "PASS" if ok else "FAIL"
    suffix = f" — {extra}" if extra else ""
    print(f"  [{status}] {name}{suffix}")

if failed:
    sys.exit(1)
