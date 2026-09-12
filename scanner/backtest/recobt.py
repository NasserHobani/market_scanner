# -*- coding: utf-8 -*-
"""اختبار خلفي **للتوصية التي تعرضها اللوحة فعلاً**.

لماذا كان لا بدّ من محرّك ثانٍ:

``backtest/engine.py`` يختبر إشارة الالتقاء وحدها ولا يستدعي
``analysis/recommend.py`` إطلاقاً. بينما اللوحة توصي عبر ``recommend``
— إليوت والنماذج وحركة السعر والتصنيف A/B/C — وصفقاتك المسجّلة تُفتح
منها. أي أن الرقم الذي كان يطمئنك ليس رقم ما ستنفّذه.

هنا يُشغَّل ``recommend`` نفسه على التاريخ، وتُحسم كل خطة بـ
``tracking.resolve`` — المحرّك ذاته الذي يحسم صفقاتك الحيّة. فالنتيجة
قابلة للمقارنة المباشرة بصفحة الأداء لأنها تقيس الشيء نفسه بالقاعدة
نفسها، بما فيها اعتبار الشمعة الغامضة خسارة.

مبدأ لا يُخرق: **لا شمعة مستقبلية تدخل القرار**. عند كل خطوة يُمرَّر
``df.iloc[:i+1]`` فقط، وما بعد ``i`` يُستعمل للحسم لا للقرار. اختبار
الحقن في ``tests_recobt.py`` يثبت ذلك بتشويه المستقبل والتأكد من ثبات
النتيجة.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pandas as pd

from ..analysis.recommend import build as build_reco
from ..config import MarketConfig
from ..scoring.engine import score_symbol
from ..tracking import LOST, OPEN, PENDING, WON, Plan, resolve, split, split_multi, summarize

# أقلّ تاريخ يحتاجه فلتر الفريم الأعلى قبل أن تُعتبر النتيجة ذات معنى
WARMUP = 300

# مهلة الدخول والاحتفاظ بالشموع — نفس أرقام التتبّع الحيّ حتى تتطابق
# قواعد الحسم بين الاختبار والواقع
ENTRY_DEADLINE = {"15m": 96, "1h": 48, "4h": 30, "1d": 10, "1w": 4}
MAX_HOLD = {"15m": 200, "1h": 150, "4h": 100, "1d": 60, "1w": 26}

FACTOR_KEYS = {
    "الفريم الأعلى": "الفريم الأعلى",
    "نماذج الشموع": "نماذج الشموع",
    "النموذج السعري": "النموذج السعري",
    "موجات إليوت": "موجات إليوت",
    "عناصر الالتقاء": "عناصر الالتقاء",
    "حركة السعر": "حركة السعر",
    "الدرجة الموزونة": "الدرجة",
    "اصطياد سيولة سفلية": "اصطياد سيولة",
}


@dataclass
class Signal:
    symbol: str
    timeframe: str
    index: int
    time: object
    action: str
    grade: str
    score: float
    entry: float
    stop: float
    target: float
    factors: list[str] = field(default_factory=list)
    status: str = PENDING
    r_multiple: float | None = None
    bars_held: int = 0
    note: str = ""

    def as_row(self) -> dict:
        return {
            "symbol": self.symbol, "timeframe": self.timeframe,
            "time": self.time, "action": self.action, "grade": self.grade,
            "score": self.score, "entry": self.entry, "stop": self.stop,
            "target": self.target, "factors": self.factors,
            "status": self.status, "r_multiple": self.r_multiple,
            "bars_held": self.bars_held, "note": self.note,
        }


def _factors(reco: dict) -> list[str]:
    out: list[str] = []
    for item in reco.get("breakdown") or []:
        try:
            value = float(item.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        label = FACTOR_KEYS.get(str(item.get("label") or "").strip())
        if label and label not in out:
            out.append(label)
    return out


def _bars(df: pd.DataFrame, start: int) -> list[dict]:
    """شموع ما بعد الإشارة بالشكل الذي يفهمه محرّك الحسم."""
    part = df.iloc[start:]
    cols = ("open", "high", "low", "close")
    return [{"open": float(o), "high": float(h), "low": float(l), "close": float(c)}
            for o, h, l, c in zip(*(part[k].to_numpy() for k in cols))]


def scan_symbol(df: pd.DataFrame, symbol: str, timeframe: str,
                cfg: MarketConfig, *, step: int = 1,
                warmup: int = WARMUP,
                start: int | None = None,
                end: int | None = None,
                window_bars: int | None = None) -> list[Signal]:
    """يمرّ على التاريخ ويجمع كل خطة كان النظام سيصدرها.

    ``step`` يقفز شموعاً لتسريع التجربة؛ 1 يفحص كل شمعة.
    """
    n = len(df)
    first = max(warmup, start if start is not None else warmup)
    last = min(n - 2, end if end is not None else n - 2)
    # ‎>‎ لا ‎>=‎: مدى من شمعة واحدة (start == end) طلبٌ مشروع، ورفضه
    # كان يجعل فحص إشارة بعينها يعود فارغاً بلا سبب ظاهر
    if first > last:
        return []

    window_bars = int(window_bars or getattr(cfg, "candles", 1500) or 1500)
    deadline = ENTRY_DEADLINE.get(timeframe, 30)
    cap = MAX_HOLD.get(timeframe, 100)
    signals: list[Signal] = []
    seen_entry: float | None = None

    for i in range(first, last + 1, step):
        # لا شيء بعد i يدخل القرار — هذا هو الشرط الذي يجعل النتيجة
        # ذات معنى؛ خرقه يجعل أي اختبار خلفي يبدو مربحاً.
        # والنافذة مقيّدة بحجمها في التشغيل الحيّ: التشغيل الحيّ يمرّر
        # آخر cfg.candles شمعة، فنافذة أطول هنا تعني اختبار نظامٍ آخر.
        # وهي تحدّ الكلفة أيضاً فلا تنمو تربيعياً مع طول التاريخ.
        lo = max(0, i + 1 - window_bars)
        window = df.iloc[lo: i + 1]
        try:
            scored = score_symbol(window, symbol, timeframe, cfg)
            reco = build_reco(window, cfg, scored.score, scored.htf,
                              scored.confluence).as_dict()
        except Exception:  # noqa: BLE001
            continue

        if reco.get("action") not in ("now", "pending"):
            continue
        targets = reco.get("targets") or []
        entry, stop = reco.get("entry"), reco.get("stop")
        if entry is None or stop is None or not targets:
            continue

        plan = Plan(side=reco.get("side", "buy"), entry=float(entry),
                    stop=float(stop), target=float(targets[0]))
        if not plan.valid():
            continue

        # الخطة نفسها تتكرّر على شموع متتالية؛ تسجيلها مرّة واحدة يمنع
        # تضخيم العيّنة بصفقة واحدة مكرّرة عشرين مرة
        if seen_entry is not None and abs(plan.entry - seen_entry) <= seen_entry * 0.002:
            continue
        seen_entry = plan.entry

        immediate = reco.get("action") == "now"
        res = resolve(_bars(df, i + 1), plan,
                      already_entered=immediate,
                      entry_price=plan.entry if immediate else None,
                      max_bars=deadline)

        status, r = res.status, res.r_multiple
        if status == OPEN and res.bars_held > cap:
            status = WON if (r or 0) > 0 else LOST

        signals.append(Signal(
            symbol=symbol, timeframe=timeframe, index=i,
            time=df.index[i], action=reco["action"],
            grade=reco.get("grade") or "—", score=round(scored.score, 1),
            entry=plan.entry, stop=plan.stop, target=plan.target,
            factors=_factors(reco), status=status, r_multiple=r,
            bars_held=res.bars_held, note=res.note,
        ))

    return signals


def report(signals: Iterable[Signal], *, min_n: int = 5) -> dict:
    """ملخّص بنفس مقاييس صفحة الأداء — لتكون الأرقام قابلة للمقارنة."""
    rows = [s.as_row() for s in signals]
    return {
        "overall": summarize(rows),
        "by_grade": split(rows, "grade", min_n=min_n),
        "by_timeframe": split(rows, "timeframe", min_n=min_n),
        "by_action": split(rows, "action", min_n=min_n),
        "by_factor": split_multi(rows, "factors", min_n=min_n),
        "rows": rows,
    }
