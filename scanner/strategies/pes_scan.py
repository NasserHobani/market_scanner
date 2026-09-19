# -*- coding: utf-8 -*-
"""مسح PES — على كل رموز السوق، مع تذكّر المرحلة السابقة.

═══ لماذا تُحفظ الحالة ═══

``ENTRY_READY`` تعني: مرّ الرمز بـ ‏PRE_BREAKOUT ثمّ اختراقٍ مؤكَّد
ثمّ إعادة اختبار. وهذا **تسلسلٌ عبر الزمن** لا حالةٌ لحظية — فبلا
ذاكرةٍ لا يمكن أن يُمنح أبداً، أو يُمنح لمن لم يمرّ به.

فالحالة تُحفظ لكل رمز مع تاريخ تبدّلها، ويُقارَن بها في الدورة
التالية.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("scanner.strategies.pes_scan")

# ‏PES مبنيّة على 4H للإعداد و1D للاتجاه — والفريمان لازمان
REQUIRED = ("1d", "4h")

# ═══ أطرٌ تُحسّن ولا تُشترط (المادّة ١٠) ═══
#
#     ‎1h‎   ‏MACD — تأكيدٌ أقرب للتحوّل
#     ‎15m‎  ‏StochRSI — لحظة الدخول
#
# وغيابها **لا يُسقط الرمز**: رمزٌ لم يُزامَن فريمه بعد ليس رمزاً
# سيّئاً، واشتراطُها كان سيُخرج أغلب السوق السعودي والأمريكي من
# المسح بلا أن يظهر السبب. فيرتدّ التوقيت إلى ‎4h‎ ويُعلَن ذلك.
OPTIONAL = ("1h", "15m")


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _fib_brief(fib: dict) -> dict:
    """ما يُحفظ من امتداد فيب — وسببُ غيابه إن غاب.

    ``ok=False`` مع سببٍ مكتوب أنفع من حذف المفتاح: الشاشة تقول
    «لا موجة صالحة لأنّ التصحيح كسر بدايتها» بدل أن تصمت، فلا
    يُظنّ العطب في الحساب.
    """
    if not fib.get("ok"):
        return {"ok": False, "why": fib.get("why", "غير محسوب")}
    nxt = fib.get("next_level") or {}
    return {
        "ok": True,
        "p1": fib["p1"], "p2": fib["p2"], "p3": fib["p3"],
        "retracement": fib["retracement"],
        "leg_pct": fib["leg_pct"],
        "next_ratio": nxt.get("ratio"),
        "next_price": nxt.get("price"),
        "room_pct": fib.get("room_pct"),
        "stage": fib.get("stage"),
        "extended": fib.get("extended"),
        "confluence": fib.get("confluence"),
    }


def cache_path(market: str) -> Path:
    return _root() / "data" / "pes" / f"{market}.json"


def load(market: str) -> dict | None:
    try:
        return json.loads(cache_path(market).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _previous_states(market: str) -> dict[str, str]:
    old = load(market) or {}
    return {r["symbol"]: r.get("state", "")
            for r in (old.get("rows") or []) if r.get("symbol")}


def scan(market: str, *, limit: int = 0, params: dict | None = None) -> dict:
    """يقيّم كل رموز السوق ويصنّفها."""
    from scanner import storage
    from scanner.strategies import pes

    p = params or pes.load_params()
    prev = _previous_states(market)

    # ═══ نظام BTC للكريبتو وحده ═══
    #
    # يُحسب مرّة ويُشارَك بين رموز السوق الرقميّ. وكان يُحسب لكل
    # سوق: شموع BTCUSDT تُقرأ من القرص لتقييم سهمٍ سعوديّ، فتتحرّك
    # درجتُه عشر نقاطٍ بحركة عملةٍ لا تربطه بها رابطة، وتهبط ثقتُه
    # إلى ٠٫٤ لأنّ البتكوين هابط.
    #
    # والقطع هنا — عند المصدر — لا في ``evaluate`` وحدها: ما لا
    # يُقرأ لا يُسرَّب.
    btc = {}
    if market in pes.BTC_MARKETS:
        try:
            btc = pes.btc_regime(storage.load("crypto", "BTCUSDT", "1d"))
        except Exception:  # noqa: BLE001
            log.warning("تعذّر حساب نظام BTC")

    symbols = storage.stored_symbols(market, "4h")
    if limit:
        symbols = symbols[:limit]

    rows: list[dict] = []
    skipped = {"no_frames": 0, "blocked": 0, "error": 0}
    t0 = time.perf_counter()

    # الرموز المحظورة لا تُقيَّم أصلاً — قرار المستخدم يسبق الحساب
    try:
        import sys

        sys.path.insert(0, str(_root() / "web"))
        from dashboard import blocklist
    except Exception:  # noqa: BLE001
        blocklist = None

    for sym in symbols:
        if blocklist is not None:
            try:
                if blocklist.is_blocked(market, sym):
                    skipped["blocked"] += 1
                    continue
            except Exception:  # noqa: BLE001
                pass
        frames = {}
        try:
            for tf in REQUIRED:
                frames[tf] = storage.load(market, sym, tf)
        except Exception:  # noqa: BLE001
            skipped["error"] += 1
            continue
        if any(frames.get(tf) is None or len(frames[tf]) < 60
               for tf in REQUIRED):
            skipped["no_frames"] += 1
            continue

        # الاختيارية تُقرأ بصمت: فشلُ قراءتها ليس فشلَ الرمز
        for tf in OPTIONAL:
            try:
                got = storage.load(market, sym, tf)
                if got is not None and len(got) >= 60:
                    frames[tf] = got
            except Exception:  # noqa: BLE001
                pass

        try:
            res = pes.evaluate(frames, btc=btc, params=p, market=market)
            cls = pes.classify(res, frames["4h"], previous=prev.get(sym, ""),
                               params=p)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر تقييم %s: %s", sym, str(exc)[:100])
            skipped["error"] += 1
            continue

        rows.append({
            "symbol": sym, "market": market,
            "score": res["score"],
            "state": cls["state"], "state_label": cls["label"],
            "why": cls["why"],
            "confidence": res["confidence"],
            "already_expanded": res["already_expanded"],
            "expanded_reasons": res["expanded_reasons"],
            "family_count": res["family_count"],
            "families_contributing": res["families_contributing"],
            "families": res["families"],
            "factors": [{"key": f["key"], "family": f["family"],
                         "points": f["points"], "max": f["max"],
                         "detail": f.get("detail", "")}
                        for f in res["factors"]],
            "resistance": cls.get("resistance_level"),
            "distance": cls.get("resistance_distance"),
            "breakout": cls.get("breakout") or {},
            # ═══ ‏Supertrend مختصراً ═══
            #
            # الاتّجاه وعمر الانقلاب وحدهما — لا الخطّ ولا سلسلته.
            # الشاشة تعرض هذين، والخطّ يُرسم على شارت الرمز حيث
            # يُحسب على نافذة العرض لا على آخر شمعة.
            "supertrend": next(
                (f.get("supertrend") or {} for f in res["factors"]
                 if f["key"] == "supertrend"), {}),
            # ═══ التقاء الزخم — مختصراً لا كاملاً ═══
            #
            # المخرَج الكامل يحمل سلاسل MACD وStochRSI، وحفظُه لكل
            # رمز يضخّم ملفّ الذاكرة عشرات الأضعاف. والمعروض هو
            # الدرجة ومرتبتها وأسبابها — وهذا ما تقرأه الشاشة.
            "momentum": {
                "score": (res.get("momentum") or {}).get("score", 0.0),
                "label": (res.get("momentum") or {}).get("label", ""),
                "reasons": (res.get("momentum") or {}).get("reasons", []),
                "macd_rising": (res.get("momentum") or {}).get(
                    "macd_rising", False),
                "stoch_timing": (res.get("momentum") or {}).get(
                    "stoch_timing", False),
                "timing_source": (res.get("momentum") or {}).get(
                    "timing_source", ""),
                "timeframes": (res.get("momentum") or {}).get(
                    "timeframes", {}),
            },
            "momentum_backs_breakout": cls.get("momentum_backs_breakout",
                                               False),
            # ═══ امتداد فيب — مختصراً ═══
            #
            # ثمانية مستويات لكل رمز تضخّم ملفّ الذاكرة، والمعروض
            # هو الهدف التالي والمسافة إليه وموضع السعر. والرسم
            # الكامل يُحسب في صفحة الرمز حيث يُرى.
            "fib": _fib_brief(cls.get("fib") or {}),
            "previous_state": prev.get(sym, ""),
            "close": float(frames["4h"]["close"].iloc[-1]),
            # ═══ شمعة القرار — لا وقت المسح ═══
            #
            # ‏PES تقرّر على آخر شمعة **مغلقة** (‎-2‎)، والمسح قد
            # يعمل بعدها بدقائق أو بساعتين حسب ازدحام الجدولة.
            # فقياسُ ما جرى «بعد الرصد» من وقت المسح يخلط تأخّر
            # الجدولة بحركة السوق — والسجلّ يصير عن نفسه لا عن
            # الاستراتيجية.
            "candle_time": (frames["4h"].index[-2].isoformat()
                            if len(frames["4h"]) > 1 else None),
            "decision_close": float(frames["4h"]["close"].iloc[-2])
                              if len(frames["4h"]) > 1 else None,
        })

    # الأعلى نقاطاً أوّلاً — والمرحلة تُرشَّح في الواجهة
    rows.sort(key=lambda r: -r["score"])
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1

    return {
        "market": market, "measured_at": time.time(),
        "elapsed_sec": round(time.perf_counter() - t0, 1),
        "btc": btc, "rows": rows,
        "evaluated": len(rows), "skipped": skipped,
        "by_state": by_state,
    }


def save(payload: dict) -> Path:
    p = cache_path(payload["market"])
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, default=str),
                   encoding="utf-8")
    tmp.replace(p)
    return p


__all__ = ["scan", "save", "load", "cache_path", "REQUIRED", "OPTIONAL"]
