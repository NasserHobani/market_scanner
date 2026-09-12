# -*- coding: utf-8 -*-
"""Monthly advisor evaluation report."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .advisor_report import AdvisorReport


class MonthlyReport:
    """Generate monthly evaluation report."""

    def __init__(self, base: AdvisorReport | None = None) -> None:
        self._base = base or AdvisorReport()

    def generate(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
        filtered = [r for r in records if (r.get("execution_date") or "") >= since]
        report = self._base.generate(filtered, period="monthly", since=since)
        report["month_start"] = since
        report["month_end"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return report
