"""السياق العام: نظام السوق، اتساع الصعود، والأخبار.

تمييز مهم بين مصدرين:

  ١. ما يُحسب من البيانات — نظام السوق القائد، اتساع الصعود، التذبذب.
     موثوق لأنه مشتقّ من أسعار حقيقية.

  ٢. الأخبار — تُقرأ من تغذيات RSS عامة. عناوين فقط، بلا تحليل معنى.
     الأداة لا تفهم الخبر ولا تقدّر أثره؛ تعرضه لتقرأه أنت.

لا تُحوّل عناوين الأخبار إلى إشارة آلية. تصنيف أثر خبر على سعر يحتاج
فهماً للسياق لا تملكه مطابقة الكلمات، ونتيجته ثقة زائفة أخطر من الجهل.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (compatible; market-scanner/0.1)"}

DEFAULT_FEEDS = {
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "us": [
        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ],
    "saudi": [
        "https://www.argaam.com/en/rss",
    ],
}


@dataclass
class MarketContext:
    regime: str = ""                  # وصف السوق القائد
    regime_score: int = 0             # 1 صاعد · -1 هابط · 0 مختلط
    breadth_pct: float | None = None  # نسبة الرموز فوق العتبة
    volatility: str = ""
    headlines: list[dict] = field(default_factory=list)
    news_error: str = ""
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "regime": self.regime, "regime_score": self.regime_score,
            "breadth_pct": self.breadth_pct, "volatility": self.volatility,
            "headlines": self.headlines, "news_error": self.news_error,
            "notes": self.notes,
        }


def volatility_state(df: pd.DataFrame, atr_series: pd.Series) -> str:
    """التذبذب الحالي مقارنة بمتوسطه — يحدد ملاءمة السوق للتداول."""
    if len(atr_series.dropna()) < 60:
        return ""
    now = float(atr_series.iloc[-1])
    avg = float(atr_series.tail(100).mean())
    if avg <= 0:
        return ""
    ratio = now / avg
    if ratio > 1.6:
        return f"تذبذب مرتفع ({ratio:.1f}× المعتاد) — وقف أوسع وحجم أصغر"
    if ratio < 0.6:
        return f"تذبذب منخفض ({ratio:.1f}× المعتاد) — الأهداف قد لا تتحقق"
    return f"تذبذب طبيعي ({ratio:.1f}× المعتاد)"


def fetch_headlines(market: str, feeds: list[str] | None = None,
                    limit: int = 6, timeout: int = 8) -> tuple[list[dict], str]:
    """عناوين من تغذيات RSS. يعيد (العناوين، نص الخطأ)."""
    urls = feeds if feeds is not None else DEFAULT_FEEDS.get(market, [])
    if not urls:
        return [], "لا تغذيات معرّفة لهذا السوق"

    items: list[dict] = []
    errors: list[str] = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                root = ET.fromstring(resp.read())
            for node in root.iter("item"):
                title = (node.findtext("title") or "").strip()
                if not title:
                    continue
                items.append({
                    "title": title[:180],
                    "link": (node.findtext("link") or "").strip(),
                    "date": (node.findtext("pubDate") or "").strip()[:31],
                    "source": _domain(url),
                })
                if len(items) >= limit * 2:
                    break
        except (urllib.error.URLError, ET.ParseError, OSError, ValueError) as exc:
            errors.append(f"{_domain(url)}: {str(exc)[:60]}")

    if not items:
        return [], " · ".join(errors) or "لم تصل عناوين"
    return items[:limit], ""


def _domain(url: str) -> str:
    try:
        return url.split("//")[1].split("/")[0].replace("www.", "")
    except IndexError:
        return url[:24]


def build(market: str, regime_bull: bool | None = None,
          breadth: tuple[int, int] | None = None,
          df: pd.DataFrame | None = None, atr_series: pd.Series | None = None,
          with_news: bool = True, feeds: list[str] | None = None) -> MarketContext:
    ctx = MarketContext()

    if regime_bull is True:
        ctx.regime, ctx.regime_score = "السوق القائد صاعد", 1
    elif regime_bull is False:
        ctx.regime, ctx.regime_score = "السوق القائد هابط", -1
    else:
        ctx.regime = "نظام السوق غير محدد"

    if breadth and breadth[1]:
        ready, total = breadth
        ctx.breadth_pct = round(ready / total * 100, 1)
        if ctx.breadth_pct >= 30:
            ctx.notes.append(f"اتساع صاعد: {ctx.breadth_pct}% من الرموز فوق العتبة")
        elif ctx.breadth_pct <= 5:
            ctx.notes.append(f"اتساع ضعيف: {ctx.breadth_pct}% فقط فوق العتبة")

    if df is not None and atr_series is not None:
        ctx.volatility = volatility_state(df, atr_series)

    if with_news:
        ctx.headlines, ctx.news_error = fetch_headlines(market, feeds)
        if ctx.headlines:
            ctx.notes.append("العناوين للقراءة لا للإشارة — الأداة لا تحلّل معناها")

    return ctx
