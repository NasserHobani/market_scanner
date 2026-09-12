# -*- coding: utf-8 -*-
"""Weekly advisor evaluation report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .advisor_report import AdvisorReport


class WeeklyReport:
    """Generate weekly evaluation report."""

    def __init__(self, base: AdvisorReport | None = None) -> None:
        self._base = base or AdvisorReport()

    def generate(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
        filtered = [r for r in records if (r.get("execution_date") or "") >= since]
        report = self._base.generate(filtered, period="weekly", since=since)
        report["week_start"] = since
        report["week_end"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return report
