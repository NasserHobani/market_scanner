"""مخرجات المرحلة 0: جدول في الطرفية + ملف CSV."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import MarketConfig
from .scoring import ScoreResult

TV_EXCHANGE = {"binance": "BINANCE", "binance_lib": "BINANCE"}

# TradingView يستخدم الدقائق للفريمات دون اليوم: 4h = 240 وليس 4
TV_INTERVAL = {
    "1m": "1", "3m": "3", "5m": "5", "15m": "15", "30m": "30",
    "1h": "60", "2h": "120", "4h": "240", "6h": "360", "12h": "720",
    "1d": "D", "3d": "3D", "1w": "W", "1M": "M",
}


def tv_interval(timeframe: str) -> str:
    return TV_INTERVAL.get(timeframe, timeframe)


def tradingview_link(adapter: str, symbol: str, timeframe: str) -> str:
    if symbol.endswith(".SR"):
        # السوق السعودي على TradingView: TADAWUL:2222
        sym = f"TADAWUL:{symbol[:-3]}"
    else:
        ex = TV_EXCHANGE.get(adapter, "")
        sym = f"{ex}:{symbol}" if ex else symbol
    return f"https://www.tradingview.com/chart/?symbol={sym}&interval={tv_interval(timeframe)}"


def to_frame(results: list[ScoreResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame([r.to_row() for r in results])
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def print_table(df: pd.DataFrame, cfg: MarketConfig, preview_rows: int = 20) -> None:
    if df.empty:
        print("لا توجد نتائج.")
        return
    cols = [c for c in ("symbol", "close", "score", "decision", "confluence",
                        "htf", "ready", "rsi", "rvol", "atr_pct") if c in df.columns]
    print()
    print(df[cols].head(preview_rows).to_string(index=False))
    if len(df) > preview_rows:
        print(f"... و{len(df) - preview_rows} رمزاً آخر في ملف التقرير")
    print()

    # الفرص المكتملة الشروط هي ما يهم فعلاً — لا مجرد من تجاوز العتبة
    if "ready" in df.columns:
        ready = df[df["ready"]].head(cfg.max_candidates)
        print(f"✅ فرص مكتملة الشروط: {int(df['ready'].sum())} من {len(df)}")
        for _, row in ready.iterrows():
            entry = row.get("entry")
            extra = ""
            if entry and row.get("stop"):
                from .formatting import price as _p, ratio as _r
                extra = (f"  دخول {_p(entry)} · وقف {_p(row['stop'])}"
                         f" · {_r(row.get('rr'))}")
            print(f"  • {row['symbol']:<12} {row['score']:>6.1f}  "
                  f"التقاء {int(row.get('confluence', 0))}  ←  "
                  f"{row.get('reasons', '—')}{extra}")
        if not len(ready):
            print("  (لا شيء — راجع أعمدة blocker أدناه)")

        blocked = df[(~df["ready"]) & (df["score"] >= cfg.normal_threshold)]
        if len(blocked):
            print(f"\n⛔ تجاوزوا العتبة لكن حُجبوا: {len(blocked)}")
            counts = blocked["blocker"].value_counts()
            for reason, n in counts.items():
                names = ", ".join(blocked[blocked["blocker"] == reason]["symbol"].head(6))
                print(f"  {reason} ({n}): {names}")
    else:
        candidates = df[df["score"] >= cfg.normal_threshold].head(cfg.max_candidates)
        print(f"المرشحون فوق العتبة ({cfg.normal_threshold}): {len(candidates)}")
        for _, row in candidates.iterrows():
            active = [k[2:] for k in df.columns if k.startswith("c_") and row.get(k, 0) == 1]
            print(f"  • {row['symbol']:<10} {row['score']:>6.1f}  ← {', '.join(active)}")
    print()


def write_csv(df: pd.DataFrame, market: str, out_dir: str = "reports") -> Path:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M")
    p = Path(out_dir) / f"{market}_{stamp}.csv"
    df.to_csv(p, index=False)
    return p
