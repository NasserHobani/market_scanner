# -*- coding: utf-8 -*-
"""مسح «من الأعلى للأسفل» على كل رموز السوق، وحفظُ النتيجة.

يتبع ما يتبعه ``pes_scan``: ملفٌّ واحد لكل سوق في ``data/topdown/``،
يُقرأ فوراً عند فتح الشاشة. والحساب في مهمّةٍ مجدولة لا في الطلب —
مئة رمزٍ × ثلاثة فريمات لا تُحسب وخادمٌ ينتظر.

═══ ويُحفَظ المستبعَد أيضاً ═══

شاشةٌ تعرض المطابق وحده تصير صندوقاً مغلقاً: صفر نتيجة لا يُفرّق
بين «لا فرصة اليوم» و«المسح معطوب». فتُحفظ المراحل التي سقط عندها
كلُّ رمز، وتعرض الشاشة العدّ: كم سقط عند الأسبوعيّ، وكم عند
الامتداد، وكم وصل إلى الـ4س ولم يرتدّ بعد.

والرمز الذي سقط عند **آخر** مرحلةٍ وحدها هو قائمة مراقبتك غداً.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

log = logging.getLogger("scanner.strategies.topdown_scan")

REQUIRED = ("1d", "4h")

#: ترتيب المراحل — ويُعرَض العدّ عليها، فترتيبها جزءٌ من المعنى
STAGES = ("weekly", "daily", "not_extended", "entry", "ready")

STAGE_LABELS = {
    "weekly": "الأسبوعيّ ليس صاعداً",
    "daily": "اليوميّ ليس صاعداً",
    "not_extended": "ممتدّ — ارتفع بالفعل",
    "entry": "ينتظر ارتداداً على 4س",
    "ready": "جاهز",
}


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def cache_path(market: str) -> Path:
    return _root() / "data" / "topdown" / f"{market}.json"


def load(market: str) -> dict | None:
    try:
        return json.loads(cache_path(market).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scan(market: str, *, limit: int = 0, params: dict | None = None) -> dict:
    """يمسح السوق ويعيد الصفوف مرتّبةً — الجاهز أوّلاً."""
    from scanner import storage
    from scanner.strategies import pes, topdown

    p = params or pes.load_params()
    symbols = storage.stored_symbols(market, "4h")
    if limit:
        symbols = symbols[:limit]

    # الرموز المحظورة لا تُقيَّم — قرار المستخدم يسبق الحساب
    try:
        import sys

        sys.path.insert(0, str(_root() / "web"))
        from dashboard import blocklist
    except Exception:  # noqa: BLE001
        blocklist = None

    rows: list[dict] = []
    by_stage = {k: 0 for k in STAGES}
    skipped = {"no_frames": 0, "blocked": 0, "error": 0}
    t0 = time.perf_counter()

    for sym in symbols:
        if blocklist is not None:
            try:
                if blocklist.is_blocked(market, sym):
                    skipped["blocked"] += 1
                    continue
            except Exception:  # noqa: BLE001
                pass

        frames = {}
        for tf in REQUIRED:
            try:
                frames[tf] = storage.load(market, sym, tf)
            except Exception:  # noqa: BLE001
                frames[tf] = None
        if any(frames.get(tf) is None or len(frames[tf]) == 0
               for tf in REQUIRED):
            skipped["no_frames"] += 1
            continue

        try:
            res = topdown.analyze(frames, params=p)
        except Exception as exc:  # noqa: BLE001
            log.warning("تعذّر تحليل %s: %s", sym, str(exc)[:120])
            skipped["error"] += 1
            continue

        stage = res.get("stage", "weekly")
        if stage in by_stage:
            by_stage[stage] += 1

        entry = res.get("entry") or {}
        rows.append({
            "symbol": sym, "market": market,
            "ok": bool(res.get("ok")),
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "reason": res.get("reason", ""),
            "stages": res.get("stages") or [],
            "weekly_bias": (res.get("weekly") or {}).get("bias", 0),
            "daily_bias": (res.get("daily") or {}).get("bias", 0),
            "weekly_checks": (res.get("weekly") or {}).get("checks", []),
            "daily_checks": (res.get("daily") or {}).get("checks", []),
            "ext_weekly_pct": res.get("ext_weekly_pct"),
            "ext_daily_pct": res.get("ext_daily_pct"),
            "extended": res.get("extended"),
            "entry_ok": bool(entry.get("ok")),
            "entry_zone": entry.get("zone"),
            "entry_bars_ago": entry.get("touched_bars_ago"),
            "entry_checks": entry.get("checks") or [],
            "stop_hint": entry.get("stop_hint"),
            "risk_pct": entry.get("risk_pct"),
            "price": (res.get("daily") or {}).get("close"),
        })

    # ═══ الترتيب: الجاهز أوّلاً ثمّ الأقرب ═══
    #
    # وداخل الجاهز: الأقلّ مخاطرةً أوّلاً — لا الأعلى سعراً ولا
    # الأبجديّ. فالوقف القريب هو ما يجعل الخطأ رخيصاً.
    order = {s: i for i, s in enumerate(reversed(STAGES))}
    rows.sort(key=lambda r: (-order.get(r["stage"], 0),
                             r["risk_pct"] if r["risk_pct"] is not None
                             else 9e9,
                             r["symbol"]))

    out = {
        "market": market,
        "measured_at": time.time(),
        "elapsed_sec": round(time.perf_counter() - t0, 1),
        "evaluated": len(rows),
        "skipped": skipped,
        "by_stage": by_stage,
        "ready": [r["symbol"] for r in rows if r["ok"]],
        "rows": rows,
    }

    path = cache_path(market)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False),
                        encoding="utf-8")
    except OSError as exc:
        log.warning("تعذّر حفظ مسح topdown لـ %s: %s", market, exc)
    return out


__all__ = ["scan", "load", "cache_path", "STAGES", "STAGE_LABELS"]
