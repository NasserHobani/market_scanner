# -*- coding: utf-8 -*-
"""قياس قواعد الوقف لوحدة الاختراق.

    python -m scanner.backtest.breakout_stops --timeframe 4h

سبب وجود هذا الملف — عطب قِيس لا خُمِّن:

الوقف الحالي ‏1.5×ATR14 مقيس على الشمعة المغلقة الأخيرة، وATR متوسط
أربع عشرة شمعة. فحين تنفجر شمعة واحدة إلى عشرة أضعاف مداها المعتاد،
يبتلع المتوسط الانفجار ويقسّمه على أربعة عشر: ‏(13×0.62 + 4.78) / 14 ≈
0.92٪. فيخرج وقف عند 1.38٪ في سوق صار مداه اليومي 4.78٪.

النتيجة أن الوقف يقع **داخل الضجيج**: خمس صفقات حيّة، خمس خسائر، كلها
في شمعة واحدة وكلها خرجت عند الوقف بالضبط. لا علاقة للاتجاه بالأمر —
لو كان صحيحاً تماماً لطُرد قبل أن يتحرّك.

ما يقيسه هذا الملف: خمس قواعد وقف على كل التاريخ المخزَّن، بمحرّك
الحسم نفسه الذي يحكم الصفقات الحيّة. لا قاعدة تُتبنّى قبل رقمها.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import breakout as bo
from scanner import storage
from scanner.backtest.experiments import create_id, log_event
from scanner.indicators.pine import atr as atr_series, ema
from scanner.indicators.volume import rvol as rvol_series
from scanner.tracking import Plan, resolve, summarize

# مهلة الحسم: الاختراق حركة سريعة، وحملها ثلاثين شمعة يخلط نتيجتها
# بحركة أخرى لا علاقة لها بالإشارة
MAX_BARS = 20


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    note: str


RULES: tuple[Rule, ...] = (
    Rule("atr", "الحالي: 1.5×ATR14",
         "المتوسط يبتلع الانفجار فيقع الوقف داخل الضجيج"),
    Rule("low", "قاع شمعة الاختراق",
         "الوقف تحت أدنى نقطة لمسها السعر في الشمعة نفسها"),
    Rule("low_buf", "قاع الشمعة −10٪ من مداها",
         "هامش صغير تحت القاع، فالقاع بالضبط يُلمس كثيراً"),
    Rule("range", "1.0× مدى شمعة الاختراق",
         "يقيس التقلّب الجديد لا القديم"),
    Rule("wider", "الأوسع بين ATR والقاع",
         "لا يضيق أبداً عن الحالي — أدنى تغيير ممكن"),
)


def stop_for(rule: str, close: float, low: float, span: float,
             atr_val: float, stop_atr: float) -> float:
    if rule == "atr":
        return close - stop_atr * atr_val
    if rule == "low":
        return low
    if rule == "low_buf":
        return low - 0.10 * span
    if rule == "range":
        return close - span
    if rule == "wider":
        return min(close - stop_atr * atr_val, low)
    raise ValueError(rule)


def scan_symbol(df: pd.DataFrame, symbol: str, timeframe: str, *,
                min_rvol: float, lookback: int, stop_atr: float,
                target_atr: float, min_body: float,
                target_rr: float | None) -> list[dict]:
    """كل اختراقات الرمز عبر التاريخ، محسومة تحت كل قاعدة وقف.

    الشروط منسوخة عن ``breakout.detect`` بصيغة متّجهة — والاختبار
    ``tests_breakout_stops`` يتحقّق أن النسختين تعطيان النتيجة نفسها،
    وإلا صار القياس على محرّك غير الذي يعمل.
    """
    need = max(lookback, 50) + 25
    if df is None or len(df) < need + 30:
        return []
    if not {"open", "high", "low", "close", "volume"} <= set(df.columns):
        return []

    close = df["close"]
    rv = rvol_series(df, 20).to_numpy()
    av = atr_series(df, 14).to_numpy()
    tr = ema(close, 50).to_numpy()
    c = close.to_numpy()
    h = df["high"].to_numpy()
    lo = df["low"].to_numpy()
    op = df["open"].to_numpy()

    # قمة lookback شمعة سابقة — بلا الشمعة الحالية وإلا قارنت نفسها
    prior = pd.Series(h).rolling(lookback).max().shift(1).to_numpy()

    span = h - lo
    body = np.abs(c - op)
    with np.errstate(divide="ignore", invalid="ignore"):
        body_ratio = np.where(span > 0, body / span, 0.0)

    hits = np.where(
        np.isfinite(rv) & (rv >= min_rvol)
        & np.isfinite(prior) & (c > prior)
        & np.isfinite(tr) & (c > tr)
        & (body_ratio >= min_body)
        & np.isfinite(av) & (av > 0)
    )[0]

    rows: list[dict] = []
    times = df.index
    for i in hits:
        if i < need or i + 2 >= len(df):
            continue        # نحتاج شمعتين على الأقل بعدها ليكون للحسم معنى
        bars = [{"time": times[k], "high": float(h[k]), "low": float(lo[k]),
                 "close": float(c[k]), "open": float(op[k])}
                for k in range(i + 1, min(i + 2 + MAX_BARS, len(df)))]
        entry = float(c[i])
        for rule in RULES:
            stop = stop_for(rule.key, entry, float(lo[i]), float(span[i]),
                            float(av[i]), stop_atr)
            if stop >= entry:
                continue
            risk = entry - stop
            target = (entry + target_rr * risk if target_rr
                      else entry + target_atr * float(av[i]))
            plan = Plan(side="buy", entry=entry, stop=stop, target=target)
            if not plan.valid():
                continue
            res = resolve(bars, plan, max_bars=MAX_BARS)
            rows.append({
                "symbol": symbol, "timeframe": timeframe,
                "time": times[i], "rule": rule.key,
                "status": res.status, "r_multiple": res.r_multiple,
                "rr": (target - entry) / risk,
                "stop_pct": risk / entry * 100,
                "rvol": float(rv[i]),
            })
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="قياس قواعد الوقف للاختراق")
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-rvol", type=float, default=bo.MIN_RVOL)
    ap.add_argument("--lookback", type=int, default=bo.LOOKBACK)
    ap.add_argument("--stop-atr", type=float, default=bo.STOP_ATR)
    ap.add_argument("--target-atr", type=float, default=bo.TARGET_ATR)
    ap.add_argument("--min-body", type=float, default=bo.MIN_BODY)
    ap.add_argument("--target-rr", type=float, default=0.0,
                    help="0 = الهدف بـ ATR كما هو الآن؛ 2 = ضعف المخاطرة")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--hypothesis", default="breakout stop rules")
    args = ap.parse_args(argv)

    base = ROOT / "data" / args.market / args.timeframe
    symbols = sorted({p.stem for p in base.glob("*.csv")}
                     | {p.stem for p in base.glob("*.parquet")})
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print(f"لا بيانات في {base}")
        return 1

    dataset = {"market": args.market, "timeframe": args.timeframe, "symbols": len(symbols)}
    cfg = vars(args).copy()
    experiment_id = create_id(args.hypothesis, dataset, cfg, args.seed)
    log_event(
        experiment_id=experiment_id,
        hypothesis=args.hypothesis,
        dataset=dataset,
        config=cfg,
        seed=args.seed,
        stage="start",
        metrics={"symbols": len(symbols)},
        decision="running",
        meta={},
    )

    rows: list[dict] = []
    for n, sym in enumerate(symbols, 1):
        df = storage.load(args.market, sym, args.timeframe)
        rows += scan_symbol(
            df, sym, args.timeframe, min_rvol=args.min_rvol,
            lookback=args.lookback, stop_atr=args.stop_atr,
            target_atr=args.target_atr, min_body=args.min_body,
            target_rr=args.target_rr or None)
        if n % 25 == 0:
            print(f"  … {n}/{len(symbols)}", end="\r", flush=True)
    print(" " * 40, end="\r")

    head = (f"{args.market} · {args.timeframe} · {len(symbols)} رمز · "
            f"حجم ≥×{args.min_rvol:g}")
    print(f"\n{'═' * 78}\n{head}\n{'═' * 78}")
    if not rows:
        print("لا اختراقات مطابقة للشروط.")
        return 0

    print(f"{'قاعدة الوقف':<26}{'محسومة':>7}{'معلّقة':>8}{'نجاح':>8}"
          f"{'توقّع':>9}{'مع المعلّق':>11}{'وقف%':>8}{'عائد':>7}")
    for rule in RULES:
        part = [r for r in rows if r["rule"] == rule.key]
        s = summarize(part)
        if not s["closed"]:
            print(f"{rule.label:<26}  لا صفقات محسومة")
            continue
        # الصفقة التي لم تُحسم خلال المهلة تُغلق سعرياً في الواقع، فحذفها
        # من الحساب يقيس أعنف الحالات وحدها. نعرض الرقمين معاً: المحسوم
        # وحده، والمحسوم مع اعتبار كل معلّقة صفراً — والحقيقة بينهما.
        unresolved = len(part) - s["closed"]
        with_open = s["total_r"] / len(part) if part else 0.0
        print(f"{rule.label:<26}{s['closed']:>7}{unresolved:>8}"
              f"{s['win_rate']:>7.1f}%{s['expectancy']:>+9.2f}R"
              f"{with_open:>+10.2f}R"
              f"{np.mean([r['stop_pct'] for r in part]):>8.2f}"
              f"{np.mean([r['rr'] for r in part]):>7.2f}")
        print(f"{'':<26}{rule.note}")

    print(f"\nمهلة الحسم {MAX_BARS} شمعة. عمود «مع المعلّق» يفترض أن كل "
          "صفقة لم تُحسم\nخرجت بلا ربح ولا خسارة — وهو الحدّ الأدنى "
          "المتشائم، إذ الوقف الواسع\nيُخفي خسائره في خانة المعلّق.")
    print("\nالحسم بقواعد الصفقات الحيّة: الهدف قبل الوقف = ربح، "
          "والشمعة التي تلمس الاثنين خسارة.")
    log_event(
        experiment_id=experiment_id,
        hypothesis=args.hypothesis,
        dataset=dataset,
        config=cfg,
        seed=args.seed,
        stage="complete",
        metrics={"rows": len(rows), "rules": [r.key for r in RULES]},
        decision="done",
        meta={},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
