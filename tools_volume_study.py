# -*- coding: utf-8 -*-
"""هل يفصل الفوليوم الرابح عن الخاسر؟ — قياسٌ على صفقاتك أنت.

═══ لماذا القياس قبل الإضافة ═══

أنماط الحجم مشهورةٌ بأنّها تصف الماضي ببلاغة ولا تتنبّأ. وإضافتها
إلى التقييم لأنّها «معروفة» تُنتج نظاماً يبدو أذكى وهو أضعف: كل
مكوّنٍ جديد يخفّف وزن ما يعمل فعلاً.

فهذه الأداة تحسب كل خاصيّة **عند شمعة الدخول** لكل صفقة محسومة —
بلا نظرة إلى الأمام — ثمّ تسأل سؤالاً واحداً: هل قيمتها عند الرابحات
تختلف عنها عند الخاسرات اختلافاً يتجاوز الصدفة؟

والأدوات نفسها المستعملة في تشريح الصفقات: حجم الأثر (Cohen's d)،
واختبار ثنائي الحدّ الدقيق، وتصحيح بنجاميني-هوكبرغ لتعدّد المقارنات.

    python tools_volume_study.py
    python tools_volume_study.py --market crypto --min 30
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

OK, BAD, DOT, WARN = "✓", "✗", "·", "!"


def _load_trades(market: str = "", limit: int = 0) -> list[dict]:
    """الصفقات المحسومة من نسخة القاعدة — لا نلمس قاعدةً عاملة."""
    src = ROOT / "data" / "dashboard.sqlite3"
    if not src.exists():
        return []
    tmp = Path(tempfile.mkdtemp())
    dst = tmp / "c.sqlite3"
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)
    con.row_factory = sqlite3.Row
    sql = ("SELECT symbol, market, timeframe, side, status, r_multiple, "
           "candle_time, opened_at FROM dashboard_trade "
           "WHERE status IN ('won','lost') AND r_multiple IS NOT NULL")
    args: list = []
    if market:
        sql += " AND market=?"
        args.append(market)
    sql += " ORDER BY id"
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    shutil.rmtree(tmp, ignore_errors=True)
    return rows[:limit] if limit else rows


def _entry_features(df, ts) -> dict | None:
    """الخصائص عند شمعة الدخول — من بياناتٍ حتى تلك الشمعة فقط.

    ═══ ولا شمعةً بعدها ═══

    القطع عند شمعة الدخول ليس تدقيقاً زائداً: بروفايلٌ يشمل ما جرى
    **بعد** الدخول يعرف كيف انتهت الصفقة، فيبدو كل مؤشّر نبيّاً.
    وهذا أسهل خطأ يقع فيه قياسٌ كهذا، وأصعبه اكتشافاً — لأنّ
    النتيجة تكون ممتازة.
    """
    import numpy as np
    import pandas as pd

    from scanner.indicators import volume_profile as vp
    from scanner.indicators import vsa

    try:
        t = pd.Timestamp(ts)
        t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    except Exception:  # noqa: BLE001
        return None

    idx = df.index
    pos = idx.searchsorted(t, side="right") - 1
    if pos < 60:                    # سياق غير كافٍ للمتوسّطات
        return None
    hist = df.iloc[: pos + 1]       # حتى شمعة الدخول ضمناً

    close = float(hist["close"].iloc[-1])
    out: dict = {}

    prof = vp.build(hist.tail(180))
    if prof is not None and prof.value_width > 0:
        # المسافة بوحدة عرض منطقة القيمة — قابلة للمقارنة بين الرموز
        out["vp_dist_poc"] = (close - prof.poc) / prof.value_width
        out["vp_dist_vah"] = (close - prof.vah) / prof.value_width
        out["vp_dist_val"] = (close - prof.val) / prof.value_width
        out["vp_inside_value"] = 1.0 if prof.val <= close <= prof.vah else 0.0
        out["vp_above_poc"] = 1.0 if close > prof.poc else 0.0
        rng = prof.high - prof.low
        out["vp_value_width"] = prof.value_width / rng if rng > 0 else np.nan

    rv = vp.rolling_vwap(hist, 20)
    if len(rv) and np.isfinite(rv.iloc[-1]) and rv.iloc[-1] > 0:
        out["vwap_dist_20"] = (close - float(rv.iloc[-1])) / float(rv.iloc[-1])
        out["above_vwap_20"] = 1.0 if close > float(rv.iloc[-1]) else 0.0

    a_lo = vp.anchor_swing(hist, 120, "low")
    av = vp.anchored_vwap(hist, a_lo)
    if len(av) and np.isfinite(av.iloc[-1]) and av.iloc[-1] > 0:
        out["avwap_low_dist"] = (close - float(av.iloc[-1])) / float(av.iloc[-1])
        out["above_avwap_low"] = 1.0 if close > float(av.iloc[-1]) else 0.0

    f = vsa.features(hist, 20)
    if len(f):
        last = f.iloc[-1]
        for k in ("vol_ratio", "range_ratio", "close_pos", "body_ratio",
                  "spread_per_volume"):
            v = last.get(k)
            if v is not None and np.isfinite(v):
                out[f"vsa_{k}"] = float(v)

    bar = vsa.classify(hist, 20)
    if bar is not None:
        for name in vsa.ARABIC:
            out[f"sig_{name}"] = 1.0 if name in bar.signals else 0.0

    return out or None


def main() -> int:
    ap = argparse.ArgumentParser(description="دراسة الفوليوم")
    ap.add_argument("--market", default="")
    ap.add_argument("--min", type=int, default=25,
                    help="أقلّ عدد صفقات لكل مجموعة")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    import numpy as np

    from scanner import storage
    from scanner.postmortem.separation import (benjamini_hochberg,
                                               binom_two_sided_p,
                                               wilson_interval)

    trades = _load_trades(a.market, a.limit)
    print("=" * 68)
    print("هل يفصل الفوليوم الرابح عن الخاسر؟")
    print("=" * 68)
    if not trades:
        print(f"\n{BAD} لا صفقات محسومة.")
        return 1
    print(f"  صفقات محسومة: {len(trades)}")

    rows: list[tuple[dict, bool, float]] = []
    skipped = 0
    cache: dict[tuple, object] = {}
    for t in trades:
        key = (t["market"], t["symbol"], t["timeframe"])
        if key not in cache:
            cache[key] = storage.load(*key)
        df = cache[key]
        if df is None or len(df) < 80:
            skipped += 1
            continue
        feats = _entry_features(df, t["candle_time"] or t["opened_at"])
        if not feats:
            skipped += 1
            continue
        rows.append((feats, t["status"] == "won", float(t["r_multiple"])))

    print(f"  قِيست: {len(rows)}   تُخطّيت (بلا شموع كافية): {skipped}")
    if len(rows) < a.min * 2:
        print(f"\n{WARN} عيّنة أصغر من أن تُقرأ.")
        return 0

    wins = sum(1 for _, w, _ in rows if w)
    print(f"  رابحة {wins} · خاسرة {len(rows) - wins} "
          f"({100.0 * wins / len(rows):.1f}٪ أساس)")

    names = sorted({k for f, _, _ in rows for k in f})
    findings = []
    for name in names:
        vals_w = [f[name] for f, w, _ in rows if w and name in f
                  and np.isfinite(f[name])]
        vals_l = [f[name] for f, w, _ in rows if not w and name in f
                  and np.isfinite(f[name])]
        if len(vals_w) < a.min or len(vals_l) < a.min:
            continue
        mw, ml = float(np.mean(vals_w)), float(np.mean(vals_l))
        sw, sl = float(np.std(vals_w, ddof=1)), float(np.std(vals_l, ddof=1))
        nw, nl = len(vals_w), len(vals_l)
        pooled = np.sqrt(((nw - 1) * sw ** 2 + (nl - 1) * sl ** 2)
                         / max(1, nw + nl - 2))
        d = (mw - ml) / pooled if pooled > 1e-12 else 0.0

        # الثنائية تُختبر كنسبة فوز بدل فرق المتوسّطات
        binary = set(np.unique(np.concatenate([vals_w, vals_l]))) <= {0.0, 1.0}
        p = 1.0
        extra = ""
        if binary:
            on = [(f[name], w) for f, w, _ in rows if name in f]
            k = sum(1 for v, w in on if v == 1.0 and w)
            n = sum(1 for v, _ in on if v == 1.0)
            if n >= a.min:
                base = wins / len(rows)
                p = binom_two_sided_p(k, n, base)
                lo, hi = wilson_interval(k, n)
                extra = (f"عند 1: {k}/{n} = {100.0 * k / n:.0f}٪ "
                         f"[{100 * lo:.0f}–{100 * hi:.0f}] · الأساس "
                         f"{100 * base:.0f}٪")
            else:
                continue
        else:
            # ‏t تقريبي عبر z على فرق المتوسّطات
            se = np.sqrt(sw ** 2 / nw + sl ** 2 / nl)
            z = abs(mw - ml) / se if se > 1e-12 else 0.0
            p = float(np.exp(-0.717 * z - 0.416 * z * z)) if z > 0 else 1.0
            extra = f"رابحة {mw:+.3f} · خاسرة {ml:+.3f}"
        findings.append({"name": name, "d": d, "p": p, "extra": extra,
                         "n": nw + nl})

    if not findings:
        print(f"\n{WARN} لا خاصيّة بلغت الحدّ الأدنى للعيّنة.")
        return 0

    flags = benjamini_hochberg([f["p"] for f in findings], alpha=0.05)
    for f, keep in zip(findings, flags):
        f["survives"] = bool(keep)
    findings.sort(key=lambda f: -abs(f["d"]))

    print(f"\n{'الخاصيّة':26} {'d':>7} {'p':>9}  الحكم")
    print("─" * 68)
    for f in findings:
        mark = OK if f["survives"] else DOT
        verdict = "يفصل (بعد التصحيح)" if f["survives"] else "ضمن الصدفة"
        print(f"{mark} {f['name']:24} {f['d']:+7.2f} {f['p']:9.4f}  {verdict}")
        print(f"    {f['extra']}")

    strong = [f for f in findings if f["survives"]]
    print("\n" + "=" * 68)
    if strong:
        print(f"{OK} {len(strong)} خاصيّة تفصل فعلاً — هذه وحدها تستحقّ")
        print("   الدخول في التقييم:")
        for f in strong:
            print(f"     · {f['name']}  (d={f['d']:+.2f})")
    else:
        print(f"{WARN} لا خاصيّة نجت من تصحيح تعدّد المقارنات.")
        print("   وهذا نتيجةٌ لا فشل: إضافتها إلى التقييم كانت ستُضعفه")
        print("   بتخفيف وزن ما يعمل فعلاً.")
    print(f"\n{DOT} حجم الأثر: 0.2 ضئيل · 0.5 متوسّط · 0.8 كبير.")
    print(f"{DOT} العيّنة {len(rows)} صفقة — والحكم يتغيّر بتغيّرها.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
