# -*- coding: utf-8 -*-
"""دورة المحفظة الورقية: قيّم المفتوح، ثمّ افتح ما تسمح به القواعد.

الترتيب مقصود: التقييم أوّلاً. فصفقةٌ بلغت وقفها تُغلق وتُحرّر
مقعداً ونقداً — ولو فُتح قبل التقييم لضاعت الفرصة أو تجاوز الحدّ.
"""
from __future__ import annotations

import logging

log = logging.getLogger("dashboard.paper_engine")


def _prices(symbols_by_market: dict) -> dict:
    """أسعار حالية لكل سوق — بأقلّ عدد نداءات."""
    from . import monitor

    out: dict[str, float] = {}
    for market, syms in symbols_by_market.items():
        if not syms:
            continue
        try:
            if market == "crypto":
                out.update(monitor._crypto_prices(set(syms)))
            else:
                out.update(monitor._stock_prices(market, list(syms)))
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر جلب أسعار %s: %s", market, str(exc)[:100])
    return out


def _signals(cfg: dict) -> list[dict]:
    """إشارات المصدر المختار — بمستوياتها.

    ‏PES لا تحمل مستويات دخول ووقف، فتُؤخذ من صفّ المسح المطابق.
    وبلا مستويات لا تُفتح صفقة: حجم المركز يُحسب من بُعد الوقف،
    وبلا وقفٍ لا مخاطرة محدَّدة — وهو ضدّ الغرض كلّه.
    """
    from .models import ScanResult

    src = str(cfg.get("source") or "pes")
    markets = cfg.get("markets") or ["crypto"]
    out: list[dict] = []

    if src == "pes":
        from scanner.strategies import pes_scan

        allowed = set(cfg.get("allowed_states") or ["PRE_BREAKOUT"])
        min_score = float(cfg.get("min_score", 75))
        for m in markets:
            data = pes_scan.load(m) or {}
            for r in (data.get("rows") or []):
                if r.get("state") not in allowed:
                    continue
                if float(r.get("score") or 0) < min_score:
                    continue
                row = (ScanResult.objects
                       .filter(market=m, symbol=r["symbol"])
                       .exclude(entry__isnull=True)
                       .exclude(stop__isnull=True)
                       .order_by("-candle_time").first())
                if row is None:
                    continue
                out.append({"symbol": r["symbol"], "market": m,
                            "timeframe": row.timeframe,
                            "entry": row.entry, "stop": row.stop,
                            "target": row.target1, "source": "pes",
                            "score": r.get("score")})
    else:
        from datetime import timedelta

        from django.utils import timezone

        cutoff = timezone.now() - timedelta(hours=24)
        for m in markets:
            for row in (ScanResult.objects
                        .filter(market=m, action__in=("now", "pending"),
                                candle_time__gte=cutoff)
                        .exclude(entry__isnull=True)
                        .exclude(stop__isnull=True)
                        .order_by("-score")[:20]):
                out.append({"symbol": row.symbol, "market": m,
                            "timeframe": row.timeframe,
                            "entry": row.entry, "stop": row.stop,
                            "target": row.target1, "source": "scanner",
                            "score": row.score})
    return out


def tick() -> dict:
    """دورة واحدة — تقييمٌ ثمّ فتح."""
    from . import paper
    from .models import PaperTrade

    acc = paper.get_or_create_account()
    cfg = paper.settings_for(acc)

    # ── ١) تقييم المفتوحة ──
    open_trades = list(PaperTrade.objects.filter(account=acc, status="open"))
    by_market: dict[str, list[str]] = {}
    for t in open_trades:
        by_market.setdefault(t.market, []).append(t.symbol)
    prices = _prices(by_market) if by_market else {}
    settled = paper.mark_and_settle(acc, prices)

    # ── ٢) فتح ما تسمح به القواعد ──
    opened, refused = [], []
    gate = paper.can_open(acc, cfg)
    if gate["ok"]:
        for sig in _signals(cfg):
            res = paper.open_trade(acc, sig)
            if res.get("ok"):
                opened.append(sig["symbol"])
            else:
                refused.append(f"{sig['symbol']}: {res.get('reason')}")
            if not paper.can_open(acc, cfg)["ok"]:
                break
    else:
        refused.append(gate["reason"])

    return {"marked": settled["marked"], "closed": settled["closed"],
            "opened": opened, "refused": refused[:8],
            "summary": paper.summary(acc)}
