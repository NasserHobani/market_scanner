# -*- coding: utf-8 -*-
"""تشغيل الاختبار الخلفي للتوصية الحقيقية.

    python -m scanner.backtest.reco_run --market crypto --timeframe 4h
    python -m scanner.backtest.reco_run --split --step 10

التوازي بالعمليات لا الخيوط: العمل معالجة بحتة، والخيوط تتنازع على GIL
فتُبطئه (قيس ×0.65 في هذا المشروع). والرموز مستقلة تماماً فالتقسيم
عليها طبيعي.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scanner import storage
from scanner.backtest import recobt
from scanner.backtest.baselines import run_baselines
from scanner.backtest.experiments import create_id, log_event
from scanner.backtest.walkforward import aggregate as wf_aggregate
from scanner.backtest.walkforward import run_symbol as wf_run_symbol
from scanner.config import load_market

_STATE: dict = {}


def _init(market: str, timeframe: str, step: int, warmup: int,
          half: str | None, htf: bool = True):
    cfg = load_market(ROOT / "config" / f"{market}.yaml")
    # المقارنة أ/ب تتطلّب تغيير عامل واحد فقط على العيّنة نفسها
    cfg.require_htf = bool(htf)
    _STATE.update(market=market, timeframe=timeframe, step=step,
                  warmup=warmup, half=half, cfg=cfg)


def _one(symbol: str):
    """تُنفَّذ في عملية مستقلة — لذلك تقرأ من القرص بنفسها."""
    st = _STATE
    df = storage.load(st["market"], symbol, st["timeframe"])
    if df is None or len(df) < st["warmup"] + 60:
        return symbol, [], "تاريخ قصير"

    start = end = None
    if st["half"]:
        mid = len(df) // 2
        if st["half"] == "in":
            end = mid
        else:
            start = max(st["warmup"], mid)

    try:
        sigs = recobt.scan_symbol(df, symbol, st["timeframe"], st["cfg"],
                                  step=st["step"], warmup=st["warmup"],
                                  start=start, end=end)
    except Exception as exc:  # noqa: BLE001
        return symbol, [], str(exc)[:80]
    return symbol, sigs, ""


def _line(title: str, s: dict) -> str:
    if not s["closed"]:
        return f"  {title:<22} لا صفقات محسومة ({s['total']} خطة)"
    risk = (f" · DD {s.get('max_drawdown_r', 0):.1f}R"
            f" · Sharpe {s.get('sharpe') if s.get('sharpe') is not None else '—'}"
            f" · Recovery {s.get('recovery_factor') if s.get('recovery_factor') is not None else '—'}")
    return (f"  {title:<22} {s['closed']:>4} صفقة · نجاح {s['win_rate']:>5.1f}% "
            f"({s['win_rate_low']:.0f}–{s['win_rate_high']:.0f}) · "
            f"توقّع {s['expectancy']:+.2f}R · حصيلة {s['total_r']:+.1f}R"
            + risk
            + ("" if s["reliable"] else "  ⚠عيّنة صغيرة"))


def _print_rows(rows: list[dict], label: str, min_n: int) -> dict:
    """التلخيص من صفوف خام — لتعمل على المحفوظ كما على المحسوب للتوّ."""
    from scanner.tracking import split, split_multi, summarize

    rep = {
        "overall": summarize(rows),
        "by_grade": split(rows, "grade", min_n=min_n),
        "by_action": split(rows, "action", min_n=min_n),
        "by_factor": split_multi(rows, "factors", min_n=min_n),
    }
    o = rep["overall"]
    print(f"\n{'═' * 74}\n{label}\n{'═' * 74}")
    print(_line("الإجمالي", o))
    print(f"  {'':<22} مفتوحة {o['open']} · تنتظر {o['pending']} · "
          f"لم تُفعَّل {o['expired']}")
    for key, title in (("by_grade", "حسب التصنيف"),
                       ("by_action", "حسب نوع التوصية"),
                       ("by_factor", "حسب سبب الدخول")):
        part = rep.get(key) or []
        if not part:
            continue
        print(f"\n  ── {title} ──")
        for r in part:
            print(_line(str(r["value"]), r))
    return rep


def _cache_path(market: str, timeframe: str, step: int, half: str | None,
                suffix: str = "") -> Path:
    out = ROOT / "data" / "backtest"
    out.mkdir(parents=True, exist_ok=True)
    tag = half or "all"
    extra = f"_{suffix}" if suffix else ""
    return out / f"reco_{market}_{timeframe}_s{step}_{tag}{extra}.jsonl"


def _load_cache(path: Path) -> dict[str, list[dict]]:
    """نتائج رموز أُنجزت سابقاً — الاختبار على مئات الرموز يستغرق دقائق،
    وإعادته من الصفر بعد كل انقطاع تُهدر العمل كله."""
    done: dict[str, list[dict]] = {}
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue        # سطر نصف مكتوب من انقطاع سابق
            done[rec["symbol"]] = rec.get("rows", [])
    return done


def _append(path: Path, symbol: str, signals) -> None:
    with path.open("a", encoding="utf-8") as fh:
        rows = [{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                 for k, v in s.as_row().items()} for s in signals]
        fh.write(json.dumps({"symbol": symbol, "rows": rows},
                            ensure_ascii=False) + "\n")


def _load_symbol_data(market: str, timeframe: str, symbols: list[str], half: str | None) -> dict[str, object]:
    data: dict[str, object] = {}
    for sym in symbols:
        df = storage.load(market, sym, timeframe)
        if df is None or len(df) < 100:
            continue
        if half:
            mid = len(df) // 2
            df = df.iloc[:mid] if half == "in" else df.iloc[mid:]
        data[sym] = df
    return data


def _print_baselines(market: str, timeframe: str, symbols: list[str], half: str | None,
                     warmup: int, seed: int) -> list[dict]:
    data = _load_symbol_data(market, timeframe, symbols, half)
    summaries = run_baselines(data, timeframe, warmup=warmup, seed=seed)
    rows: list[dict] = []
    if summaries:
        print("\n  ── المقارنة مع خطوط الأساس ──")
    for item in summaries:
        s = item.stats
        print(_line(item.name, s))
        rows.append({"name": item.name, "expectancy": s.get("expectancy"),
                     "total_r": s.get("total_r"), "closed": s.get("closed")})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="اختبار خلفي لمحرّك التوصية الذي تعرضه اللوحة")
    ap.add_argument("--market", default="crypto")
    ap.add_argument("--timeframe", default="4h")
    ap.add_argument("--step", type=int, default=10,
                    help="كم شمعة نقفز بين تقييم وآخر (1 = كل شمعة)")
    ap.add_argument("--warmup", type=int, default=400)
    ap.add_argument("--limit", type=int, default=0, help="أقصى عدد رموز")
    ap.add_argument("--workers", type=int, default=0, help="0 = عدد الأنوية")
    ap.add_argument("--min-n", type=int, default=5,
                    help="أقلّ عيّنة لعرض شريحة")
    ap.add_argument("--split", action="store_true",
                    help="نصف للمعايرة ونصف للاختبار المستقل")
    ap.add_argument("--budget", type=float, default=0.0,
                    help="أقصى ثوانٍ لكل نصف؛ الباقي يُستأنف في تشغيل لاحق")
    ap.add_argument("--fresh", action="store_true",
                    help="تجاهل النتائج المحفوظة وابدأ من الصفر")
    ap.add_argument("--report-only", action="store_true",
                    help="اعرض ملخّص المحفوظ بلا حساب جديد")
    ap.add_argument("--no-htf", action="store_true",
                    help="أطفئ فلتر الفريم الأعلى (للمقارنة أ/ب)")
    ap.add_argument("--tag", default="",
                    help="لاحقة لملف النتائج، لفصل تجربة عن أخرى")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--hypothesis", default="reco engine evaluation")
    ap.add_argument("--walkforward", action="store_true",
                    help="تشغيل تقييم Walk-Forward بعد التقرير")
    ap.add_argument("--wf-train", type=int, default=700)
    ap.add_argument("--wf-test", type=int, default=250)
    ap.add_argument("--wf-step", type=int, default=125)
    args = ap.parse_args(argv)

    base = ROOT / "data" / args.market / args.timeframe
    symbols = sorted(p.stem for p in base.glob("*.csv"))
    symbols += sorted(p.stem for p in base.glob("*.parquet"))
    symbols = sorted(set(symbols))
    if args.limit:
        symbols = symbols[: args.limit]
    if not symbols:
        print(f"لا بيانات مخزّنة في {base}")
        return 1

    import os

    workers = args.workers or max(1, (os.cpu_count() or 2))
    halves = [None] if not args.split else ["in", "out"]
    dataset = {"market": args.market, "timeframe": args.timeframe,
               "symbols": len(symbols), "split": bool(args.split)}
    cfg_for_hash = vars(args).copy()
    experiment_id = create_id(args.hypothesis, dataset, cfg_for_hash, args.seed)
    log_event(
        experiment_id=experiment_id,
        hypothesis=args.hypothesis,
        dataset=dataset,
        config=cfg_for_hash,
        seed=args.seed,
        stage="start",
        metrics={"symbols": len(symbols)},
        decision="running",
        meta={"cache_tag": args.tag},
    )

    for half in halves:
        htf_note = " · بلا فلتر الفريم الأعلى" if args.no_htf else ""
        label = {None: f"{args.market} · {args.timeframe} · كل التاريخ" + htf_note,
                 "in": "النصف الأول — للمعايرة",
                 "out": "النصف الثاني — اختبار مستقل لم يُعايَر عليه"}[half]
        suffix = args.tag or ("nohtf" if args.no_htf else "")
        cache_file = _cache_path(args.market, args.timeframe, args.step,
                                 half, suffix)
        if args.fresh and cache_file.exists():
            cache_file.unlink()
        cached = _load_cache(cache_file)
        todo = [s for s in symbols if s not in cached]

        errors = []
        if todo and not args.report_only:
            deadline = (time.time() + args.budget) if args.budget else None
            with ProcessPoolExecutor(
                max_workers=workers, initializer=_init,
                initargs=(args.market, args.timeframe, args.step,
                          args.warmup, half, not args.no_htf),
            ) as pool:
                futures = {pool.submit(_one, s): s for s in todo}
                for i, fut in enumerate(as_completed(futures), 1):
                    sym, sigs, err = fut.result()
                    _append(cache_file, sym, sigs)
                    cached[sym] = [s.as_row() for s in sigs]
                    if err:
                        errors.append(f"{sym}: {err}")
                    print(f"  … {len(cached)}/{len(symbols)}  {sym:<14} "
                          f"{len(sigs)} خطة", end="\r", flush=True)
                    if deadline and time.time() > deadline:
                        for f in futures:
                            f.cancel()
                        break
        print(" " * 70, end="\r")

        rows = [r for rs in cached.values() for r in rs]
        remaining = len(symbols) - len(cached)
        head = f"{label}   [{len(cached)}/{len(symbols)} رمز]"
        rep = _print_rows(rows, head, args.min_n)
        baseline_rows = _print_baselines(
            args.market, args.timeframe, symbols, half, args.warmup, args.seed)
        overall_exp = rep["overall"].get("expectancy")
        baseline_best = max([b.get("expectancy") for b in baseline_rows
                            if b.get("expectancy") is not None], default=None)
        if overall_exp is not None and baseline_best is not None:
            gate = overall_exp > baseline_best
            print(f"\n  بوابة الأساس: استراتيجية التوصية {'تتفوّق' if gate else 'لا تتفوّق'} "
                  f"(reco={overall_exp:+.2f}R vs best_baseline={baseline_best:+.2f}R)")
        if remaining > 0:
            print(f"\n  بقي {remaining} رمزاً — أعد التشغيل نفسه ليُستأنف "
                  f"(النتائج محفوظة في {cache_file.name})")
        if errors:
            print(f"  تعذّر {len(errors)}: " + " · ".join(errors[:3]))
        log_event(
            experiment_id=experiment_id,
            hypothesis=args.hypothesis,
            dataset=dataset | {"half": half or "all"},
            config=cfg_for_hash,
            seed=args.seed,
            stage=f"half_{half or 'all'}",
            metrics={
                "overall": rep["overall"],
                "baselines": baseline_rows,
                "cached_symbols": len(cached),
                "remaining_symbols": remaining,
            },
            decision="ok",
            meta={"errors": errors[:10]},
        )

    if args.walkforward:
        cfg = load_market(ROOT / "config" / f"{args.market}.yaml")
        fold_rows = []
        for sym in symbols:
            df = storage.load(args.market, sym, args.timeframe)
            if df is None or len(df) < (args.wf_train + args.wf_test + 100):
                continue
            fold_rows.extend(wf_run_symbol(
                df, sym, args.timeframe, cfg, args.wf_train, args.wf_test, args.wf_step))
        agg = wf_aggregate(fold_rows)
        print("\n" + "═" * 74)
        print("Walk-Forward (OOS)")
        print("═" * 74)
        print(f"  Folds: {agg['folds']} · OOS mean {agg['oos_expectancy_mean']}")
        print(f"  OOS std: {agg['oos_expectancy_std']} · Positive folds: {agg['oos_positive_ratio']}%")
        print(f"  Worst fold: {agg['oos_worst_fold']} · Stable: {'yes' if agg['stable'] else 'no'}")
        if agg.get("oos_expectancy_mean") is not None:
            print(f"  بوابة OOS: {'PASS' if agg['oos_expectancy_mean'] > 0 else 'FAIL'}")
        log_event(
            experiment_id=experiment_id,
            hypothesis=args.hypothesis,
            dataset=dataset,
            config=cfg_for_hash,
            seed=args.seed,
            stage="walkforward",
            metrics=agg,
            decision="pass" if (agg.get("oos_expectancy_mean") or -1) > 0 else "reject",
            meta={},
        )

    print("\nالحسم بنفس قواعد الصفقات الحيّة: الهدف الأول قبل الوقف = ربح، "
          "\nوالشمعة التي تلمس الاثنين تُحتسب خسارة.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
