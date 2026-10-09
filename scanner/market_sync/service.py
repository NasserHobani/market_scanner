# -*- coding: utf-8 -*-
"""MarketDataSyncService — incremental candle sync only (no AI / scan / trading)."""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from scanner import storage, tf_prefs
from scanner.adapters import get_adapter
from scanner.config import load_market
from scanner.live import UI_TIMEFRAMES

from .config import DEFAULT_SYNC_CONFIG, MarketSyncConfig
from .freshness import FreshnessStatus, assess_freshness, utc_now_iso
from .locks import sync_lock
from . import observability as obs
from . import status_store

log = logging.getLogger("scanner.market_sync")

_SERVICE: MarketDataSyncService | None = None


def _config_dir(explicit: Path | None) -> Path:
    """مجلّد الإعدادات — من المُعطى، وإلاّ من إعدادات Django.

    ═══ لماذا دالّة ═══

    كانت ثلاثة توابع تبدأ بـ ``from django.conf import settings``
    قبل أن تنظر هل مُرِّر ``config_dir`` أصلاً. فإن مُرِّر — وهو حال
    كلّ اختبار — استُورد Django بلا حاجة، وفشل الاستيراد يُجهض
    المزامنة كاملةً برسالة ``No module named 'django'`` لا صلة لها
    بالمزامنة. وحزمة ``scanner`` موصوفة بأنّها بلا Django، فكان
    هذا خرقاً صامتاً للوصف.

    الآن: إن أُعطي المسار فلا استيراد. وإن لم يُعط ولا Django،
    نسقط إلى ``config/`` بجوار الجذر بدل الانهيار.
    """
    if explicit is not None:
        return Path(explicit)
    try:
        from django.conf import settings as dj

        return Path(dj.SCANNER_CONFIG_DIR)
    except Exception:
        return Path(__file__).resolve().parents[2] / "config"


# ذاكرة قصيرة لحالة البيانات — انظر ``global_status``.
# مفتاحها الأسواق المطلوبة، وقيمتها (وقت الحساب، النتيجة).
_STATUS_CACHE: dict[str, tuple[float, dict]] = {}


# خيوط تحديث جارية — واحد لكل مفتاح. بلا هذا يبدأ كل طلب خيطاً،
# فيتحوّل الحلّ إلى مشكلة أشدّ من الأصل.
_REFRESHING: set[str] = set()
_REFRESH_LOCK = threading.Lock()


def _refresh_in_background(service, markets, key: str) -> bool:
    """يبدأ تحديثاً خلفياً. يعيد True إن أمكن إرجاع القديم."""
    with _REFRESH_LOCK:
        if key in _REFRESHING:
            return True                 # تحديث جارٍ — القديم يكفي
        _REFRESHING.add(key)

    def run() -> None:
        try:
            service.global_status(markets=markets)
        except Exception:  # noqa: BLE001
            pass
        finally:
            with _REFRESH_LOCK:
                _REFRESHING.discard(key)

    threading.Thread(target=run, name=f"sync-status-{key}",
                     daemon=True).start()
    return True


def get_service(config: MarketSyncConfig | None = None) -> MarketDataSyncService:
    global _SERVICE
    if config is not None and config is not DEFAULT_SYNC_CONFIG:
        return MarketDataSyncService(config)
    if _SERVICE is None:
        _SERVICE = MarketDataSyncService(DEFAULT_SYNC_CONFIG)
    return _SERVICE


# ═══════════════════════════════════════════════════════════════
#  ضبط فريمات المزامنة من الواجهة
# ═══════════════════════════════════════════════════════════════
#
# صيغة الإعداد سطرٌ واحد، سوقٌ لكل جزء — والمسافة تفصل كالسطر:
#
#     crypto=4h,1d saudi=1d gold=4h,1d
#
# والسوق غير المذكور يبقى على الافتراض. وهذا مقصود: من أراد
# تقليل الكريبتو وحده لا يُجبَر على كتابة الأسواق الأربعة.
#
# ═══ ولماذا نصٌّ لا أربع خانات لكل سوق ═══
#
# خمسة أسواق × أربعة فريمات = عشرون مفتاحاً في مخطّط الإعدادات،
# وكلّها تتغيّر بإضافة سوقٍ واحد. والسطر الواحد يتّسع لما يأتي
# بلا تعديل المخطّط.
#
# والتحليل نفسه انتقل إلى ``scanner.tf_prefs``: الماسح يحتاجه
# أيضاً، ونسخةٌ ثانية منه كانت ستنحرف عن هذه.

def _override_for(market: str) -> list[str]:
    """فريمات مزامنة هذا السوق من الإعدادات، أو قائمةٌ فارغة."""
    return tf_prefs.sync_for(market)


class MarketDataSyncService:
    """Synchronize OHLC from exchange → disk. Never runs AI/research/trading."""

    def __init__(self, config: MarketSyncConfig = DEFAULT_SYNC_CONFIG) -> None:
        self.config = config
        self._backoff: dict[str, dict[str, Any]] = {}

    # ── universe ──────────────────────────────────────────────

    def resolve_symbols(self, market: str, *, config_dir: Path | None = None) -> list[str]:
        """Active symbol universe — configured list + existing store files, capped."""
        cfg_dir = _config_dir(config_dir)
        cfg = load_market(cfg_dir / f"{market}.yaml")
        symbols: list[str] = []

        # ═══ الأحياء وحدهم يُزامَنون ═══
        #
        # الملف الباقي لرمزٍ مشطوب يبقى إلى الأبد، والجلب التراكمي
        # يطلب الناقص فلا يعود بشيء — كل دورة، بلا نهاية.
        #
        # وبلغ عدد هؤلاء ١٣٨ من ٥٣٤ في الكريبتو. أربعة فريمات لكلٍّ،
        # فأكثر من خمسمئة طلبٍ ضائع في كل دورة: هو ما ضخّم سجلّ
        # الأحداث إلى ٣٠٥ ميغابايت، وما جعل عامل المزامنة لا يلحق
        # الأحياء أبداً.
        #
        # والفحص من **ذيل الملف** لا بتحميله: قراءةٌ بأقلّ من مليّ
        # ثانية للرمز، ثمنٌ زهيد مقابل مئات الطلبات الشبكية.
        tfs = self._timeframes_for(cfg)
        buried: set[str] = set()
        for tf in tfs:
            for sym in storage.stored_symbols(market, tf):
                if sym in symbols or sym in buried:
                    continue
                behind = storage.bars_behind_from(
                    storage.last_time_on_disk(market, sym, tf), tf,
                    market=market)
                if behind is not None and behind > self.config.dead_max_bars:
                    buried.add(sym)
                    continue
                symbols.append(sym)
        if buried:
            log.info("تُخطّي %d رمزاً مشطوباً في %s (آخر شمعة أقدم من %d)",
                     len(buried), market, int(self.config.dead_max_bars))
            self.last_buried = sorted(buried)

        # YAML explicit list
        for s in cfg.symbols or []:
            symbols.append(s)

        # ═══ الاكتشاف يعمل مع البذور لا بدلاً منها ═══
        #
        # كان الشرط ``if not symbols`` — أي: لا تكتشف إلّا إن لم
        # يكن هناك شيء. و``symbols`` تحمل قائمة الـYAML التي أُضيفت
        # قبل سطرين، وفيها عشرة رموز لكريبتو وعشرة للأمريكي.
        #
        # فالنتيجة أنّ ``universe: auto`` **لم يعمل قطّ** لهذين
        # السوقين: عشرة رموز، إلى الأبد، مهما كان في المنصّة.
        #
        # ولم يظهر على الجهاز لأنّ الملفّات المتراكمة على القرص
        # تدخل ``symbols`` أيضاً — ٢١٠ رموز كريبتو جُمعت أيّام كانت
        # القائمة فارغة. فبدا الاكتشاف يعمل وهو معطّل منذ أن كُتبت
        # القائمة.
        #
        # وانكشف على خادمٍ نظيف: «١٠ من ١٠ رموز متأخّرة» — والعشرة
        # هي القائمة نفسها. السوق كلّه كان عشرة رموز.
        #
        # فالبذور تبقى أوّلاً (أهمّ الرموز تُزامَن أوّلاً)، والمكتشَف
        # يُضاف بعدها، والتكرار يُزال أسفلُ.
        if getattr(cfg, "universe", "") == "auto":
            try:
                # قد يكون الاكتشاف من محوّل آخر: سهمك يكتشف السوق
                # السعودي مجاناً بينما ياهو يجلب شموعه مجاناً.
                name = getattr(cfg, "universe_adapter", "") or cfg.adapter
                adapter = get_adapter(name)
                if hasattr(adapter, "usdt_universe"):
                    # المحوّلات تخبّئ الكون داخلها، فالنداء هنا لا
                    # يعني طلباً شبكياً في كل دورة.
                    found = list(adapter.usdt_universe(
                        cfg.min_quote_volume,
                        top_n=cfg.top_n or self.config.max_symbols_per_market,
                    ))
                    log.info("اكتُشف %d رمزاً في %s (بذور: %d)",
                             len(found), market, len(symbols))
                    symbols.extend(found)
            except Exception as exc:  # noqa: BLE001
                # والفشل لا يُفرغ القائمة: البذور تبقى، فالسوق يعمل
                # بعشرة رموز خيرٌ من أن يتوقّف.
                log.warning("universe resolve failed %s: %s", market, str(exc)[:120])

        # Dedupe preserve order
        seen: set[str] = set()
        out: list[str] = []
        for s in symbols:
            if s not in seen:
                seen.add(s)
                out.append(s)

        # القصّ يُعلَن. كان ``out[:200]`` يبتلع مئة شركة سعودية بلا
        # كلمة — والنقصان الصامت لا يُكتشَف إلا بالعدّ اليدوي.
        cap = self.config.max_symbols_per_market
        if len(out) > cap:
            log.warning(
                "قُصّ كون %s من %d إلى %d رمزاً (max_symbols_per_market)",
                market, len(out), cap,
            )
        return out[:cap]

    #: آخر ما استُبعد كمشطوب — للتشخيص، لا يُبتلع
    last_buried: list[str] = []

    def _timeframes_for(self, cfg) -> list[str]:
        """أيّ الفريمات تُزامَن لهذا السوق.

        ═══ لماذا صار قابلاً للضبط ═══

        كانت أربعة فريماتٍ لكل سوق دائماً: ‎15m, 1h, 4h, 1d‎. وهي
        ضربُ عدد الرموز في أربعة — ٥٣٠ رمز كريبتو تصير ٢٬١٢٠
        طلباً في الدورة الواحدة، والجدول مُشبَعٌ أصلاً ثلاثة
        أضعاف.

        وأكثرها لا يُستعمل: المسح يقرأ ‎4h‎، والتحليل من الأعلى
        للأسفل يقرأ ‎4h‎ و‎1d‎. و‎15m‎ لا تدخل إلّا في توقيت
        الالتقاء — وهو تحسينٌ لا شرط.

        فالإعداد ``sync_timeframes`` يقصرها على ما يُستعمل فعلاً،
        لكل سوقٍ على حدة.

        ═══ وفريم المسح يبقى دائماً ═══

        إسقاطه يعني سوقاً يُزامَن ولا يُمسَح — بلا خطأ ولا صفر
        نتائج، لأنّ الماسح يقرأ القرص فيجده فارغاً لذلك الفريم.
        فهو يُضاف ولو لم يُذكر، والإعداد لا يستطيع نزعه.

        وفريم المسح صار مصدرين: ``config/<سوق>.yaml`` و‏الإعداد
        ``scan_timeframes``. وكلاهما يُضمّ هنا — وإلّا فمن فعّل
        ‎1h‎ للمسح من الشاشة حصل على سوقٍ يُمسح بلا شموع.
        """
        market = getattr(cfg, "name", "")
        # ما يُمسح يُزامَن قسراً: الملفّ والإعداد معاً
        required = list(cfg.timeframes or []) + tf_prefs.scan_for(market)

        # ترتيب الأولوية: إعداد الواجهة ← ملفّ السوق ← الافتراض
        chosen = _override_for(market) \
            or list(getattr(cfg, "sync_timeframes", None) or []) \
            or list(self.config.sync_timeframes)

        merged: list[str] = []
        for tf in list(required) + list(chosen):
            if tf in UI_TIMEFRAMES and tf not in merged:
                merged.append(tf)
        return merged or list(cfg.timeframes or [])

    # ── single pair sync ──────────────────────────────────────

    def sync_pair(
        self,
        market: str,
        symbol: str,
        timeframe: str,
        *,
        force: bool = False,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Incremental sync one symbol/timeframe. Idempotent upsert via storage.merge."""
        key = status_store.pair_key(market, symbol, timeframe)
        if self._in_backoff(key) and not force:
            return {"ok": False, "reason": "backoff", "symbol": symbol, "timeframe": timeframe}

        t0 = time.perf_counter()
        obs.bump("sync_count")
        obs.log_event(
            "MARKET_SYNC_STARTED",
            market=market, symbol=symbol, timeframe=timeframe,
            config=self.config,
        )

        with sync_lock(market, symbol, timeframe, config=self.config) as acquired:
            if not acquired:
                obs.bump("skipped_busy")
                return {"ok": False, "reason": "locked", "symbol": symbol, "timeframe": timeframe}

            try:
                result = self._sync_unlocked(
                    market, symbol, timeframe,
                    force=force, config_dir=config_dir,
                )
            except Exception as exc:  # noqa: BLE001
                latency = round((time.perf_counter() - t0) * 1000, 2)
                obs.bump("failed_syncs")
                obs.record_latency(latency)
                self._register_failure(key)
                err = str(exc)[:200]
                freshness = assess_freshness(
                    market, symbol, timeframe,
                    last_sync=utc_now_iso(), error=err, config=self.config,
                )
                status_store.update_pair(market, symbol, timeframe, {
                    **freshness,
                    "last_error": err,
                    "last_sync": utc_now_iso(),
                }, config=self.config)
                obs.log_event(
                    "MARKET_SYNC_FAILED",
                    market=market, symbol=symbol, timeframe=timeframe,
                    status=FreshnessStatus.ERROR.value,
                    latency_ms=latency,
                    extra={"error": err},
                    config=self.config,
                )
                return {"ok": False, "reason": err, "symbol": symbol, "timeframe": timeframe}

        latency = round((time.perf_counter() - t0) * 1000, 2)
        obs.record_latency(latency)
        if result.get("ok"):
            obs.bump("successful_syncs")
            self._clear_backoff(key)
            obs.log_event(
                "MARKET_SYNC_COMPLETED",
                market=market, symbol=symbol, timeframe=timeframe,
                status=result.get("freshness", {}).get("status", ""),
                candle_timestamp=result.get("freshness", {}).get("latest_candle", ""),
                latency_ms=latency,
                extra={
                    "inserted": result.get("inserted", 0),
                    "updated": result.get("updated", 0),
                    "mode": result.get("mode", ""),
                },
                config=self.config,
            )
        else:
            obs.bump("failed_syncs")
            self._register_failure(key)
            obs.log_event(
                "MARKET_SYNC_FAILED",
                market=market, symbol=symbol, timeframe=timeframe,
                status="error",
                latency_ms=latency,
                extra={"reason": result.get("reason", "")},
                config=self.config,
            )
        result["latency_ms"] = latency
        return result

    # ═══ ملفّ السوق يُقرأ مرّةً لا لكل زوج ═══
    #
    # ``load_market`` يفتح YAML ويحلّله. وكان يُنادى **داخل** مزامنة
    # كل زوج: خمسة آلاف تحليلٍ لملفٍّ واحد لا يتغيّر في الدورة.
    _cfg_cache: dict[str, Any] = {}

    def _market_cfg(self, cfg_dir: Path, market: str):
        key = f"{cfg_dir}|{market}"
        hit = self._cfg_cache.get(key)
        if hit is None:
            hit = load_market(cfg_dir / f"{market}.yaml")
            self._cfg_cache[key] = hit
        return hit

    def _skip_if_current(self, market: str, symbol: str,
                         timeframe: str) -> dict[str, Any] | None:
        """‏``None`` إن لزم العمل، وإلّا نتيجةُ تخطٍّ جاهزة.

        ═══ والشكّ يُسقِط إلى المسار الكامل ═══

        ``last_time_on_disk`` تعيد ``None`` عند أيّ التباس — ملفٌّ
        بصيغةٍ غير متوقَّعة أو مبتور. وحينها لا يُتخطّى شيء: قرارٌ
        مبنيّ على قراءةٍ ناقصة أسوأ من قراءةٍ كاملة بطيئة.
        """
        try:
            last = storage.last_time_on_disk(market, symbol, timeframe)
            if last is None:
                return None
            behind = storage.bars_behind_from(last, timeframe, market=market)
            if behind is None or behind > 0:
                return None
        except Exception:  # noqa: BLE001
            return None

        # شمعةٌ جديدة لم تُغلَق: لا شيء يُجلَب
        status_store.update_pair(market, symbol, timeframe, {
            "status": FreshnessStatus.FRESH.value,
            "last_sync": utc_now_iso(),
            "latest_candle": str(last),
            "mode": "skip_current",
            "last_error": "",
        }, config=self.config)
        return {
            "ok": True, "symbol": symbol, "timeframe": timeframe,
            "mode": "skip_current", "inserted": 0, "updated": 0,
            "freshness": {"status": FreshnessStatus.FRESH.value,
                          "latest_candle": str(last)},
        }

    def _sync_unlocked(
        self,
        market: str,
        symbol: str,
        timeframe: str,
        *,
        force: bool,
        config_dir: Path | None,
    ) -> dict[str, Any]:
        cfg_dir = _config_dir(config_dir)
        cfg = self._market_cfg(cfg_dir, market)

        # ═══ الفحص الرخيص قبل القراءة الكاملة ═══
        #
        # ``storage.load`` يقرأ ويحلّل ١٥٠٠ شمعة — قِيست بـ18.76
        # مللي ثانية للزوج. وخمسة آلاف زوجٍ تعني **٩٤ ثانية** من
        # القراءة وحدها، معظمها لأزواجٍ لم تُغلَق لها شمعةٌ جديدة
        # أصلاً.
        #
        # و``last_time_on_disk`` يقفز إلى ذيل الملفّ: النتيجة نفسها
        # بجزءٍ من الألف من الكلفة. فإن لم تُغلَق شمعةٌ جديدة
        # خرجنا قبل أن نلمس الملفّ كاملاً.
        if not force:
            skip = self._skip_if_current(market, symbol, timeframe)
            if skip is not None:
                return skip

        adapter = get_adapter(cfg.adapter)
        cached = storage.load(market, symbol, timeframe)
        # ═══ فجوةٌ أوسع من جلبة: إعادة بناء لا دمج ═══
        #
        # ``bars_needed`` محدودٌ بـ``candles``، فالدمج يترك ثقباً بين
        # الذيل القديم والجديد. والقاعدة نفسها في ``scan.fetch_only``
        # و``resurrect`` — ثلاثة مسارات تكتب الملفّ نفسه، فيجب أن
        # تتّفق، وإلّا أعاد أحدُها الثقبَ الذي سدّه الآخر.
        if cached is not None:
            _gap = storage.bars_behind(cached, timeframe, market=market)
            if _gap is not None and _gap > cfg.candles - 2:
                cached = None
        before_len = 0 if cached is None else len(cached)
        last_before = storage.last_time(cached)

        # Bootstrap once when missing / too short
        if cached is None or before_len < self.config.bootstrap_min_candles:
            need = cfg.candles
            mode = "bootstrap"
        else:
            need = storage.bars_needed(cached, timeframe, cfg.candles, margin=2)
            mode = "incremental"
            # Nothing useful to fetch
            if need <= 2 and not force:
                freshness = assess_freshness(
                    market, symbol, timeframe, df=cached,
                    last_sync=utc_now_iso(), config=self.config,
                )
                status_store.update_pair(market, symbol, timeframe, {
                    **freshness,
                    "last_sync": utc_now_iso(),
                    "mode": "skip_fresh",
                    "last_error": "",
                }, config=self.config)
                return {
                    "ok": True,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "mode": "skip_fresh",
                    "inserted": 0,
                    "updated": 0,
                    "freshness": freshness,
                }

        fresh = adapter.fetch(symbol, timeframe, need)
        if fresh is None or (hasattr(fresh, "empty") and fresh.empty):
            raise RuntimeError("empty fetch from exchange")

        merged = storage.merge(cached, fresh)
        after_len = len(merged)
        last_after = storage.last_time(merged)
        inserted = max(0, after_len - before_len)
        # Same index count but last bar replaced → open candle update
        updated = 0
        if last_before is not None and last_after is not None:
            if last_before == last_after and before_len == after_len:
                # OHLC of open candle may have changed — always rewrite when force
                # or when merge kept last with keep="last" from fresh data
                updated = 1
                obs.bump("candles_updated")
                obs.log_event(
                    "CANDLE_UPDATED",
                    market=market, symbol=symbol, timeframe=timeframe,
                    candle_timestamp=str(last_after),
                    config=self.config,
                )
            elif last_before != last_after:
                obs.bump("candles_inserted", inserted or 1)
                # Previous open candle finalized when a newer open arrives
                obs.bump("candles_closed")
                obs.log_event(
                    "CANDLE_CLOSED",
                    market=market, symbol=symbol, timeframe=timeframe,
                    candle_timestamp=str(last_before),
                    config=self.config,
                )
                obs.log_event(
                    "CANDLE_UPDATED",
                    market=market, symbol=symbol, timeframe=timeframe,
                    candle_timestamp=str(last_after),
                    config=self.config,
                )
        elif inserted:
            obs.bump("candles_inserted", inserted)

        changed = (
            before_len != after_len
            or last_before != last_after
            or updated
            or force
        )
        if changed:
            storage.save(market, symbol, timeframe, merged)

        freshness = assess_freshness(
            market, symbol, timeframe, df=merged,
            last_sync=utc_now_iso(), config=self.config,
        )
        prev_status = (status_store.load_status(self.config).get("pairs") or {}).get(
            status_store.pair_key(market, symbol, timeframe), {},
        ).get("status")
        if prev_status in (FreshnessStatus.STALE.value, FreshnessStatus.CRITICAL.value,
                           FreshnessStatus.ERROR.value):
            if freshness["status"] == FreshnessStatus.FRESH.value:
                obs.log_event(
                    "MARKET_DATA_RECOVERED",
                    market=market, symbol=symbol, timeframe=timeframe,
                    status="fresh",
                    config=self.config,
                )
        if freshness["status"] in (FreshnessStatus.STALE.value, FreshnessStatus.CRITICAL.value):
            obs.log_event(
                "MARKET_DATA_STALE",
                market=market, symbol=symbol, timeframe=timeframe,
                status=freshness["status"],
                candle_timestamp=freshness.get("latest_candle") or "",
                config=self.config,
            )

        status_store.update_pair(market, symbol, timeframe, {
            **freshness,
            "last_sync": utc_now_iso(),
            "mode": mode,
            "last_error": "",
            "inserted": inserted,
            "updated": updated,
        }, config=self.config)

        return {
            "ok": True,
            "symbol": symbol,
            "timeframe": timeframe,
            "mode": mode,
            "inserted": inserted,
            "updated": updated,
            "freshness": freshness,
            "candle_count": after_len,
        }

    # ── market / batch ────────────────────────────────────────

    def sync_market(
        self,
        market: str,
        *,
        timeframes: list[str] | None = None,
        symbols: list[str] | None = None,
        force: bool = False,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        cfg_dir = _config_dir(config_dir)
        cfg = load_market(cfg_dir / f"{market}.yaml")
        tfs = timeframes or self._timeframes_for(cfg)
        syms = symbols or self.resolve_symbols(market, config_dir=cfg_dir)

        results: list[dict] = []
        workers = max(1, min(self.config.max_workers, int(getattr(cfg, "workers", 8) or 8)))

        def _job(sym: str, tf: str) -> dict:
            return self.sync_pair(market, sym, tf, force=force, config_dir=cfg_dir)

        # ═══ حالةُ الأزواج تُكتب مرّةً في النهاية ═══
        #
        # كانت تُكتب لكل زوج: قراءة الملفّ كاملاً وتعديل مفتاحٍ
        # وإعادة كتابته — تحت قفلٍ واحد يُسلسل الخيوط العشرة.
        # والملفّ يحمل كل الأزواج، فالعمل تربيعيّ.
        status_store.batch_begin()
        try:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(_job, sym, tf): (sym, tf)
                    for tf in tfs
                    for sym in syms
                }
                for fut in as_completed(futs):
                    try:
                        results.append(fut.result())
                    except Exception as exc:  # noqa: BLE001
                        sym, tf = futs[fut]
                        results.append({"ok": False, "symbol": sym,
                                        "timeframe": tf,
                                        "reason": str(exc)[:120]})
        finally:
            # ``finally``: استثناءٌ في الحلقة يجب ألّا يترك التجميع
            # مفتوحاً — فيبتلع كل تحديثٍ بعده بلا كتابة.
            written = status_store.batch_flush(config=self.config)

        ok = sum(1 for r in results if r.get("ok"))
        skipped = sum(1 for r in results
                      if r.get("mode") in ("skip_current", "skip_fresh"))
        return {
            "market": market,
            "symbols": len(syms),
            "timeframes": tfs,
            "attempted": len(results),
            "successful": ok,
            "failed": len(results) - ok,
            # ═══ ويُعلَن كم تُخطّي ═══
            #
            # «٤٢٦٥ نجحت» لا تفرّق بين جلبٍ تمّ وزوجٍ لم يكن له
            # شيء. والرقمان مختلفان تماماً في تفسير الزمن.
            "skipped_current": skipped,
            "fetched": ok - skipped,
            "status_writes": written,
            "results": results,
        }

    def incremental_refresh_stale(
        self,
        market: str,
        timeframe: str,
        *,
        symbols: list[str] | None = None,
        config_dir: Path | None = None,
        deadline_seconds: float | None = None,
        max_pairs: int | None = None,
    ) -> dict[str, Any]:
        """ينعش المتأخّر وحده — بحدٍّ زمنيّ وعدديّ.

        ═══ لماذا صار محدوداً ═══

        كان يمرّ على كل رمزٍ متأخّر **تسلسلياً وبلا سقف**. وهو
        يُنادى من بوّابة المسح، فصار زمنُ المسح = زمنُ مزامنة كل
        ما تأخّر.

        والمقيس على الخادم: ``scan:us`` استغرقت **١٩٣ دقيقة**
        وفترتها خمس عشرة، و``scan:crypto`` ستّاً وخمسين. وليس
        التحليل هو ما طال — بل المزامنة التي تجري داخله.

        والأسوأ أنّ ``market_sync`` تفعل العمل نفسه كل عشر دقائق
        بـ**اثني عشر خيطاً**. فالبوّابة تعيد تسلسلياً ما تفعله
        المزامنة متوازياً.

        ═══ والحدّ لا يُخفي ═══

        ما لم يُنعَش يُعلَن في ``remaining``، والبوّابة تستبعد
        رموزه من المسح. فالنتيجة مسحٌ على ما هو طازجٌ فعلاً —
        لا مسحٌ متأخّر ولا انتظارٌ بلا نهاية.
        """
        import time as _t

        syms = symbols or self.resolve_symbols(market, config_dir=config_dir)
        budget = (deadline_seconds if deadline_seconds is not None
                  else float(getattr(self.config, "gate_refresh_seconds",
                                     120.0)))
        cap = (max_pairs if max_pairs is not None
               else int(getattr(self.config, "gate_refresh_max_pairs", 60)))

        started = _t.monotonic()
        refreshed: list[dict] = []
        remaining: list[str] = []
        stopped = ""

        for sym in syms:
            if stopped:
                remaining.append(sym)
                continue
            # ═══ الحدّ يُفحَص قبل الجلب لا بعده ═══
            if budget > 0 and (_t.monotonic() - started) >= budget:
                stopped = f"نفد الوقت ({budget:g}ث)"
                remaining.append(sym)
                continue
            if cap > 0 and len(refreshed) >= cap:
                stopped = f"بلغ الحدّ ({cap} زوجاً)"
                remaining.append(sym)
                continue

            info = assess_freshness(market, sym, timeframe, config=self.config)
            if info["status"] in (
                FreshnessStatus.STALE.value,
                FreshnessStatus.MISSING.value,
            ):
                refreshed.append(self.sync_pair(market, sym, timeframe, config_dir=config_dir))
            elif info["status"] == FreshnessStatus.CRITICAL.value:
                refreshed.append(self.sync_pair(market, sym, timeframe, force=True, config_dir=config_dir))

        if stopped:
            log.info("إنعاش بوّابة %s/%s توقّف: %s — %d أُنعش و%d بقي",
                     market, timeframe, stopped, len(refreshed),
                     len(remaining))
        return {"refreshed": len(refreshed), "results": refreshed,
                "remaining": len(remaining), "stopped": stopped,
                "elapsed": round(_t.monotonic() - started, 1)}

    # ── إحياء المقبرة ─────────────────────────────────────────

    def live_universe(self, market: str, *,
                      config_dir: Path | None = None) -> set[str] | None:
        """رموز المنصّة الآن — أو ``None`` إن لم يُعرَف الكون.

        هذا هو **الفارق الوحيد** بين رمزٍ شُطب من المنصّة ورمزٍ
        تأخّرت مزامنته حتى بدا مشطوباً. وبلا هذا السؤال لا يمكن
        التمييز بينهما من القرص وحده: كلاهما ملفٌّ آخر شمعةٍ فيه
        قديمة.
        """
        try:
            cfg = self._market_cfg(_config_dir(config_dir), market)
            name = getattr(cfg, "universe_adapter", "") or cfg.adapter
            ad = get_adapter(name)
            if hasattr(ad, "usdt_universe"):
                return set(ad.usdt_universe(
                    cfg.min_quote_volume,
                    top_n=cfg.top_n or self.config.max_symbols_per_market,
                ))
            return set(cfg.symbols or []) or None
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر معرفة كون %s: %s", market, str(exc)[:120])
            return None

    def resurrect(
        self,
        market: str,
        timeframe: str,
        *,
        symbols: list[str] | None = None,
        config_dir: Path | None = None,
        deadline_seconds: float | None = None,
        max_pairs: int | None = None,
    ) -> dict[str, Any]:
        """يعيد بناء الرموز التي بدت مشطوبةً وهي ما تزال متداولة.

        ═══ الباب ذو الاتّجاه الواحد ═══

        ``dead`` تعني «آخر شمعة أقدم من مئة شمعة». وقد وُضعت
        للرمز الذي **شُطب من المنصّة**: ملفٌّ باقٍ على القرص
        والجلب التراكمي يطلب الناقص فلا يعود بشيء، إلى الأبد.

        لكنّ التعريف لا يفرّق بين سببين:

            رمزٌ شُطب       ← لا علاج، والملاحقة هدرٌ محض
            مزامنةٌ تعطّلت   ← علاجُه جلبةٌ واحدة

        ومزامنةٌ تتوقّف أكثر من مئة شمعة (‎4h‎ ← سبعة عشر يوماً)
        تُسقط **السوق كلّه** في الخانة الأولى دفعةً واحدة. وبعدها:

            ``resolve_symbols``        يستبعد المشطوبين
            بوّابة المسح               تُنعش ``alive`` وحدهم
            والمشطوب ليس من ``alive``

        فلا شيء يجلب لهم، فيبقون مشطوبين، إلى الأبد. بابٌ يُغلق
        ولا يُفتح — وهذا ما رأيتَه: ٥٣٧ مشطوباً من ٥٣٨.

        ═══ والفارق يُسأل من المنصّة ═══

        لا يُحزَر من القرص: يُسأل ``live_universe``. فمن كان في
        كون المنصّة اليوم فهو حيّ مهما قدُم ملفّه.

        ═══ والفجوة تُعاد بناءً لا دمجاً ═══

        ``bars_needed`` محدودٌ بـ``candles`` (١٥٠٠). وفجوةٌ أوسع
        منها تعني إطاراً فيه **ثقب** بعد الدمج — والمؤشّرات
        تُحسب عليه بلا أن يقول أحدٌ شيئاً. فما تجاوزت فجوتُه ما
        تسعه جلبةٌ واحدة يُستبدَل ملفُّه بالكامل: تاريخٌ أقصر
        ونظيف خيرٌ من أطولَ مثقوب.
        """
        import time as _t

        cfg_dir = _config_dir(config_dir)
        cfg = self._market_cfg(cfg_dir, market)
        syms = symbols or self.resolve_symbols(market, config_dir=config_dir)
        universe = self.live_universe(market, config_dir=config_dir)

        budget = (deadline_seconds if deadline_seconds is not None
                  else float(getattr(self.config, "resurrect_seconds", 600.0)))
        cap = (max_pairs if max_pairs is not None
               else int(getattr(self.config, "resurrect_max_pairs", 1000)))

        started = _t.monotonic()
        adapter = get_adapter(cfg.adapter)
        rebuilt: list[str] = []
        patched: list[str] = []
        buried: list[str] = []
        failed: list[dict] = []
        remaining: list[str] = []
        stopped = ""

        for sym in syms:
            if stopped:
                remaining.append(sym)
                continue
            if budget > 0 and (_t.monotonic() - started) >= budget:
                stopped = f"نفد الوقت ({budget:g}ث)"
                remaining.append(sym)
                continue
            if cap > 0 and len(rebuilt) + len(patched) >= cap:
                stopped = f"بلغ الحدّ ({cap} رمزاً)"
                remaining.append(sym)
                continue

            info = assess_freshness(market, sym, timeframe,
                                    config=self.config)
            if info["status"] != FreshnessStatus.DEAD.value:
                continue

            # ═══ المشطوب حقاً يُترك ═══
            #
            # ملاحقته آلافُ طلباتٍ لا تعود بشمعة — وهي ما ضخّم
            # سجلّ الأحداث إلى ٣٠٥ ميغابايت أوّل مرّة.
            if universe is not None and sym not in universe:
                buried.append(sym)
                continue

            behind = info.get("bars_behind") or 0
            try:
                if behind > cfg.candles:
                    # الفجوة أوسع من جلبة: يُعاد البناء لا يُدمَج
                    fresh = adapter.fetch(sym, timeframe, cfg.candles)
                    if fresh is None or getattr(fresh, "empty", False):
                        failed.append({"symbol": sym, "error": "جلبٌ فارغ"})
                        continue
                    storage.save(market, sym, timeframe, fresh)
                    rebuilt.append(sym)
                else:
                    r = self.sync_pair(market, sym, timeframe, force=True,
                                       config_dir=config_dir)
                    if r.get("ok"):
                        patched.append(sym)
                    else:
                        failed.append({"symbol": sym,
                                       "error": str(r.get("reason"))[:80]})
            except Exception as exc:  # noqa: BLE001
                failed.append({"symbol": sym,
                               "error": f"{type(exc).__name__}: "
                                        f"{str(exc)[:80]}"})

        log.info("إحياء %s/%s: %d أُعيد بناؤه · %d رُقّع · %d مشطوبٌ حقاً "
                 "· %d فشل · %d بقي%s",
                 market, timeframe, len(rebuilt), len(patched), len(buried),
                 len(failed), len(remaining),
                 f" ({stopped})" if stopped else "")
        return {
            "rebuilt": len(rebuilt), "patched": len(patched),
            "buried": len(buried), "failed": len(failed),
            "remaining": len(remaining), "stopped": stopped,
            "universe_known": universe is not None,
            "universe_size": 0 if universe is None else len(universe),
            "rebuilt_symbols": rebuilt, "buried_symbols": buried,
            "failures": failed[:20],
            "elapsed": round(_t.monotonic() - started, 1),
        }

    # ── scan gate ─────────────────────────────────────────────

    def scan_freshness_gate(
        self,
        market: str,
        timeframe: str,
        *,
        symbols: list[str] | None = None,
        auto_refresh: bool = True,
        config_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Decide whether scan may proceed on cached data."""
        syms = symbols or self.resolve_symbols(market, config_dir=config_dir)
        if not syms:
            return {
                "ok": False,
                "code": "MARKET_DATA_MISSING",
                "reason": "لا رموز للمزامنة",
                "action": "bootstrap",
            }

        # ═══ رمزٌ واحد لا يُسقط تقييم السوق ═══
        #
        # كانت قائمةً بلا حماية: ملفّ ``GIGGLEUSDT.npz`` مبتور على
        # القرص، و``np.load`` يرمي ``BadZipFile``، فيصعد الاستثناء
        # ويُسقط تقييم **السوق كلّه** — بايتٌ واحد يُعمي سوقاً.
        #
        # وعُولج في ``storage`` أيضاً، لكن الحماية هنا لا تُستغنى:
        # القائمة تلمس القرص وقواعد الوقت وجداول الجلسات، وأيٌّ منها
        # قد يفاجئ. والرمز الذي يفاجئ يُعدّ ``error`` — حالةٌ معلَنة
        # لها خانتها في التعداد، لا انهيار.
        assessments = []
        for s in syms:
            try:
                assessments.append(
                    assess_freshness(market, s, timeframe, config=self.config))
            except Exception as exc:  # noqa: BLE001
                log.warning("تعذّر تقييم %s/%s %s: %s",
                            market, s, timeframe, str(exc)[:100])
                assessments.append({"symbol": s, "market": market,
                                    "timeframe": timeframe,
                                    "status": FreshnessStatus.ERROR.value,
                                    "error": str(exc)[:200]})
        counts = {
            "fresh": sum(1 for a in assessments if a["status"] == "fresh"),
            "stale": sum(1 for a in assessments if a["status"] == "stale"),
            "critical": sum(1 for a in assessments if a["status"] == "critical"),
            "dead": sum(1 for a in assessments if a["status"] == "dead"),
            "missing": sum(1 for a in assessments if a["status"] == "missing"),
            "error": sum(1 for a in assessments if a["status"] == "error"),
        }

        # ═══ المقبرة لا تُحسب على الأحياء ═══
        #
        # ١٣٨ زوجاً من ٥٢٦ في كريبتو 4h آخر شمعة لها من 2022 —
        # رموز شُطبت من المنصّة وبقيت ملفّاتها. وكانت تُعدّ ``critical``
        # فتجاوز «الحرج» نصف السوق، فأعلنت البوابة السوق متأخّراً
        # وأوقفت المسح **منذ ٢٠ أغسطس**: بلا دورة ولا مراقبة ولا صفقة.
        #
        # ومقبرةٌ على القرص لا تقول شيئاً عن صحّة الجلب اليوم. فتُخرَج
        # من المقام: النسبة تُقاس على من **يمكن** أن يكون حديثاً.
        #
        # ولا تُخفى: تُحصى وتُعرَض، وتُقترح إزالتها.
        living = len(assessments) - counts["dead"]
        total = living or 1
        fresh_ratio = counts["fresh"] / total

        # ═══ «لا بيانات بعد» ليس «بيانات متأخّرة» ═══
        #
        # كان الشرط ``critical + missing > النصف`` — فيخلط حالتين
        # متضادّتين في الخطر:
        #
        #   critical = ملفٌّ موجود وآخر شمعة فيه قديمة جداً. خطرٌ
        #              حقيقي: توصية بسعر عمره أسابيع.
        #   missing  = لا ملف أصلاً. لا خطر البتّة — لا سعر قديم
        #              يُخدَع به أحد، والمسح يجلبه بنفسه في السطر
        #              التالي (``fetch_only`` يعالج ``cached is None``).
        #
        # وأثر الخلط ظهر بالضبط لحظة إصلاح الاكتشاف: صار السوق
        # الأمريكي يكتشف أربعمئة رمز، وتسعون وثلاثمئة منها بلا ملف
        # لأنّها **جديدة**. فتجاوز ``missing`` النصف، فأعلنت البوابة
        # ``MARKET_DATA_STALE`` وأوقفت المسح — ولم تُحفَظ دورة، فظلّت
        # اللوحة تعرض دورةً عمرها أسبوعان بعشرة رموز.
        #
        # أي أن إصلاح الاكتشاف هو الذي فجّر هذا: كلّما اكتشف النظام
        # أكثر، ازداد ``missing``، وازداد يقين البوابة أنّ شيئاً
        # معطوب. البوابة كانت تعاقب النجاح.
        #
        # فالحكم على ``critical`` وحده. و``missing`` يُبلَّغ ويُجلَب
        # ولا يمنع.
        # ═══════════════════════════════════════════════════════
        #  الاستبعاد بالرمز لا بالسوق
        # ═══════════════════════════════════════════════════════
        #
        # كانت البوّابة تحجب السوق **كلّه** إن تجاوز نصفُ رموزه
        # الحدّ. والغاية صحيحة — ألّا تُبنى توصيةٌ على سعرٍ عمره
        # أسبوعان — لكنّ الإنفاذ كان خطأً في اتّجاهين معاً:
        #
        # **أقلّ أماناً.** عند ٤٩٪ حرجاً تمرّ البوّابة، فيُمسَح
        # نصف السوق ببياناتٍ قديمة. النسبة تحمي الأغلبية وتترك
        # الأقلّية تمرّ — والخطر في الرمز الواحد لا في النسبة.
        #
        # **وأقلّ نفعاً.** عند ٥١٪ تُحجب النتائج كلّها، بما فيها
        # ٤٩ رمزاً بياناتها سليمة تماماً. صفرُ نتيجة بدل نتيجةٍ
        # ناقصة معلومة النقص.
        #
        # ونظامٌ يملأ بياناته لأوّل مرّة يقع في الفخّ حتماً: كل
        # رموزه قديمة حتى تلحقها المزامنة، فيُحجب المسح، فلا
        # تُحفظ دورة، فتبدو اللوحة معطوبة وهي تعمل.
        #
        # فالقاعدة الآن: الرمز المتأخّر **لا يُمسَح**، والباقي
        # يُمسَح، والعدد يُعلَن. ولا يُحجب السوق إلّا إن لم يبقَ
        # رمزٌ واحد صالح — وذلك عطلٌ حقيقيّ لا إحماء.
        if counts["critical"] and auto_refresh:
            # الموتى لا يُلاحَقون: ملاحقتهم تعني آلاف الطلبات التي
            # لا تعود بشمعة، وهي ما ضخّم سجلّ الأحداث إلى ٣٠٥
            # ميغابايت وأشغل عامل المزامنة عن الأحياء.
            alive = [a["symbol"] for a in assessments
                     if a["status"] != "dead"]
            self.incremental_refresh_stale(
                market, timeframe, symbols=alive or syms,
                config_dir=config_dir,
            )
            return self.scan_freshness_gate(
                market, timeframe, symbols=syms, auto_refresh=False,
                config_dir=config_dir,
            )

        # ``missing`` صالحٌ عمداً: لا ملفّ = لا سعرٌ قديم يُخدَع به
        # أحد، والمسح يجلبه في السطر التالي. والحرج والميّت
        # يُستبعدان: لهما ملفّ، وفيه سعرٌ قديم.
        _USABLE = ("fresh", "stale", "missing")
        usable = [a["symbol"] for a in assessments if a["status"] in _USABLE]
        excluded = [a["symbol"] for a in assessments
                    if a["status"] not in _USABLE]

        # ═══ ومقبرةٌ جماعية ليست شطباً جماعياً ═══
        #
        # رمزٌ يُشطب وحده، وعشرةٌ تُشطب في شهر. أمّا أن يصير
        # **كلّ** السوق مشطوباً في وقتٍ واحد فليس شطباً — بل
        # مزامنةٌ توقّفت أكثر من مئة شمعة. والفرع أعلاه لا يعالجه:
        # هو يُنعش ``alive`` والمشطوب ليس منهم.
        #
        # فحين لا يبقى رمزٌ واحد صالح والمشطوبون كثرة، يُسأل كونُ
        # المنصّة: من كان فيه اليوم يُعاد بناؤه.
        if auto_refresh and not usable and counts["dead"]:
            # ═══ والبوّابة تُسعف ولا تُعالج ═══
            #
            # ``resurrect`` سقفُه ستّمئة ثانية وألف زوج — وهو صحيحٌ
            # للأداة اليدوية. لكنّه يُنادى من **داخل المسح**، فصار
            # المسح يحمل عشر دقائق من الجلب قبل أن يحلّل شمعةً
            # واحدة. وهو عطبٌ أدخلتُه أنا بهذا الفرع.
            #
            # فميزانية البوّابة هي ميزانيتها: شريحةٌ صغيرة تُسعف،
            # والباقي يُعلَن ويُترك لـ``tools_resurrect.py`` أو
            # لدورةٍ تالية. مسحٌ ناقصٌ معلوم النقص خيرٌ من مسحٍ
            # يتأخّر عشر دقائق في كل دورة.
            res = self.resurrect(
                market, timeframe, symbols=syms, config_dir=config_dir,
                deadline_seconds=float(getattr(
                    self.config, "gate_refresh_seconds", 120.0)),
                max_pairs=int(getattr(
                    self.config, "gate_refresh_max_pairs", 60)),
            )
            if res["rebuilt"] or res["patched"]:
                return self.scan_freshness_gate(
                    market, timeframe, symbols=syms, auto_refresh=False,
                    config_dir=config_dir,
                )

        if not usable:
            # ═══ لماذا لا يُستثنى «السوق مغلق» هنا ═══
            #
            # جرّبتُ أوّلاً أن أُمرّر الحالة إن كان السوق مغلقاً —
            # وكان خطأً: جلبٌ متعطّل منذ أسبوعين يقع اكتشافه يوم
            # سبت، فيُعلَن «مغلق» ويمضي. الاستثناء كان سيصنع عمًى
            # أوسع من الإنذار الكاذب الذي يعالجه.
            #
            # والعلاج الصحيح في **القياس** لا في الاستثناء: التأخّر
            # يُحسب الآن بزمن السوق المفتوح، فعطلة نهاية الأسبوع
            # تعطي صفراً بذاتها، وأسبوعان من التعطّل يعطيان عشر
            # جلسات مهما كان يوم الفحص.
            from scanner import sessions

            nxt = sessions.next_open(market)
            return {
                "ok": False,
                "code": "MARKET_DATA_STALE",
                # الرقم في الرسالة لا في الحقول وحدها: «متأخرة جداً»
                # بلا عدد لا يقول أهي ثلاثة رموز أم أربعمئة.
                # ═══ والعدد وحده لا يقول ماذا يُفعل ═══
                #
                # «٥٣٧ مشطوباً من ٥٣٨» رقمٌ صحيح وصامت. وشطبٌ يعمّ
                # السوق كلّه ليس شطباً بل مزامنةً توقّفت، وعلاجه
                # مختلفٌ تماماً — فيُقال.
                "reason": (
                    f"لا رمز واحد ببيانات صالحة — "
                    f"{counts['critical']} حرجاً و{counts['dead']} "
                    f"مشطوباً من {len(assessments)}"
                    + (" · شطبٌ يعمّ السوق = مزامنةٌ توقّفت لا رموزٌ "
                       "شُطبت؛ شغّل tools_resurrect.py --apply"
                       if counts["dead"] >= max(5, len(assessments) // 2)
                       else "")),
                "counts": counts,
                "living": living,
                "dead": counts["dead"],
                "usable": [],
                "excluded": excluded,
                "market_open": sessions.is_open(market),
                "next_open": None if nxt is None else nxt.isoformat(),
                "action": "manual_sync",
            }

        if excluded:
            return {
                "ok": True,
                "code": "PARTIAL",
                "reason": (f"مُسِح {len(usable)} من {len(assessments)} رمزاً "
                           f"· استُبعد {len(excluded)} لقِدَم بياناته"),
                "counts": counts,
                "living": living,
                "dead": counts["dead"],
                "usable": usable,
                "excluded": excluded,
                "fresh_ratio": round(fresh_ratio, 3),
                "use_cached": True,
            }

        if counts["stale"] or counts["missing"]:
            if auto_refresh:
                self.incremental_refresh_stale(
                    market, timeframe, symbols=syms, config_dir=config_dir,
                )
            return {
                "ok": True,
                "code": "REFRESHED",
                "reason": "تم تحديث البيانات الناقصة",
                "counts": counts,
                "living": living,
                "dead": counts["dead"],
                "usable": usable,
                "excluded": excluded,
                "fresh_ratio": round(fresh_ratio, 3),
                "use_cached": True,
            }

        return {
            "ok": True,
            "code": "FRESH",
            "reason": "البيانات حديثة",
            "counts": counts,
            "living": living,
            "dead": counts["dead"],
            "usable": usable,
            "excluded": excluded,
            "fresh_ratio": round(fresh_ratio, 3),
            "use_cached": True,
        }

    # ── global status ─────────────────────────────────────────

    def global_status(self, *, markets: list[str] | None = None,
                      max_age: float = 0.0) -> dict[str, Any]:
        """حالة بيانات السوق.

        ═══ لماذا صارت مذاكَرة ═══

        هذه الدالة تُنادى من ``base.html`` في **كل تحميل صفحة** وكل
        ثلاثين ثانية. وكانت تُعيد تقييم **كل زوج مسجَّل** بقراءة ملفّ
        شموعه من القرص: 1588 زوجاً، فقياسٌ فعلي أعطى **26.3 ثانية**
        للنداء الواحد.

        وهذا هو سبب «التحديث يظلّ يدور»: الصفحة تنتظر ألفاً وخمسمئة
        قراءة قرص متسلسلة قبل أن ترسم شارة صغيرة.

        والحالة لا تتغيّر بين لحظة وأخرى — عامل المزامنة يكتبها كل
        دقائق. فذاكرة قصيرة تُحوّل النداء من ثوانٍ إلى أجزاء من الألف
        بلا فقدان معنى.

        ``max_age=0`` يفرض إعادة الحساب (لعامل الخلفية)، وأي قيمة
        موجبة تقبل نتيجة أحدث منها.
        """
        if max_age > 0:
            key = ",".join(sorted(markets)) if markets else "*"
            hit = _STATUS_CACHE.get(key)
            if hit:
                age = time.time() - hit[0]
                if age < max_age:
                    out = dict(hit[1])
                    out["cached"] = True
                    out["cache_age"] = round(age, 1)
                    return out

                # ═══ القديم فوراً، والتحديث خلفاً ═══
                #
                # الذاكرة وحدها تحلّ تسعة وتسعين طلباً وتترك المئة
                # ينتظر خمس عشرة ثانية — وهو من يشتكي. فيُعاد آخر
                # ما حُسب حالاً، ويُحدَّث في خيط.
                #
                # وحالة بيانات عمرها دقيقة كافية تماماً لشارة تقول
                # «البيانات حديثة» — والدقّة المطلقة هنا لا تساوي
                # تعليق الصفحة.
                if _refresh_in_background(self, markets, key):
                    out = dict(hit[1])
                    out["cached"] = True
                    out["stale"] = True
                    out["cache_age"] = round(age, 1)
                    return out

        data = status_store.load_status(self.config)
        pairs = data.get("pairs") or {}
        # Optionally re-assess from disk for accuracy
        items = []
        for key, row in pairs.items():
            parts = key.split("|")
            if len(parts) != 3:
                continue
            market, symbol, timeframe = parts
            if markets and market not in markets:
                continue
            info = assess_freshness(
                market, symbol, timeframe,
                last_sync=row.get("last_sync"),
                error=row.get("last_error") or None,
                config=self.config,
            )
            items.append(info)

        healthy = sum(1 for i in items if i["status"] == "fresh")
        stale = sum(1 for i in items if i["status"] in ("stale", "missing"))
        error = sum(1 for i in items if i["status"] in ("error", "critical"))
        last_ok = max(
            (i.get("last_sync") or "" for i in items if i.get("last_sync")),
            default=None,
        ) or (data.get("worker") or {}).get("last_successful_sync")

        overall = "healthy"
        if error and error >= max(1, len(items) // 5):
            overall = "error"
        elif stale or error:
            overall = "degraded"
        if not items:
            overall = "unknown"

        worker = data.get("worker") or {}
        result = {
            "status": overall,
            "symbols": len({i["symbol"] for i in items}),
            "pairs": len(items),
            "healthy": healthy,
            "stale": stale,
            "error": error,
            "last_successful_sync": last_ok,
            "next_sync": worker.get("next_sync"),
            "worker": worker,
            "metrics": obs.metrics_snapshot(),
            "items": items[:200],
        }
        _STATUS_CACHE[",".join(sorted(markets)) if markets else "*"] = (
            time.time(), result)
        return result

    # ── backoff ───────────────────────────────────────────────

    def _in_backoff(self, key: str) -> bool:
        entry = self._backoff.get(key)
        if not entry:
            return False
        return time.time() < float(entry.get("until", 0))

    def _register_failure(self, key: str) -> None:
        entry = self._backoff.get(key) or {"failures": 0}
        failures = int(entry.get("failures", 0)) + 1
        delays = self.config.retry_backoff_seconds
        delay = delays[min(failures - 1, len(delays) - 1)]
        self._backoff[key] = {"failures": failures, "until": time.time() + delay}
        obs.bump("retry_count")
        obs.log_event("MARKET_SYNC_RETRY", extra={"key": key, "delay": delay}, config=self.config)

    def _clear_backoff(self, key: str) -> None:
        self._backoff.pop(key, None)
