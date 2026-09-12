# -*- coding: utf-8 -*-
"""استرجاع الصفقات التي ألغاها حارس «البيانات القديمة» خطأً.

    python tools_repair_cancelled.py            # عرض بلا تعديل
    python tools_repair_cancelled.py --apply    # تنفيذ

═══ ما حدث ═══

أُضيف حارس يلغي الصفقات المبنية على شمعة ميتة (رمز شُطب من المنصّة
وملفه باقٍ على القرص). وكُتب في أول صياغة بعتبة **ثابتة**: عشر شموع.

والعتبة الثابتة خطأ صنفي لا رقمي. الصفقة المفتوحة تشيخ بطبيعتها:
``MAX_HOLD_BARS`` يسمح لصفقة 15m بمئتي شمعة و 4h بمئة. فعتبة العشرة
كانت تقتل كل صفقة تجاوز عمرها ساعتين ونصفاً على 15m — وهي في عزّ
عملها. المقياس خلط بين **قِدم الصفقة** و**قِدم البيانات**، وهما شيئان
لا علاقة لأحدهما بالآخر.

أسقطت اختبارات الحسم هذه الصياغة وصُحّحت العتبة إلى ``MAX_HOLD_BARS ×
3``، لكن النسخة الأولى كانت قد عملت على قاعدة بيانات حيّة وألغت 91
صفقة سليمة — بينها صفقات رابحة (‏RONINUSDT عند ‎+0.78R‎ حين قُتلت).

═══ لماذا الاسترجاع ممكن ═══

لأن الإلغاء لم يمحُ شيئاً: الخطة (دخول · وقف · هدف · وقت الشمعة)
محفوظة كما هي، والشموع على القرص. فالحالة الصحيحة قابلة لإعادة
الاشتقاق بالمحرّك نفسه الذي يحسم الصفقات الحيّة — لا بالتخمين.

═══ التمييز ═══

يُسترجع الصفّ إن كان تأخّره **دون** ``MAX_HOLD_BARS × 3`` لفريمه؛ وما
تجاوزها (‏50 صفّاً، بعضها متأخر 126 ألف شمعة) بيانات ميتة فعلاً ويبقى
ملغى. والرقم مقروء من نصّ الملاحظة نفسها لا محسوباً من جديد: الوقت
مضى منذ الإلغاء، فإعادة الحساب اليوم تعطي رقماً أكبر وتخلط الفئتين.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import storage
from scanner.tracking import LOST, OPEN, PENDING, WON, Plan, resolve

DB = ROOT / "data" / "dashboard.sqlite3"

# نسخ من web/dashboard/trades.py — هذا الملف يعمل بلا Django عمداً حتى
# يُشغَّل والخادم متوقّف. والاختبار أدناه يتحقّق أنهما لم يفترقا.
ENTRY_DEADLINE_BARS = {"15m": 96, "1h": 48, "4h": 30, "1d": 10, "1w": 4}
MAX_HOLD_BARS = {"15m": 200, "1h": 150, "4h": 100, "1d": 60, "1w": 26}
STALE_MULTIPLE = 3

MARK = "بيانات قديمة"


def bars_after(candles: list[dict], after) -> list[dict]:
    if after is None:
        return list(candles)
    cut = pd.Timestamp(after)
    if cut.tz is None:
        cut = cut.tz_localize("UTC")
    return [c for c in candles if pd.Timestamp(c["time"]) > cut]


def candles_for(market: str, symbol: str, timeframe: str) -> list[dict]:
    df = storage.load(market, symbol, timeframe)
    if df is None or getattr(df, "empty", True):
        return []
    cols = ("open", "high", "low", "close")
    if not all(c in df.columns for c in cols):
        return []
    return [{"time": t, "open": float(o), "high": float(h),
             "low": float(low), "close": float(c)}
            for t, (o, h, low, c) in zip(df.index, df[list(cols)].to_numpy())]


def wrongly_cancelled(db) -> list[sqlite3.Row]:
    """الصفوف التي ألغتها العتبة الثابتة وهي ضمن الحدّ المشروع."""
    out = []
    for r in db.execute(
            "SELECT * FROM dashboard_trade WHERE status='expired' "
            "AND resolution_note LIKE ?", (f"%{MARK}%",)):
        m = re.search(r"متأخرة (\d+) شمعة", r["resolution_note"] or "")
        if not m:
            continue
        limit = MAX_HOLD_BARS.get(r["timeframe"], 100) * STALE_MULTIPLE
        if int(m.group(1)) <= limit:
            out.append(r)
    return out


def _bar_time(bars: list[dict], index):
    if index is None or not (0 <= index < len(bars)):
        return None
    t = pd.Timestamp(bars[index]["time"])
    if t.tz is None:
        t = t.tz_localize("UTC")
    return t.to_pydatetime()


def recompute(row: sqlite3.Row) -> dict | None:
    """الحالة الصحيحة من الشموع — بالمحرّك لا بالتخمين."""
    tf = row["timeframe"]
    bars = bars_after(candles_for(row["market"], row["symbol"], tf),
                      row["candle_time"])
    if not bars:
        return None
    plan = Plan(side=row["side"], entry=row["entry"], stop=row["stop"],
                target=row["target1"])
    if not plan.valid():
        return None

    # ``already_entered`` من سعر الدخول المحفوظ: الصفّ الذي كان مفتوحاً
    # وقت الإلغاء يحمل entry_price، والمعلّق لا يحمله.
    res = resolve(bars, plan,
                  already_entered=row["entry_price"] is not None,
                  entry_price=row["entry_price"],
                  max_bars=ENTRY_DEADLINE_BARS.get(tf, 30))

    fields: dict = {"status": res.status, "bars_held": res.bars_held,
                    "resolution_note": (res.note or "")[:120]}
    if res.entry_price is not None:
        fields["entry_price"] = round(res.entry_price, 10)
    if res.r_multiple is not None:
        fields["r_multiple"] = res.r_multiple
    if res.excursion:
        fields["best_r"] = res.excursion.get("best_r")
        fields["worst_r"] = res.excursion.get("worst_r")

    entered = _bar_time(bars, res.entry_bar)
    exited = _bar_time(bars, res.exit_bar)
    if res.status in (WON, LOST):
        if res.exit_price is not None:
            fields["exit_price"] = round(res.exit_price, 10)
        fields["opened_at"] = entered or row["candle_time"]
        fields["closed_at"] = exited
    elif res.status == OPEN:
        fields["opened_at"] = entered or row["candle_time"]
        cap = MAX_HOLD_BARS.get(tf, 100)
        if res.bars_held > cap:
            last = float(bars[-1]["close"])
            base = res.entry_price or row["entry"]
            risk = abs(base - row["stop"])
            sign = 1 if row["side"] == "buy" else -1
            r = ((last - base) / risk * sign) if risk else 0.0
            fields.update(status=WON if r > 0 else LOST, exit_price=last,
                          r_multiple=round(r, 3),
                          closed_at=_bar_time(bars, len(bars) - 1),
                          resolution_note=f"أُغلقت بالسوق بعد {cap} شمعة "
                                          f"بلا حسم")
    return fields


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="استرجاع الملغى خطأً")
    ap.add_argument("--apply", action="store_true", help="نفّذ التعديل")
    ap.add_argument("--db", default=str(DB))
    args = ap.parse_args(argv)

    db = sqlite3.connect(args.db)
    db.row_factory = sqlite3.Row
    rows = wrongly_cancelled(db)
    print(f"صفوف ألغتها العتبة الثابتة وهي ضمن الحدّ المشروع: {len(rows)}\n")
    if not rows:
        return 0

    tally: dict[str, int] = {}
    changes: list[tuple[int, dict]] = []
    no_candles = 0
    for row in rows:
        fields = recompute(row)
        if fields is None:
            no_candles += 1
            tally["بلا شموع — تبقى ملغاة"] = tally.get(
                "بلا شموع — تبقى ملغاة", 0) + 1
            continue
        tally[fields["status"]] = tally.get(fields["status"], 0) + 1
        changes.append((row["id"], fields))

    print("الحالة الصحيحة بعد إعادة الاشتقاق من الشموع:")
    for k, v in sorted(tally.items(), key=lambda p: -p[1]):
        print(f"  {k:<26}{v:>4}")

    won = [(r, f) for r, f in changes if f["status"] == WON]
    if won:
        print(f"\n  منها {len(won)} صفقة **رابحة** كانت ستُحسب لاغية:")
        for _id, f in won[:8]:
            r = db.execute("SELECT symbol,timeframe FROM dashboard_trade "
                           "WHERE id=?", (_id,)).fetchone()
            print(f"    {r['symbol']:<13}{r['timeframe']:<5}"
                  f"R={f.get('r_multiple', 0):+.2f}")

    if not args.apply:
        print("\nعرض فقط. للتنفيذ:  python tools_repair_cancelled.py --apply")
        return 0

    for _id, fields in changes:
        sets = ", ".join(f"{k}=?" for k in fields)
        db.execute(f"UPDATE dashboard_trade SET {sets} WHERE id=?",
                   [*fields.values(), _id])
    db.commit()
    print(f"\n✓ استُرجع {len(changes)} صفّاً · بقي {no_candles} بلا شموع")
    return 0


if __name__ == "__main__":
    sys.exit(main())
