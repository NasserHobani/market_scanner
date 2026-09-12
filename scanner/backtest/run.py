"""تشغيل التحقق التاريخي.

    python -m scanner.backtest.run --market crypto --top 30
    python -m scanner.backtest.run --market crypto --candles 3000 --split
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .. import storage
from ..adapters import get_adapter
from ..config import load_market
from .engine import BacktestResult, run
from .walkforward import aggregate as wf_aggregate
from .walkforward import run_symbol as wf_run_symbol


def _fmt(summary: dict) -> str:
    if not summary.get("trades"):
        return "لا صفقات"
    return (
        f"صفقات {summary['trades']:4d} · نجاح {summary['win_rate']:5.1f}% · "
        f"متوسط {summary['avg_r']:+.2f}R · مجموع {summary['total_r']:+.1f}R · "
        f"أكبر تراجع {summary['max_drawdown_r']:.1f}R"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="التحقق التاريخي لمنطق الإشارة")
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--timeframe", default=None)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--candles", type=int, default=2000)
    ap.add_argument("--split", action="store_true",
                    help="تقسيم البيانات: نصف للمعايرة ونصف للاختبار المستقل")
    ap.add_argument("--offline", action="store_true", help="استخدم المخزَّن فقط بلا جلب")
    ap.add_argument("--walkforward", action="store_true")
    ap.add_argument("--wf-train", type=int, default=700)
    ap.add_argument("--wf-test", type=int, default=250)
    ap.add_argument("--wf-step", type=int, default=125)
    args = ap.parse_args(argv)

    cfg_path = Path("config") / f"{args.market}.yaml"
    if not cfg_path.exists():
        print(f"ملف الإعدادات غير موجود: {cfg_path}", file=sys.stderr)
        return 1

    cfg = load_market(cfg_path)
    cfg.candles = args.candles
    timeframe = args.timeframe or cfg.timeframes[0]
    adapter = get_adapter(cfg.adapter)

    if args.offline:
        symbols = cfg.symbols
    else:
        try:
            symbols = adapter.usdt_universe(cfg.min_quote_volume, top_n=args.top)
        except Exception as exc:  # noqa: BLE001
            print(f"تعذّر جلب قائمة الرموز ({exc}) — سأستخدم قائمة الإعدادات.")
            symbols = cfg.symbols

    calib = BacktestResult()
    test = BacktestResult()
    whole = BacktestResult()
    failed = 0

    for sym in symbols:
        try:
            df = storage.load(cfg.name, sym, timeframe)
            if df is None or len(df) < cfg.candles * 0.5:
                if args.offline:
                    continue
                df = storage.merge(df, adapter.fetch(sym, timeframe, cfg.candles))
                storage.save(cfg.name, sym, timeframe, df)
        except Exception:  # noqa: BLE001
            failed += 1
            continue

        if df is None or len(df) < 400:
            continue

        whole.trades.extend(run(df, sym, timeframe, cfg).closed)
        if args.split:
            mid = len(df) // 2
            calib.trades.extend(run(df.iloc[:mid], sym, timeframe, cfg).closed)
            test.trades.extend(run(df.iloc[mid:], sym, timeframe, cfg).closed)

    print(f"\nالرموز: {len(symbols)} · تعذّر {failed}")
    print(f"الفريم: {timeframe} · الشموع لكل رمز: {cfg.candles}")
    print(f"العتبة: {cfg.normal_threshold} · أقل التقاء: {cfg.min_confluence} · "
          f"فلتر الفريم الأعلى: {'مفعّل' if cfg.require_htf else 'معطّل'}")

    print("\n=== الفترة كاملة ===")
    print(_fmt(whole.summary()))

    if args.split:
        print("\n=== فترة المعايرة (النصف الأول) ===")
        print(_fmt(calib.summary()))
        print("\n=== فترة الاختبار المستقل (النصف الثاني) ===")
        print(_fmt(test.summary()))
        print("\nإن كان أداء الاختبار أسوأ بكثير من المعايرة، فالإعدادات مُفصّلة على الماضي.")

    tbl = whole.by_confluence()
    if not tbl.empty:
        print("\n=== الأداء حسب عدد عناصر الالتقاء ===")
        print(tbl.to_string())
        print("لا تُبنى قرارات على صفوف عدد صفقاتها أقل من 30.")

    if whole.closed:
        rows = [{
            "symbol": t.symbol, "entry_time": t.entry_time, "exit_time": t.exit_time,
            "entry": t.entry, "sl": t.initial_sl, "tp2": t.tp2,
            "r": round(t.r_multiple, 3), "tp1_hit": t.tp1_hit,
            "confluence": t.confluence, "reason": t.reason,
        } for t in whole.closed]
        out = Path("reports"); out.mkdir(exist_ok=True)
        path = out / f"backtest_{cfg.name}_{timeframe}.csv"
        pd.DataFrame(rows).to_csv(path, index=False)
        print(f"\nتفاصيل الصفقات: {path}")

    if args.walkforward:
        folds = []
        for sym in symbols:
            df = storage.load(cfg.name, sym, timeframe)
            if df is None or len(df) < args.wf_train + args.wf_test + 100:
                continue
            folds.extend(wf_run_symbol(
                df, sym, timeframe, cfg,
                train_window=args.wf_train, test_window=args.wf_test,
                step=args.wf_step, warmup=300))
        agg = wf_aggregate(folds)
        print("\n=== Walk-Forward (OOS) ===")
        print(f"folds={agg['folds']} · oos_mean={agg['oos_expectancy_mean']}")
        print(f"oos_std={agg['oos_expectancy_std']} · "
              f"oos_positive={agg['oos_positive_ratio']}% · "
              f"worst={agg['oos_worst_fold']}")

    s = whole.summary()
    if s.get("trades", 0) < 100:
        print(f"\n⚠ العينة {s.get('trades', 0)} صفقة — دون الحد الأدنى (100) لأي استنتاج.")
    elif s["avg_r"] <= 0:
        print(f"\n⚠ متوسط R سالب ({s['avg_r']:+.2f}). لا تتوسّع قبل معايرة العتبات والأوزان.")
    else:
        print(f"\n✓ متوسط R موجب ({s['avg_r']:+.2f}) على {s['trades']} صفقة.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
