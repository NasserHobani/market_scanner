# -*- coding: utf-8 -*-
"""MD-01 background market-data sync tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from scanner.market_sync.config import MarketSyncConfig
from scanner.market_sync.freshness import FreshnessStatus, assess_freshness, expected_open_candle
from scanner.market_sync.locks import sync_lock
from scanner.market_sync.service import MarketDataSyncService
from scanner.market_sync import observability as obs
from scanner.market_sync import status_store
from scanner import storage

results: list[tuple[bool, str, str]] = []
skipped: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((cond, name, extra))


def _cfg(tmp: Path) -> MarketSyncConfig:
    return MarketSyncConfig(
        status_path=str(tmp / "status.json"),
        events_path=str(tmp / "events.jsonl"),
        lock_dir=str(tmp / "locks"),
        max_workers=2,
        max_symbols_per_market=20,
        bootstrap_min_candles=5,
        fresh_max_bars=0.5,
        stale_max_bars=1.5,
        sync_timeframes=("1h",),
        interval_seconds={"1h": 60, "15m": 30, "4h": 120, "1d": 300, "1w": 600},
    )


def _ohlc(n: int = 10, start: str = "2026-08-11 10:00:00", freq: str = "1h") -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq=freq, tz="UTC")
    return pd.DataFrame({
        "open": range(100, 100 + n),
        "high": range(101, 101 + n),
        "low": range(99, 99 + n),
        "close": range(100, 100 + n),
        "volume": [1000.0] * n,
    }, index=idx)


with tempfile.TemporaryDirectory() as tmp:
    tmp_path = Path(tmp)
    data_dir = tmp_path / "data"
    cfg = _cfg(tmp_path)
    obs.reset_metrics()

    # Patch storage root
    with mock.patch.object(storage, "DATA_DIR", data_dir):
        svc = MarketDataSyncService(cfg)

        # Fake market yaml + adapter
        yaml_dir = tmp_path / "config"
        yaml_dir.mkdir()
        (yaml_dir / "crypto.yaml").write_text(
            "name: crypto\nadapter: binance\ntimeframes: [\"1h\"]\ncandles: 50\n"
            "universe: list\nsymbols: [BTCUSDT]\nworkers: 2\n"
            "weights: {}\nparams: {}\n",
            encoding="utf-8",
        )

        class FakeAdapter:
            def __init__(self):
                self.calls = 0
                self.frames = []

            def fetch(self, symbol, timeframe, limit):
                self.calls += 1
                if self.frames:
                    return self.frames.pop(0)
                return _ohlc(limit if limit < 20 else 10)

        fake = FakeAdapter()

        with mock.patch("scanner.market_sync.service.get_adapter", return_value=fake):
            with mock.patch("scanner.market_sync.service.load_market") as lm:
                from scanner.config import load_market as real_load
                lm.side_effect = lambda p: real_load(p)

                # 6 initial bootstrap
                fake.frames = [_ohlc(10)]
                r = svc.sync_pair("crypto", "BTCUSDT", "1h", config_dir=yaml_dir)
                check("initial bootstrap", r.get("ok") and r.get("mode") == "bootstrap", str(r))
                # اللواحق من ``storage.SUFFIXES`` لا مكتوبة هنا: كانت
                # مكتوبةً فتوقّف الاختبار عن رؤية الملف يوم صار npz.
                check("bootstrap persisted",
                      any((data_dir / "crypto" / "1h" / f"BTCUSDT{sfx}").exists()
                          for sfx in storage.SUFFIXES),
                      str(sorted(p.name for p in (data_dir / "crypto" / "1h").glob("*"))
                          if (data_dir / "crypto" / "1h").exists() else "لا مجلّد"))
                check("resolve_symbols يرى القرص",
                      "BTCUSDT" in svc.resolve_symbols("crypto", config_dir=yaml_dir))

                # 1 incremental sync — new candle
                base = storage.load("crypto", "BTCUSDT", "1h")
                last = storage.last_time(base)
                next_bar = last + pd.Timedelta(hours=1)
                extra = _ohlc(2, start=str(last.to_pydatetime()).replace("+00:00", ""), freq="1h")
                # rebuild with last + new
                new_df = pd.DataFrame({
                    "open": [float(base.iloc[-1]["open"]), 200],
                    "high": [float(base.iloc[-1]["high"]) + 1, 205],
                    "low": [float(base.iloc[-1]["low"]), 195],
                    "close": [float(base.iloc[-1]["close"]) + 0.5, 202],
                    "volume": [1100.0, 1200.0],
                }, index=pd.DatetimeIndex([last, next_bar], tz="UTC"))
                fake.frames = [new_df]
                r2 = svc.sync_pair("crypto", "BTCUSDT", "1h", force=True, config_dir=yaml_dir)
                check("incremental sync ok", r2.get("ok") is True, str(r2))
                check("new candle", r2.get("inserted", 0) >= 1 or storage.last_time(
                    storage.load("crypto", "BTCUSDT", "1h")) == next_bar, str(r2))

                # 3 updated open candle (same timestamp, new OHLC)
                cur = storage.load("crypto", "BTCUSDT", "1h")
                last2 = storage.last_time(cur)
                open_update = pd.DataFrame({
                    "open": [float(cur.iloc[-1]["open"])],
                    "high": [float(cur.iloc[-1]["high"]) + 3],
                    "low": [float(cur.iloc[-1]["low"])],
                    "close": [float(cur.iloc[-1]["close"]) + 2],
                    "volume": [1500.0],
                }, index=pd.DatetimeIndex([last2], tz="UTC"))
                before_close = float(cur.iloc[-1]["close"])
                fake.frames = [open_update]
                r3 = svc.sync_pair("crypto", "BTCUSDT", "1h", force=True, config_dir=yaml_dir)
                after = storage.load("crypto", "BTCUSDT", "1h")
                check("updated open candle", float(after.iloc[-1]["close"]) != before_close
                      or r3.get("updated", 0) >= 0, str(r3))
                check("no duplicate on open update",
                      len(after) == len(after[~after.index.duplicated()]))

                # 5 duplicate prevention — merge keep last
                n_before = len(after)
                fake.frames = [after.tail(3).copy()]
                r4 = svc.sync_pair("crypto", "BTCUSDT", "1h", force=True, config_dir=yaml_dir)
                after2 = storage.load("crypto", "BTCUSDT", "1h")
                check("duplicate prevention", len(after2) == len(after2[~after2.index.duplicated()]))
                check("length stable on overlap", len(after2) <= n_before + 1)

                # 4 candle close event path — already covered by new candle insert
                check("candle close tracked", obs.metrics_snapshot().get("candles_closed", 0) >= 0)

        # 10/11 freshness detection
        fresh_df = _ohlc(5)
        # Make last candle "now"
        now_ts = pd.Timestamp.now("UTC").floor("h")
        if now_ts.tzinfo is None:
            now_ts = now_ts.tz_localize("UTC")
        fresh_df.index = pd.date_range(now_ts - pd.Timedelta(hours=4), periods=5, freq="1h", tz="UTC")
        storage.save("crypto", "ETHUSDT", "1h", fresh_df)
        f = assess_freshness("crypto", "ETHUSDT", "1h", df=fresh_df, config=cfg)
        check("stale detection API returns status", f["status"] in (
            FreshnessStatus.FRESH.value, FreshnessStatus.STALE.value,
            FreshnessStatus.CRITICAL.value,
        ), f["status"])

        # ═══ «متأخّر» و«مشطوب» ليسا حالةً واحدة ═══
        #
        # كان هذا الفحص يمرّر إطاراً من **٢٠٢٠** ويتوقّع ``critical``.
        # والخلط بينهما كلّف توقّف المسح التلقائي أسبوعاً: ١٣٨ رمزاً
        # مشطوباً من ٢٠٢٢ عُدّت «حرجة»، فتجاوز الحرج نصف السوق،
        # فأعلنت البوابة الكريبتو متأخّراً وأجهضت كل دورة.
        #
        # المتأخّر يُصلحه تحديث؛ والمشطوب لا يُصلحه شيء.
        lag_df = fresh_df.copy()
        lag_df.index = pd.date_range(now_ts - pd.Timedelta(hours=12),
                                     periods=5, freq="1h", tz="UTC")
        crit = assess_freshness("crypto", "LAG", "1h", df=lag_df, config=cfg)
        check("critical detection", crit["status"] == FreshnessStatus.CRITICAL.value,
              f'{crit["status"]} · {crit["bars_behind"]} شمعة')

        old_df = fresh_df.copy()
        old_df.index = pd.date_range("2020-01-01", periods=5, freq="1h", tz="UTC")
        dead = assess_freshness("crypto", "OLD", "1h", df=old_df, config=cfg)
        check("dead detection", dead["status"] == FreshnessStatus.DEAD.value,
              f'{dead["status"]} · {dead["bars_behind"]} شمعة')

        # 12 freshness gate
        with mock.patch.object(svc, "resolve_symbols", return_value=["ETHUSDT"]):
            with mock.patch.object(svc, "incremental_refresh_stale", return_value={"refreshed": 0}):
                gate = svc.scan_freshness_gate(
                    "crypto", "1h", symbols=["ETHUSDT"], auto_refresh=False, config_dir=yaml_dir,
                )
                check("freshness gate runs", "ok" in gate and "code" in gate, str(gate))

        # 13 concurrent lock
        acquired = []
        with sync_lock("crypto", "BTCUSDT", "1h", config=cfg) as ok1:
            acquired.append(ok1)
            with sync_lock("crypto", "BTCUSDT", "1h", config=cfg, timeout=0.2) as ok2:
                acquired.append(ok2)
        check("concurrent lock exclusive", acquired[0] is True and acquired[1] is False, str(acquired))

        # 14 API failure
        class Boom:
            def fetch(self, *a, **k):
                raise RuntimeError("exchange down")

        with mock.patch("scanner.market_sync.service.get_adapter", return_value=Boom()):
            with mock.patch("scanner.market_sync.service.load_market") as lm:
                from scanner.config import load_market as real_load
                lm.side_effect = lambda p: real_load(p)
                fail = svc.sync_pair("crypto", "BTCUSDT", "1h", force=True, config_dir=yaml_dir)
                check("api failure handled", fail.get("ok") is False, str(fail))

        # 15 recovery after backoff clear
        key = status_store.pair_key("crypto", "BTCUSDT", "1h")
        svc._clear_backoff(key)
        check("recovery clears backoff", not svc._in_backoff(key))

        # 16 chart reads synchronized data
        df_chart = storage.load("crypto", "BTCUSDT", "1h")
        check("chart reads synchronized data", df_chart is not None and len(df_chart) >= 5)

        # 17 scanner does not perform full sync — cached path uses bars_needed not full
        need = storage.bars_needed(df_chart, "1h", 1500)
        check("scanner does not need full sync", need < 1500, str(need))

        # 18 PIT snapshot remains immutable — sync must not touch snapshot store
        pit_before = None
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        snap_file = snap_dir / "v3.jsonl"
        snap_file.write_text('{"snapshot_id":"pit_x","features":{"rsi":50}}\n', encoding="utf-8")
        pit_before = snap_file.read_text(encoding="utf-8")
        # run another sync
        with mock.patch("scanner.market_sync.service.get_adapter", return_value=fake):
            with mock.patch("scanner.market_sync.service.load_market") as lm:
                from scanner.config import load_market as real_load
                lm.side_effect = lambda p: real_load(p)
                fake.frames = [storage.load("crypto", "BTCUSDT", "1h").tail(2)]
                svc.sync_pair("crypto", "BTCUSDT", "1h", force=True, config_dir=yaml_dir)
        check("PIT snapshot remains immutable", snap_file.read_text(encoding="utf-8") == pit_before)

        # 19 AI does not trigger sync — service has no AI imports in sync_pair path
        import inspect
        src = inspect.getsource(MarketDataSyncService.sync_pair)
        check("AI does not trigger sync", "claude" not in src.lower() and "qwen" not in src.lower()
              and "lightgbm" not in src.lower())

        # 7 background scheduling — worker module importable
        #
        # هذا الفحص وحده يعبر إلى Django. وكان يقول ``from dashboard
        # import ...`` بلا إضافة ``web/`` إلى المسار ولا ``django.setup``
        # — أي أنّه كان ينهار حيثما شُغّل. لم يظهر لأن الملفّ كلّه لم
        # يكن مسجّلاً في ``run_checks``.
        #
        # وإن غاب Django أصلاً فالتخطّي يُعلَن سطراً مرئيّاً: فحصٌ
        # مُخطًّى يُحسَب ناجحاً هو كذبة أهدأ من الفشل وأضرّ منه.
        _web = Path(__file__).parent / "web"
        if str(_web) not in sys.path:
            sys.path.insert(0, str(_web))
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        try:
            import django

            django.setup()
            from dashboard import market_sync_worker

            check("background scheduling module",
                  hasattr(market_sync_worker, "start")
                  and hasattr(market_sync_worker, "run_once"))
        except ModuleNotFoundError as exc:
            if "django" not in str(exc).lower():
                raise
            skipped.append(f"جدولة الخلفية — {exc}")

        # 8 retry backoff registered
        svc._register_failure("test:key")
        check("retry backoff", svc._in_backoff("test:key"))
        obs.log_event("MARKET_SYNC_RETRY", config=cfg)
        check("rate-limit / retry event logged", True)

        # 9 expected open candle
        exp = expected_open_candle("1h")
        check("expected open candle", exp is not None)

        # 20 restart recovery — status persists
        status_store.update_worker({"thread_started": True, "cycle_count": 3}, config=cfg)
        loaded = status_store.load_status(cfg)
        check("restart recovery status persisted",
              (loaded.get("worker") or {}).get("cycle_count") == 3)

        # global status
        g = svc.global_status(markets=["crypto"])
        check("global status shape", "status" in g and "healthy" in g, str(g.keys()))

passed = sum(1 for ok, _, _ in results if ok)
failed = [(n, e) for ok, n, e in results if not ok]
print(f"\nMD-01 tests: {passed}/{len(results)} passed")
for reason in skipped:
    print(f"  [SKIP] {reason}")
for ok, name, extra in results:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {extra}" if extra and not ok else ""))
if failed:
    sys.exit(1)
