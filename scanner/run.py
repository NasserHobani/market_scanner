"""نقطة الدخول.

    python -m scanner.run --market crypto                 # كل أزواج USDT
    python -m scanner.run --market crypto --top 100       # أعلى 100 بحجم التداول
    python -m scanner.run --market crypto --universe list # قائمة الإعدادات فقط
    python -m scanner.run --market crypto --timeframe 1d --no-cache
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

try:
    from . import storage
    from .adapters import get_adapter
    from .config import MarketConfig, load_market
    from . import live
    from .outputs import html_report, telegram
    from .report import print_table, to_frame, tradingview_link, write_csv
    from .scoring import score_symbol
except ImportError as _exc:  # pragma: no cover
    if "relative import" not in str(_exc):
        raise
    print(
        "\nلا تشغّل هذا الملف بمساره — بايثون لا يتعرّف على الحزمة فتنكسر الاستيرادات.\n"
        "\nمن مجلد المشروع، استخدم أحد هذين:\n"
        "    python main.py --market crypto --html\n"
        "    python -m scanner.run --market crypto --html\n"
        "\nأو انقر run.bat على ويندوز.\n",
        file=sys.stderr,
    )
    raise SystemExit(2) from None

MIN_CANDLES = 60


def resolve_symbols(cfg: MarketConfig, adapter, override: str | None, top_n: int | None,
                    diagnose: bool = False) -> list[str]:
    mode = override or cfg.universe
    if mode == "list":
        return cfg.symbols
    symbols = adapter.usdt_universe(
        min_quote_volume=cfg.min_quote_volume,
        top_n=top_n or cfg.top_n,
        diagnose=diagnose,
    )
    if not symbols:
        raise RuntimeError("لم يُرجع Binance أي أزواج تطابق شرط حجم التداول")
    return symbols


def _process(adapter, cfg: MarketConfig, symbol: str, timeframe: str, use_cache: bool):
    cached = storage.load(cfg.name, symbol, timeframe) if use_cache else None
    fresh = adapter.fetch(symbol, timeframe, cfg.candles)
    df = storage.merge(cached, fresh)
    storage.save(cfg.name, symbol, timeframe, df)
    if len(df) < MIN_CANDLES:
        raise ValueError(f"شموع غير كافية ({len(df)})")
    return score_symbol(df, symbol, timeframe, cfg)


def scan(cfg: MarketConfig, symbols: list[str], timeframe: str,
         use_cache: bool = True, verbose: bool = True):
    adapter = get_adapter(cfg.adapter)
    results, failures = [], []
    done = 0
    total = len(symbols)

    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {
            pool.submit(_process, adapter, cfg, sym, timeframe, use_cache): sym
            for sym in symbols
        }
        for fut in as_completed(futures):
            sym = futures[fut]
            done += 1
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                failures.append((sym, str(exc)))
            if verbose and (done % 25 == 0 or done == total):
                print(f"  {done}/{total} ...", flush=True)

    return results, failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ماسح الأسواق")
    ap.add_argument("--market", default="crypto", help="اسم ملف الإعدادات في config/")
    ap.add_argument("--timeframe", default=None, help="تجاوز الفريم المحدد في الإعدادات")
    ap.add_argument("--universe", choices=["auto", "list"], default=None)
    ap.add_argument("--top", type=int, default=None, help="أعلى N زوج بحجم التداول")
    ap.add_argument("--no-cache", action="store_true", help="تجاهل البيانات المخزنة")
    ap.add_argument("--html", action="store_true", help="تقرير HTML قابل للفرز")
    ap.add_argument("--notify", action="store_true", help="إرسال أفضل الفرص إلى تيليجرام")
    ap.add_argument("--top-alerts", type=int, default=5, help="عدد الفرص في رسالة التنبيه")
    ap.add_argument("--diagnose", action="store_true",
                    help="أظهر مسار تصفية الرموز ولماذا استُبعد كل منها")
    ap.add_argument("--live", action="store_true",
                    help="متابعة مستمرة: يمسح تلقائياً عند إغلاق كل شمعة")
    ap.add_argument("--every", type=int, default=None,
                    help="بدل انتظار الإغلاق، امسح كل N دقيقة (للتجربة فقط)")
    ap.add_argument("--cycles", type=int, default=0,
                    help="توقّف بعد N دورة (0 = بلا حد)")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    cfg_path = Path("config") / f"{args.market}.yaml"
    if not cfg_path.exists():
        print(f"ملف الإعدادات غير موجود: {cfg_path}", file=sys.stderr)
        return 1

    cfg = load_market(cfg_path)
    adapter = get_adapter(cfg.adapter)

    try:
        symbols = resolve_symbols(cfg, adapter, args.universe, args.top, args.diagnose)
    except NotImplementedError:
        symbols = cfg.symbols          # محوّلات بلا اكتشاف تلقائي (Yahoo)
    except Exception as exc:  # noqa: BLE001
        print(f"تعذّر تحديد قائمة الرموز: {exc}", file=sys.stderr)
        return 1

    if not symbols:
        print("قائمة الرموز فارغة — أضف رموزاً في ملف الإعدادات.", file=sys.stderr)
        return 1

    if not args.quiet:
        mode = args.universe or cfg.universe
        extra = "" if mode == "list" else f" (حجم ≥ {cfg.min_quote_volume:,.0f}$)"
        print(f"الرموز: {len(symbols)}{extra}")

    timeframes = [args.timeframe] if args.timeframe else cfg.timeframes

    if args.live:
        return _live_loop(cfg, symbols, timeframes, args)

    return _one_pass(cfg, symbols, timeframes, args)


def _one_pass(cfg, symbols, timeframes, args, alert_state=None,
              refresh_seconds=None, next_scan=None) -> int:
    all_rows = []

    for tf in timeframes:
        if not args.quiet:
            print(f"\n=== {cfg.name} · {tf} ===")
        started = time.time()
        results, failures = scan(cfg, symbols, tf, use_cache=not args.no_cache,
                                 verbose=not args.quiet)
        elapsed = time.time() - started

        df = to_frame(results)
        if not df.empty:
            df["chart"] = [tradingview_link(cfg.adapter, s, tf) for s in df["symbol"]]
            all_rows.extend(df.to_dict("records"))
            print_table(df, cfg)

            if args.html:
                path = html_report.write(df, cfg.name, tf,
                                         refresh_seconds=refresh_seconds,
                                         next_scan=next_scan)
                print(f"تقرير HTML: {path}")

            if args.notify:
                to_alert = df
                if alert_state is not None:
                    bar = int(pd.Timestamp(df["timestamp"].iloc[0]).timestamp()
                              // live.timeframe_seconds(tf))
                    to_alert = alert_state.new_alerts(df, bar)
                    if to_alert.empty:
                        print("لا فرص جديدة — لم يُرسل تنبيه")
                if not to_alert.empty:
                    msg = telegram.format_message(
                        to_alert, cfg.name, tf, top=args.top_alerts,
                        threshold=cfg.normal_threshold,
                    )
                    if msg:
                        ok = telegram.send(msg)
                        print("تنبيه تيليجرام:", "أُرسل ✓" if ok else "لم يُرسل ✗")
        if not args.quiet:
            print(f"الزمن: {elapsed:.1f} ثانية · نجح {len(results)} · فشل {len(failures)}")
        if failures and not args.quiet:
            for sym, err in failures[:10]:
                print(f"  - {sym}: {err}")
            if len(failures) > 10:
                print(f"  ... و{len(failures) - 10} غيرها")

    if all_rows:
        combined = pd.DataFrame(all_rows).sort_values("score", ascending=False)
        report = write_csv(combined, cfg.name)
        archive = storage.archive_scan(cfg.name, all_rows)
        print(f"\nالتقرير: {report}")
        print(f"الأرشيف: {archive}")
    return 0


def _live_loop(cfg, symbols, timeframes, args) -> int:
    tf = timeframes[0]
    stopper = live.Stopper()
    state = live.AlertState()
    period_min = live.timeframe_seconds(tf) // 60

    print(f"\nوضع المتابعة الحية · {cfg.name} · {tf}")
    if args.every:
        print(f"المسح كل {args.every} دقيقة (وضع تجربة — قد تُقيَّم شمعة لم تُغلق)")
    else:
        print(f"المسح عند إغلاق كل شمعة ({period_min} دقيقة)")
    print("الإشارات تُقيَّم على الشموع المغلقة فقط. Ctrl+C للإيقاف.\n")

    cycle = 0
    while not stopper.stop:
        cycle += 1
        if args.cycles and cycle > args.cycles:
            break
        print(f"── دورة {cycle} · {live.utc_now_text()} " + "─" * 24)
        wait_hint = args.every * 60 if args.every else max(
            30, live.next_close(tf) - time.time() + 20)
        try:
            _one_pass(cfg, symbols, timeframes, args, alert_state=state,
                      refresh_seconds=int(wait_hint) + 15,
                      next_scan=live.format_wait(wait_hint))
        except Exception as exc:  # noqa: BLE001
            # خطأ شبكة عابر يجب ألا يُسقط المتابعة كلها
            print(f"تعذّرت الدورة: {exc} — سيُعاد المحاولة")

        if args.every:
            wait = args.every * 60
        else:
            # هامش 20 ثانية بعد الإغلاق حتى تستقر البيانات على الخادم
            wait = max(30, live.next_close(tf) - time.time() + 20)

        if args.cycles and cycle >= args.cycles:
            break
        print(f"\nالدورة القادمة بعد {live.format_wait(wait)}\n")
        if not stopper.sleep(wait):
            break

    print("توقفت المتابعة.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nتوقف بطلب المستخدم.")
        raise SystemExit(130)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        raise SystemExit(1)
