# -*- coding: utf-8 -*-
"""مجموعة تدريب مُسمّاة بالمحاكاة — منفصلة وموسومة دائماً.

═══ لماذا وُجدت ═══

قِيس على القاعدة الحقيقية::

    صفقات محسومة              298
    منها مربوطة بلقطة ميزات    29
    صفوف مؤهّلة للتدريب        13      (المطلوب 100)
    وتيرة الربط              0.7/يوم  ← نحو 120 يوماً للحدّ

والـ٢٦٩ الباقية لا تُستردّ: لم تسجّل من أيّ ميزات وُلدت.

لكنّ التسمية لا تحتاج **صفقة**. تحتاج إشارةً لها لقطة ميزات
ومستويات (دخول ووقف وهدف) وشموعاً بعدها. وفي القاعدة::

    509 صفّ مسح  لها لقطة **و** مستويات
                 saudi 200 · us 179 · crypto 130

أي تسعةٌ وثلاثون ضعفاً، وبتنوّع أسواق لا تملكه الصفقات أصلاً —
فالمحسومة الـ٢٩٨ كلّها كريبتو.

═══ والثمن الذي لا يُخفى ═══

تسميةُ محاكاة ليست نتيجة صفقة: بلا انزلاق، بلا تأخّر تنفيذ، بلا
رفض أمر. فالنموذج المتدرّب عليها يتعلّم **هل كانت الخطّة صحيحة**،
لا **هل نجح التنفيذ**.

ولذلك:

    · المجموعتان منفصلتان ولا تُخلطان أبداً.
    · كل صفّ يحمل ``label_source`` صراحةً.
    · والترقية لا تكون إلّا بنجاحٍ على الصفقات الحقيقية — انظر
      ``promotion.py``. المحاكاة تُدرّب، والحقيقة تحكم.

═══ ومنع التسرّب ═══

الشموع تُقتطع **بعد** لحظة القرار قطعاً، لا عندها. وشمعةُ القرار
نفسها مستبعَدة: هي التي بُنيت عليها الميزات، واستعمالها في
التسمية يُسرّب المستقبل إلى الماضي.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("scanner.predictive.dataset_sim")

# أقلّ عدد شموع لاحقة يُسمح بالحكم عليه. أقلّ منه يجعل «لم تُحسم»
# تعني «لم ننتظر» لا «لم يتحرّك السوق».
MIN_FORWARD_BARS = 8

# سقف الانتظار — الصفقة التي لم تُحسم خلال هذا تُعدّ منتهية بالوقت
# لا رابحة ولا خاسرة، فتُستبعد كما تُستبعد الصفقة المعلّقة.
MAX_FORWARD_BARS = 400

LABEL_SOURCE = "simulated"


def _forward_bars(market: str, symbol: str, timeframe: str,
                  decision_ts) -> list[dict]:
    """شموع ما **بعد** لحظة القرار — لا شمعة القرار نفسها.

    الشمعة التي بُنيت عليها الميزات تحمل معلومة القرار. وإدخالها
    في التسمية يعني أن يُقاس النجاح بما عُرف وقت الدخول — وهو
    تسرّبٌ يجعل النموذج ممتازاً في الاختبار عاجزاً في السوق.
    """
    import pandas as pd

    from scanner import storage

    df = storage.load(market, symbol, timeframe)
    if df is None or df.empty:
        return []
    ts = pd.to_datetime(decision_ts, utc=True, errors="coerce")
    if ts is None or pd.isna(ts):
        return []
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
        df = df.copy()
        df.index = idx
    after = df[idx > ts]
    if after.empty:
        return []
    out = []
    for t, row in after.head(MAX_FORWARD_BARS).iterrows():
        out.append({"time": t, "open": float(row["open"]),
                    "high": float(row["high"]), "low": float(row["low"]),
                    "close": float(row["close"])})
    return out


def label_one(scan_row: dict[str, Any]) -> dict[str, Any] | None:
    """يُسمّي صفّ مسحٍ واحداً بمحاكاة الخروج.

    يعيد ``None`` إن تعذّر الحكم — ولا يخترع تسمية. والصفّ الذي لم
    يُحسم يُستبعد كما تُستبعد الصفقة المعلّقة من الإحصاءات.
    """
    from scanner.exits.simulator import RULES, simulate

    entry = scan_row.get("entry")
    stop = scan_row.get("stop")
    target = scan_row.get("target1")
    if entry is None or stop is None or target is None:
        return None
    try:
        entry, stop, target = float(entry), float(stop), float(target)
    except (TypeError, ValueError):
        return None
    if abs(entry - stop) <= 0:
        return None

    bars = _forward_bars(str(scan_row.get("market") or ""),
                         str(scan_row.get("symbol") or ""),
                         str(scan_row.get("timeframe") or ""),
                         scan_row.get("candle_time"))
    if len(bars) < MIN_FORWARD_BARS:
        return None

    # ═══ القاعدة الأساسية عمداً ═══
    #
    # ``fixed`` هي ما يفعله النظام اليوم: وقفٌ ثابت وهدفٌ ثابت.
    # والتسمية بقاعدةٍ أذكى (تتبّع، جني جزئي) تُعلّم النموذج نتيجة
    # استراتيجيةٍ لا تُنفَّذ.
    rule = next((r for r in RULES if r.name == "fixed"), RULES[0])
    side = "sell" if str(scan_row.get("side") or "buy").lower() == "sell" \
        else "buy"
    res = simulate(bars, side=side, entry=entry, stop=stop, target=target,
                   rule=rule, max_bars=MAX_FORWARD_BARS)
    if res is None:
        return None
    # أسماء الحقول من ``TradeResult`` نفسه: ``r_multiple`` و
    # ``exit_reason`` و``bars_held``. والقراءة بأسماء مُخمَّنة
    # (``reason``/``bars``) تعيد الافتراضي صامتةً — فتُستبعد
    # الصفوف كلّها بحجّة «لم تُحسم»، وهو ما وقع فعلاً: 509 من 509.
    r = float(res.r_multiple or 0.0)
    reason = str(res.exit_reason or "")
    # لم تبلغ هدفاً ولا وقفاً حتى نفدت الشموع — لا حكم لها
    if reason not in ("هدف", "وقف", "تعادل"):
        return None

    return {
        "symbol": scan_row.get("symbol"),
        "market": scan_row.get("market"),
        "timeframe": scan_row.get("timeframe"),
        "decision_timestamp": str(scan_row.get("candle_time") or ""),
        "pit_snapshot_id": scan_row.get("pit_snapshot_id") or "",
        "r_multiple": round(r, 4),
        "status": "won" if r > 0 else "lost",
        "bars_held": int(res.bars_held or 0),
        "exit_reason": reason,
        "label_source": LABEL_SOURCE,
    }


def build(scan_rows: list[dict[str, Any]], *,
          limit: int = 0) -> dict[str, Any]:
    """يبني المجموعة من صفوف المسح — ويعزو كل استبعاد إلى سببه."""
    import collections

    from scanner.feature_snapshots import tiers
    from scanner.feature_snapshots.store import get_by_id
    from scanner.predictive.dataset_v3 import encode_row_v3

    rows: list[dict[str, Any]] = []
    skipped: collections.Counter = collections.Counter()
    considered = 0

    for sr in scan_rows:
        if limit and len(rows) >= limit:
            break
        considered += 1
        pit_id = sr.get("pit_snapshot_id") or ""
        if not pit_id:
            skipped["no_snapshot"] += 1
            continue
        pit = get_by_id(pit_id)
        if pit is None:
            skipped["snapshot_missing"] += 1
            continue
        pit_d = pit.to_dict()
        feats = pit_d.get("features") or {}
        if tiers.core_coverage(feats) < tiers.CORE_MIN_COVERAGE:
            skipped["low_core_coverage"] += 1
            continue

        label = label_one(sr)
        if label is None:
            skipped["unresolved"] += 1
            continue

        # يُعاد استعمال ترميز V3 نفسه: مجموعتان بأعمدة مختلفة لا
        # تقارَنان، ولا يصلح نموذجٌ دُرِّب على إحداهما للأخرى.
        trade_like = {
            "trade_id": f"sim:{pit_id}",
            "status": label["status"],
            "r_multiple": label["r_multiple"],
            "signal_at": label["decision_timestamp"],
            "symbol": label["symbol"], "market": label["market"],
            "timeframe": label["timeframe"],
        }
        row = encode_row_v3(trade_like, pit_snapshot=pit_d)
        if not row:
            skipped["encode_failed"] += 1
            continue
        row["label_source"] = LABEL_SOURCE
        row["exit_reason"] = label["exit_reason"]
        row["bars_held"] = label["bars_held"]
        rows.append(row)

    rows.sort(key=lambda r: r.get("signal_at") or "")
    # ═══ العدّ من التسمية لا من مفتاحٍ مفترَض ═══
    #
    # ``encode_row_v3`` يضع النتيجة تحت أسماء ``LabelName``، لا
    # تحت ``r_multiple`` في جذر الصفّ. والعدّ بالمفتاح المفترَض
    # أعطى «نسبة فوز 0٪» بينما ١٣٠ صفّاً بلغت هدفها — رقمٌ يناقض
    # نفسه في السطر التالي، ولو مرّ لسمّم كل ما بُني عليه.
    wins = sum(1 for r in rows
               if str(r.get("exit_reason")) == "هدف")
    return {
        "label_source": LABEL_SOURCE,
        "considered": considered,
        "eligible_count": len(rows),
        "win_rate": round(100 * wins / len(rows), 1) if rows else None,
        "skipped": dict(skipped),
        "rows": rows,
    }


__all__ = ["build", "label_one", "LABEL_SOURCE", "MIN_FORWARD_BARS",
           "MAX_FORWARD_BARS"]
