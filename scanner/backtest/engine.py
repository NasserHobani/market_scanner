"""محرك التحقق التاريخي.

كُتب يدوياً بدل استخدام إطار جاهز لأن منطق الإدارة تسلسلي وذو حالة:
هدف أول جزئي ← نقل الوقف للتعادل ← وقف متحرك. الأطر المتجهية تقاوم هذا.

قواعد صارمة لتفادي خداع النفس:
  • الدخول عند إغلاق شمعة الإشارة، لا عند سعرها الأدنى
  • الوقف يُفحص قبل الهدف في الشمعة نفسها (الافتراض الأسوأ)
  • كل المدخلات سببية — لا شيء من المستقبل
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..config import MarketConfig
from ..indicators.htf import AUTO_HTF, adaptive_lengths, resample
from ..indicators.pine import atr, ema
from ..scoring.confluence import confluence_frame
from ..scoring.engine import compute_components


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    entry: float
    initial_sl: float
    tp1: float | None
    tp2: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    r_multiple: float = 0.0
    tp1_hit: bool = False
    reason: str = ""
    confluence: int = 0
    htf: int = 0


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)

    @property
    def closed(self) -> list[Trade]:
        return [t for t in self.trades if t.exit_time is not None]

    def summary(self) -> dict:
        cl = self.closed
        if not cl:
            return {"trades": 0}
        rs = np.array([t.r_multiple for t in cl])
        wins = rs > 0
        equity = np.cumsum(rs)
        peak = np.maximum.accumulate(equity)
        return {
            "trades": len(cl),
            "win_rate": float(wins.mean() * 100),
            "avg_r": float(rs.mean()),
            "total_r": float(rs.sum()),
            "best_r": float(rs.max()),
            "worst_r": float(rs.min()),
            "max_drawdown_r": float((peak - equity).max()),
            "tp1_rate": float(np.mean([t.tp1_hit for t in cl]) * 100),
            "expectancy": float(rs.mean()),
        }

    def by_confluence(self) -> pd.DataFrame:
        cl = self.closed
        if not cl:
            return pd.DataFrame()
        df = pd.DataFrame([{"confluence": t.confluence, "r": t.r_multiple} for t in cl])
        g = df.groupby("confluence")["r"].agg(["count", "mean", lambda s: (s > 0).mean() * 100])
        g.columns = ["صفقات", "متوسط R", "نسبة الربح %"]
        return g.round(2)


def htf_bias_series(df: pd.DataFrame, timeframe: str, fast: int, slow: int,
                    mode: str = "both") -> pd.Series:
    """اتجاه الفريم الأعلى لكل شمعة، بإعادة تجميع سببية."""
    rule = AUTO_HTF.get(timeframe)
    if rule is None:
        return pd.Series(0, index=df.index)

    htf = resample(df, rule)
    slow_eff, fast_eff = adaptive_lengths(len(htf), fast, slow)
    if slow_eff is None:
        return pd.Series(0, index=df.index)

    ef, es = ema(htf["close"], fast_eff), ema(htf["close"], slow_eff)
    ema_bull, price_bull = ef > es, htf["close"] > es

    if mode == "ema":
        bias = ema_bull.map({True: 1, False: -1})
    elif mode == "price":
        bias = price_bull.map({True: 1, False: -1})
    else:
        bias = pd.Series(0, index=htf.index)
        bias[ema_bull & price_bull] = 1
        bias[(~ema_bull) & (~price_bull)] = -1

    # الإزاحة بشمعة: قيمة شمعة الفريم الأعلى لا تُعرف إلا بعد إغلاقها
    return bias.shift(1).reindex(df.index, method="ffill").fillna(0).astype(int)


def run(df: pd.DataFrame, symbol: str, timeframe: str, cfg: MarketConfig,
        warmup: int = 250) -> BacktestResult:
    p = cfg.params
    result = BacktestResult()
    if len(df) <= warmup + 10:
        return result

    from ..scoring.engine import score_series

    scores = score_series(df, cfg)
    conf = confluence_frame(df, cfg)
    htf = htf_bias_series(df, timeframe, p.ema_fast, p.ema_slow, p.htf_mode)
    atr_s = atr(df, p.atr_len)
    swing_low = conf["swing_low"]

    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    times = df.index

    open_trade: Trade | None = None
    sl = tp1 = tp2 = np.nan
    realized_r = 0.0
    last_exit_i = -10_000

    for i in range(warmup, len(df)):
        # ---------------- إدارة صفقة مفتوحة ----------------
        if open_trade is not None:
            risk = open_trade.entry - open_trade.initial_sl
            remaining = (100 - cfg_tp1_pct(cfg)) / 100.0 if open_trade.tp1_hit else 1.0

            # الوقف أولاً: الافتراض الأسوأ داخل الشمعة
            if lows[i] <= sl:
                exit_r = (sl - open_trade.entry) / risk if risk > 0 else 0.0
                open_trade.r_multiple = realized_r + remaining * exit_r
                open_trade.exit_time, open_trade.exit_price = times[i], sl
                open_trade.reason = "وقف" if not open_trade.tp1_hit else "وقف بعد الهدف الأول"
                result.trades.append(open_trade)
                open_trade, last_exit_i = None, i
                continue

            if tp1 is not None and not open_trade.tp1_hit and highs[i] >= tp1:
                open_trade.tp1_hit = True
                realized_r += (cfg_tp1_pct(cfg) / 100.0) * cfg_tp1_r(cfg)
                sl = max(sl, open_trade.entry)          # نقل الوقف للتعادل
                remaining = (100 - cfg_tp1_pct(cfg)) / 100.0

            if highs[i] >= tp2:
                exit_r = (tp2 - open_trade.entry) / risk if risk > 0 else 0.0
                open_trade.r_multiple = realized_r + remaining * exit_r
                open_trade.exit_time, open_trade.exit_price = times[i], tp2
                open_trade.reason = "هدف كامل"
                result.trades.append(open_trade)
                open_trade, last_exit_i = None, i
                continue

            if open_trade.tp1_hit:                       # وقف متحرك للباقي
                sl = max(sl, closes[i] - atr_s.iloc[i] * cfg_trail(cfg))
            continue

        # ---------------- بحث عن دخول ----------------
        if i - last_exit_i < cfg.params.rvol_len // 4:
            continue

        s_now, s_prev = scores.iloc[i], scores.iloc[i - 1]
        if not (s_prev < cfg.normal_threshold <= s_now):
            continue
        if conf["count"].iloc[i] < cfg.min_confluence:
            continue
        if cfg.require_htf and htf.iloc[i] != 1:
            continue

        a = atr_s.iloc[i]
        if np.isnan(a) or a <= 0:
            continue

        entry = closes[i]
        liq = swing_low.iloc[i]
        stop = entry - a * 1.5 if np.isnan(liq) or liq >= entry else liq - a * 0.25
        risk = entry - stop
        if risk <= 0:
            continue

        target = entry + risk * cfg_rr(cfg)
        if (target - entry) / risk < cfg_min_rr(cfg):
            continue

        open_trade = Trade(
            symbol=symbol, entry_time=times[i], entry=entry, initial_sl=stop,
            tp1=entry + risk * cfg_tp1_r(cfg), tp2=target,
            confluence=int(conf["count"].iloc[i]), htf=int(htf.iloc[i]),
        )
        sl, tp1, tp2, realized_r = stop, open_trade.tp1, target, 0.0

    return result


# إعدادات الإدارة — قيم افتراضية تطابق المؤشر، قابلة للتجاوز من الإعدادات
def cfg_tp1_r(cfg: MarketConfig) -> float:
    return float(getattr(cfg, "tp1_r", 1.0))


def cfg_tp1_pct(cfg: MarketConfig) -> float:
    return float(getattr(cfg, "tp1_pct", 50))


def cfg_trail(cfg: MarketConfig) -> float:
    return float(getattr(cfg, "trail_atr", 1.5))


def cfg_rr(cfg: MarketConfig) -> float:
    return float(getattr(cfg, "rr_ratio", 2.0))


def cfg_min_rr(cfg: MarketConfig) -> float:
    return float(getattr(cfg, "min_rr", 1.5))
