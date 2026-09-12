"""وضع المتابعة الحية.

قرار تصميمي مهم: «حي» هنا لا يعني تقييم الإشارة مع كل تغيّر سعر.

الشمعة الجارية تتحرك حتى تغلق، فالدرجة المحسوبة عليها تتغير معها — إشارة
تظهر ثم تختفي. هذا بالضبط ما أصلحناه بقاعدة «الشمعة المغلقة فقط»، ولا يجوز
نقضه باسم الفورية.

لذلك:
  • تقييم الإشارات: عند إغلاق كل شمعة فقط — لا قبله
  • مراقبة الأسعار: كل دقيقة، للعرض والمسافة عن الحدود، بلا إصدار إشارات

النتيجة: تعرف أين السعر لحظياً، لكن لا تُتخذ قرارات على شمعة لم تكتمل.
"""
from __future__ import annotations

import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

TIMEFRAME_SECONDS = {
    "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600, "8h": 28800,
    "12h": 43200, "1d": 86400, "1w": 604800,
}

# الفريمات المتاحة للتنقّل في الواجهة
UI_TIMEFRAMES = ["15m", "1h", "4h", "1d", "1w"]

TIMEFRAME_LABELS = {
    "15m": "15 دقيقة", "1h": "ساعة", "4h": "4 ساعات",
    "1d": "يومي", "1w": "أسبوعي",
}

# الحقبة بدأت خميس 1970-01-01، وأول اثنين بعدها 1970-01-05 أي بعد أربعة أيام.
# شمعة بينانس الأسبوعية تفتح الاثنين 00:00 UTC، فالإزاحة تُطرح قبل القسمة
# وتُعاد بعدها — العكس يعطي يوم أحد.
WEEK_ANCHOR = 4 * 86400


def timeframe_seconds(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(
            f"فريم غير مدعوم في الوضع الحي: {timeframe}. "
            f"المتاح: {', '.join(TIMEFRAME_SECONDS)}"
        )
    return TIMEFRAME_SECONDS[timeframe]


def next_close(timeframe: str, now: float | None = None) -> float:
    """توقيت إغلاق الشمعة القادمة (epoch UTC).

    شموع بينانس محاذية لبداية الحقبة، فالحساب مباشر:
    4h تغلق عند 00:00 و04:00 ... و20:00 بتوقيت UTC.
    الأسبوعية استثناء: تبدأ الاثنين، والحقبة بدأت خميساً.
    """
    period = timeframe_seconds(timeframe)
    now = time.time() if now is None else now
    if timeframe == "1w":
        return ((int(now) - WEEK_ANCHOR) // period + 1) * period + WEEK_ANCHOR
    return (int(now) // period + 1) * period


def format_wait(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} ساعة و{m} دقيقة"
    if m:
        return f"{m} دقيقة و{s} ثانية"
    return f"{s} ثانية"


@dataclass
class AlertState:
    """يمنع تكرار التنبيه لنفس الرمز ما لم تتغير حالته."""

    alerted: dict[str, float] = field(default_factory=dict)
    cooldown_bars: int = 3

    def new_alerts(self, df: pd.DataFrame, bar_index: int) -> pd.DataFrame:
        if df.empty or "ready" not in df.columns:
            return df.head(0)
        ready = df[df["ready"]]
        fresh = []
        for _, row in ready.iterrows():
            sym = row["symbol"]
            last = self.alerted.get(sym)
            if last is None or (bar_index - last) >= self.cooldown_bars:
                fresh.append(row)
                self.alerted[sym] = bar_index
        return pd.DataFrame(fresh) if fresh else ready.head(0)


class Stopper:
    """إيقاف نظيف عند Ctrl+C بدل قطع المسح في منتصفه."""

    def __init__(self) -> None:
        self.stop = False
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle)
            except (ValueError, OSError):
                pass

    def _handle(self, *_):
        if self.stop:
            raise KeyboardInterrupt
        self.stop = True
        print("\nسيتوقف بعد انتهاء الدورة الحالية… (Ctrl+C مرة أخرى للإيقاف الفوري)")

    def sleep(self, seconds: float, tick: float = 1.0) -> bool:
        """نوم قابل للمقاطعة. يعيد False إن طُلب الإيقاف."""
        end = time.time() + seconds
        while time.time() < end:
            if self.stop:
                return False
            time.sleep(min(tick, max(0.0, end - time.time())))
        return not self.stop


def utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
