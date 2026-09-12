# -*- coding: utf-8 -*-
"""مقارنة قواعد الخروج على صفقاتك الفعلية.

    python tools_exits.py                  # كل الصفقات المحسومة
    python tools_exits.py --market crypto --tf 4h
    python tools_exits.py --risk-pct 1.5   # لاحتساب الكلفة بالـR

═══ لماذا نصفان زمنيّان ═══

القاعدة التي تُختار لأنها الأفضل على بيانات بعينها ستبدو أفضل عليها
دائماً — هذا تعريف الملاءمة الزائدة لا دليل على الجودة. فالمقياس هنا
يقسم الصفقات زمنياً: تُقرأ الأولى لاختيار المرشَّح، وتُقرأ الثانية
للحكم عليه. وقاعدةٌ تتفوّق في النصفين تستحقّ الالتفات؛ وواحدة تتفوّق
في الأوّل وحده هي صدفة اكتُشفت بأثر رجعي.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.exits import RULES, compare_rules  # noqa: E402

DB = ROOT / "data" / "dashboard.sqlite3"


def _connect():
    from tools_postmortem import _open_readonly

    return _open_readonly()


def load(market: str = "", timeframe: str = "") -> list[dict]:
    con = _connect()
    if con is None:
        print("تعذّر فتح قاعدة البيانات.")
        return []
    sql = ("SELECT * FROM dashboard_trade WHERE status IN ('won','lost') "
           "AND entry IS NOT NULL AND stop IS NOT NULL AND target1 IS NOT NULL")
    args: list = []
    if market:
        sql += " AND market = ?"; args.append(market)
    if timeframe:
        sql += " AND timeframe = ?"; args.append(timeframe)
    sql += " ORDER BY signal_at"
    rows = [dict(r) for r in con.execute(sql, args)]
    con.close()
    return rows


def bars_for(trade: dict):
    """شموع ما بعد شمعة الإشارة — من المخزَّن على القرص."""
    from scanner import storage

    try:
        df = storage.load(trade["market"], trade["symbol"], trade["timeframe"])
    except Exception:  # noqa: BLE001
        return []
    if df is None or getattr(df, "empty", True):
        return []
    ct = trade.get("candle_time") or trade.get("signal_at")
    out = []
    for ts, row in zip(df.index, df[["open", "high", "low", "close"]].to_numpy()):
        try:
            if ct and str(ts) <= str(ct):
                continue
        except Exception:  # noqa: BLE001
            pass
        out.append({"time": ts, "open": float(row[0]), "high": float(row[1]),
                    "low": float(row[2]), "close": float(row[3])})
    return out


def show(title: str, stats: dict, base_name: str = "fixed") -> None:
    base = stats.get(base_name)
    print(f"\n─── {title}")
    # الإجمالي والصافي معاً: الفرق بينهما هو الكلفة، وإخفاؤه يجعل
    # خطّ أساس سالباً يبدو عطباً في القاعدة وهو أثر التنفيذ
    print(f"{'القاعدة':32}{'ن':>5}{'نجاح':>8}{'إجمالي':>9}{'صافي':>9}{'مقابل الأساس':>14}")
    rows = sorted(stats.values(), key=lambda s: -s.expectancy)
    for s in rows:
        if not s.n:
            continue
        delta = (s.expectancy - base.expectancy) if base and base.n else 0.0
        mark = "★" if delta > 0.02 else ("·" if abs(delta) <= 0.02 else " ")
        print(f"{mark} {s.label[:29]:30}{s.n:>5}{s.win_rate:>8.1%}"
              f"{s.gross_expectancy:>9.3f}{s.expectancy:>9.3f}{delta:>+14.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="مقارنة قواعد الخروج")
    ap.add_argument("--market", default="")
    ap.add_argument("--tf", default="", dest="timeframe")
    ap.add_argument("--risk-pct", type=float, default=1.0,
                    help="نسبة المخاطرة من رأس المال — لتحويل الكلفة إلى R")
    ap.add_argument("--tier", default="unknown")
    a = ap.parse_args()

    trades = load(a.market, a.timeframe)
    if not trades:
        print("لا صفقات محسومة مطابقة.")
        return 0

    # الكلفة بالـR: العلاقة عكسية مع نسبة المخاطرة — مخاطرة أصغر تعني
    # كلفة أكبر بالـR، وهي الملاحظة التي حكمت تصميم هذا المشروع.
    from scanner.execution import DEFAULT as COST

    per_leg = COST.cost_in_r(a.risk_pct, a.tier, legs=2) / 2.0

    print("=" * 72)
    print("مقارنة قواعد الخروج على الشموع الحقيقية")
    print("=" * 72)
    print(f"صفقات مطابقة: {len(trades)}")
    print(f"كلفة التنفيذ: {per_leg * 2:.3f}R ذهاباً وإياباً "
          f"عند مخاطرة {a.risk_pct}% من رأس المال.")
    if per_leg * 2 > 0.25:
        # العلاقة عكسية: كلفة ثابتة بالنقاط تُقسَم على نسبة المخاطرة.
        # فمخاطرة 1% تحوّل 55 نقطة أساس إلى 0.55R — أكبر من حافّة
        # النظام كلّها. وهذا ليس عيباً في قاعدة الخروج بل في حجم
        # المخاطرة نسبةً إلى الكلفة.
        print(f"⚠ الكلفة وحدها {per_leg * 2:.2f}R — أكبر من أي فرق بين "
              "القواعد أدناه.\n"
              f"  السبب أن الكلفة بالـR = النقاط ÷ نسبة المخاطرة، "
              f"فمخاطرة أكبر تعني كلفة أقلّ بالـR.\n"
              f"  جرّب --risk-pct 3 لترى الأثر. والمقارنة بين القواعد "
              "تبقى صالحة لأن الكلفة تكاد تكون واحدة لها.")

    with_bars = [t for t in trades if bars_for(t)]
    print(f"لها شموع مخزَّنة: {len(with_bars)}")
    if len(with_bars) < 30:
        print("\nالعيّنة أصغر من أن يُبنى عليها قرار — النتائج للاستئناس.")

    cache = {}

    def bars(t):
        key = t["id"]
        if key not in cache:
            cache[key] = bars_for(t)
        return cache[key]

    show("كل الصفقات", compare_rules(with_bars, bars_for=bars,
                                     cost_per_leg_r=per_leg))

    half = len(with_bars) // 2
    if half >= 20:
        first, second = with_bars[:half], with_bars[half:]
        s1 = compare_rules(first, bars_for=bars, cost_per_leg_r=per_leg)
        s2 = compare_rules(second, bars_for=bars, cost_per_leg_r=per_leg)
        show("النصف الأول (للاختيار)", s1)
        show("النصف الثاني (للحكم)", s2)

        base1, base2 = s1.get("fixed"), s2.get("fixed")
        print("\n─── القواعد التي تتفوّق في النصفين معاً")
        survivors = [
            n for n in s1
            if n != "fixed" and s1[n].n and s2[n].n
            and s1[n].expectancy > base1.expectancy + 0.02
            and s2[n].expectancy > base2.expectancy + 0.02
        ]
        if survivors:
            for n in survivors:
                print(f"  ★ {s1[n].label}: "
                      f"{s1[n].expectancy:+.3f} ثمّ {s2[n].expectancy:+.3f}R "
                      f"(الأساس {base1.expectancy:+.3f} ثمّ {base2.expectancy:+.3f})")
            print("\n  هذه مرشَّحة للتبنّي — تتفوّق على بيانات لم تُختَر عليها.")
        else:
            print("  لا شيء. كل تفوّق ظهر في نصف واحد فقط —")
            print("  وهذا ما تنتجه الملاءمة الزائدة، لا الحافّة.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
