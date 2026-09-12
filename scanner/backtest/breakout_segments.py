# -*- coding: utf-8 -*-
"""هل داخل الاختراقات شريحة رابحة؟

    python -m scanner.backtest.breakout_segments --timeframe 4h

قياس قواعد الوقف أظهر أن توسيع الوقف ينقل الخسارة ولا يزيلها: يتحسّن
على 4h و1h ثم ينقلب على 15m. فالسؤال الباقي ليس «أي وقف» بل «أي
اختراق» — هل ثمّة شريحة داخل هذه الحالات لها أفضلية حقيقية؟

يُقاس هنا أربعة أبعاد، وأولها فرضية المستخدم مباشرة:

  • الصعود السابق للإشارة — «أغلبها بعد انفجار سعري»
  • شدّة الحجم
  • اتساع الوقف نسبة إلى السعر
  • بُعد الإغلاق عن قمة الشمعة (هل أُغلقت عند القمة أم تراجعت)

الشريحة لا تُتبنّى لمجرّد أن رقمها موجب: التقسيم على أربعة أبعاد
يولّد فرصاً كثيرة لظهور رقم موجب بالصدفة، فيُطبع تحذير الاختبار
المتعدّد مع كل جدول.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import breakout as bo
from scanner import storage
from scanner.indicators.pine import atr as atr_series, ema
from scanner.indicators.volume import rvol as rvol_series
from scanner.tracking import Plan, resolve, summarize

MAX_BARS = 20


def events(df: pd.DataFrame, symbol: str, *, min_rvol: float, lookback: int,
           min_body: float, target_rr: float) -> list[dict]:
    """اختراقات الرمز بالوقف «قاع الشمعة −10٪» — أقلّ القواعد سوءاً."""
    need = max(lookback, 50) + 25
    if df is None or len(df) < need + 30:
        return []
    if not {"open", "high", "low", "close", "volume"} <= set(df.columns):
        return []

    close = df["close"]
    rv = rvol_series(df, 20).to_numpy()
    av = atr_series(df, 14).to_numpy()
    tr = ema(close, 50).to_numpy()
    c, h = close.to_numpy(), df["high"].to_numpy()
    lo, op = df["low"].to_numpy(), df["open"].to_numpy()

    prior = pd.Series(h).rolling(lookback).max().shift(1).to_numpy()
    span = h - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        body_ratio = np.where(span > 0, np.abs(c - op) / span, 0.0)

    hits = np.where(
        np.isfinite(rv) & (rv >= min_rvol) & np.isfinite(prior) & (c > prior)
        & np.isfinite(tr) & (c > tr) & (body_ratio >= min_body)
        & np.isfinite(av) & (av > 0)
    )[0]

    out: list[dict] = []
    times = df.index
    for i in hits:
        if i < need or i + 2 >= len(df):
            continue
        entry, low_i, span_i = float(c[i]), float(lo[i]), float(span[i])
        stop = low_i - 0.10 * span_i
        if stop >= entry:
            continue
        risk = entry - stop
        plan = Plan(side="buy", entry=entry, stop=stop,
                    target=entry + target_rr * risk)
        if not plan.valid():
            continue
        bars = [{"time": times[k], "high": float(h[k]), "low": float(lo[k]),
                 "close": float(c[k]), "open": float(op[k])}
                for k in range(i + 1, min(i + 2 + MAX_BARS, len(df)))]
        res = resolve(bars, plan, max_bars=MAX_BARS)

        # الصعود السابق: من أدنى قاع في اثنتي عشرة شمعة إلى الإغلاق
        base = float(np.min(lo[max(0, i - 12):i + 1]))
        row = {
            "symbol": symbol, "status": res.status,
            "r_multiple": res.r_multiple,
            "runup": (entry / base - 1) * 100 if base > 0 else 0.0,
            "rvol": float(rv[i]),
            "stop_pct": risk / entry * 100,
            # 0 = أُغلقت عند القمة تماماً، 1 = عند القاع
            "off_high": ((float(h[i]) - entry) / span_i) if span_i > 0 else 0.0,
        }
        out.append(row)
    return out


def table(rows: list[dict], key: str, edges: list[float], unit: str,
          title: str, min_n: int) -> None:
    print(f"\n  ── {title} ──")
    prev = -1e18
    for e in edges + [1e18]:
        part = [r for r in rows if prev < r.get(key, 0) <= e]
        prev_shown, prev = prev, e
        if len(part) < min_n:
            continue
        s = summarize(part)
        if not s["closed"]:
            continue
        label = (f"≤{e:g}{unit}" if prev_shown < -1e17 else
                 f">{prev_shown:g}{unit}" if e > 1e17 else
                 f"{prev_shown:g}–{e:g}{unit}")
        honest = s["total_r"] / len(part)
        print(f"    {label:<14}{s['closed']:>5} محسومة /{len(part):>5}"
              f" · نجاح {s['win_rate']:>5.1f}%"
              f" · توقّع {s['expectancy']:>+6.2f}R"
              f" · مع المعلّق {honest:>+6.2f}R")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="شرائح الاختراق")
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-rvol", type=float, default=bo.MIN_RVOL)
    ap.add_argument("--lookback", type=int, default=bo.LOOKBACK)
    ap.add_argument("--min-body", type=float, default=bo.MIN_BODY)
    ap.add_argument("--target-rr", type=float, default=2.0)
    ap.add_argument("--min-n", type=int, default=30)
    args = ap.parse_args(argv)

    base = ROOT / "data" / args.market / args.timeframe
    symbols = sorted({p.stem for p in base.glob("*.csv")}
                     | {p.stem for p in base.glob("*.parquet")})
    if args.limit:
        symbols = symbols[: args.limit]

    rows: list[dict] = []
    for n, sym in enumerate(symbols, 1):
        rows += events(storage.load(args.market, sym, args.timeframe), sym,
                       min_rvol=args.min_rvol, lookback=args.lookback,
                       min_body=args.min_body, target_rr=args.target_rr)
        if n % 25 == 0:
            print(f"  … {n}/{len(symbols)}", end="\r", flush=True)
    print(" " * 40, end="\r")

    s = summarize(rows)
    print(f"\n{'═' * 78}")
    print(f"{args.market} · {args.timeframe} · {len(rows)} اختراقاً · "
          f"وقف = قاع الشمعة −10٪ · هدف {args.target_rr:g}R")
    print("═" * 78)
    print(f"  الإجمالي: {s['closed']} محسومة · نجاح {s['win_rate']:.1f}%"
          f" · توقّع {s['expectancy']:+.2f}R"
          f" · مع المعلّق {(s['total_r'] / len(rows) if rows else 0):+.2f}R")

    table(rows, "runup", [3, 8, 15, 30], "%", "الصعود قبل الإشارة "
          "(فرضية «بعد انفجار سعري»)", args.min_n)
    table(rows, "rvol", [10, 15, 25, 50], "×", "شدّة الحجم", args.min_n)
    table(rows, "stop_pct", [5, 10, 20], "%", "اتساع الوقف", args.min_n)
    table(rows, "off_high", [0.05, 0.15, 0.30], "", "بُعد الإغلاق عن قمة "
          "الشمعة (0 = أُغلقت عند القمة)", args.min_n)

    print("\n  تحذير الاختبار المتعدّد: أربعة أبعاد × أربع شرائح = ستّ عشرة"
          "\n  فرصة لظهور رقم موجب بالصدفة. لا تُتبنّى شريحة قبل تأكيدها"
          "\n  على فريم آخر وعلى نصف مستقلّ من الزمن.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
