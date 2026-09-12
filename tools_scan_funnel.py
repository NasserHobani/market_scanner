# -*- coding: utf-8 -*-
"""أين تتبخّر الرموز بين الاكتشاف والشاشة؟

═══ لماذا وُجدت ═══

قالت أداة التشخيص «الاكتشاف سليم: 400 رمزاً» وظلّت اللوحة تعرض
عشرة. وكان بينهما ستّ مراحل، كلٌّ منها قد يبتلع الرموز بصمت:

    اكتشاف → بوابة الحداثة → جلب → حدّ الشموع → حدّ القِدم
           → تسجيل → عرض

وفحصُ المرحلة الأولى وحدها يقول «سليم» بصدق، ثمّ لا يفسّر شيئاً.
والتنقّل بينها بالتخمين كلّفنا جولات.

فهذه الأداة تمشي المسار كلّه وتعدّ الباقي عند كل مرحلة، وتقول عند
أيّها وقع الفقد ولماذا. لا تكتب شيئاً ولا تحفظ دورة.

    python tools_scan_funnel.py us
    python tools_scan_funnel.py saudi --limit 40
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

OK, BAD, WARN, DOT = "✓", "✗", "!", "·"


def _bar(n: int, total: int, width: int = 28) -> str:
    if total <= 0:
        return " " * width
    filled = max(0, min(width, round(width * n / total)))
    return "█" * filled + "░" * (width - filled)


def main() -> int:
    ap = argparse.ArgumentParser(description="قِمع المسح")
    ap.add_argument("market", nargs="?", default="us")
    ap.add_argument("--timeframe", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="اقتصر على أوّل N رمزاً (للتجربة السريعة)")
    a = ap.parse_args()

    from scanner import sessions, storage
    from scanner.adapters import get_adapter
    from scanner.config import load_market

    cfg_root = Path(os.environ.get("SCANNER_CONFIG_DIR") or (ROOT / "config"))
    cfg_path = cfg_root / f"{a.market}.yaml"
    if not cfg_path.exists():
        print(f"{BAD} ملف السوق غير موجود: {cfg_path}")
        return 1
    cfg = load_market(cfg_path)
    tf = a.timeframe or cfg.timeframes[0]

    print("=" * 62)
    print(f"قِمع المسح — سوق {a.market} · فريم {tf}")
    print("=" * 62)
    print(f"  محوّل الشموع: {cfg.adapter}"
          + (f"   ·   محوّل الاكتشاف: {cfg.universe_adapter}"
             if cfg.universe_adapter else ""))
    print(f"  السوق الآن: {'مفتوح' if sessions.is_open(a.market) else 'مغلق'}")

    # ── ١) الاكتشاف ──
    print("\n[١] الاكتشاف")
    if cfg.universe == "list":
        symbols = list(cfg.symbols)
        print(f"  {WARN} الكون list — {len(symbols)} رمزاً من الملف")
    else:
        disc = get_adapter(cfg.universe_adapter or cfg.adapter)
        try:
            symbols = list(disc.usdt_universe(cfg.min_quote_volume,
                                              top_n=cfg.top_n))
            print(f"  {OK} {len(symbols)} رمزاً")
            note = getattr(disc, "last_universe_note", "")
            if note:
                print(f"      {WARN} {note[:100]}")
        except Exception as exc:  # noqa: BLE001
            from scanner import universe_cache as ucache

            print(f"  {BAD} تعثّر الاكتشاف: {str(exc)[:110]}")
            saved = ucache.load(cfg.universe_adapter or cfg.adapter)
            if saved and len(saved["symbols"]) > len(cfg.symbols or []):
                symbols = list(saved["symbols"])
                print(f"      {WARN} الكون المحفوظ: "
                      f"{ucache.describe(cfg.universe_adapter or cfg.adapter)}")
            else:
                symbols = list(cfg.symbols)
                print(f"      {BAD} ولا كون محفوظ — النزول إلى الملف: "
                      f"{len(symbols)} رمزاً")
    if a.limit:
        symbols = symbols[: a.limit]
        print(f"      (مقصور على {len(symbols)} بأمر --limit)")
    discovered = len(symbols)
    if not discovered:
        print(f"\n{BAD} لا رموز — لا معنى لبقيّة القِمع.")
        return 1

    # ── ٢) ما على القرص ──
    print("\n[٢] الشموع على القرص")
    on_disk = set(storage.stored_symbols(a.market, tf))
    have = [s for s in symbols if s in on_disk]
    lack = [s for s in symbols if s not in on_disk]
    print(f"  {OK if have else WARN} لها ملف: {len(have)}")
    print(f"  {DOT} بلا ملف: {len(lack)}"
          + (f"  ← ستُجلَب في المسح ({', '.join(lack[:5])} …)" if lack else ""))
    # هذا بالضبط ما كان يوقف المسح: «بلا ملف» ليس عطلاً بل بداية.
    if lack and len(lack) > discovered * 0.5:
        print(f"      {WARN} الأكثرية بلا ملف — هذه حالة **إقلاع** لا عطل.")

    # ── ٣) بوابة الحداثة ──
    print("\n[٣] بوابة الحداثة")
    from scanner.market_sync import get_service

    try:
        gate = get_service().scan_freshness_gate(
            a.market, tf, symbols=symbols, auto_refresh=False)
    except Exception as exc:  # noqa: BLE001
        gate = {"ok": False, "code": "EXC", "reason": str(exc)[:160],
                "counts": {}}
    c = gate.get("counts") or {}
    for k, label in (("fresh", "حديث"), ("stale", "متأخّر"),
                     ("critical", "حرج"), ("missing", "بلا ملف"),
                     ("error", "خطأ")):
        n = c.get(k, 0)
        if n:
            print(f"  {DOT} {label:8} {n:5}  {_bar(n, discovered)}")
    mark = OK if gate.get("ok") else BAD
    print(f"  {mark} {gate.get('code')} — {str(gate.get('reason'))[:90]}")
    if not gate.get("ok"):
        print("\n  ← المسح يتوقّف هنا ولا يحفظ دورة، فتبقى اللوحة على")
        print("    آخر دورة ناجحة مهما قدُمت. هذا هو موضع الفقد.")
        print("    للتجاوز مؤقّتاً: python web/manage.py scan "
              f"--market {a.market} --skip-freshness-gate")
        return 1

    # ── ٤) حدّا الشموع والقِدم على ما هو موجود ──
    print("\n[٤] حدّا الشموع والقِدم (على ما له ملف)")
    MIN_CANDLES, STALE_BARS = 60, 3
    thin, old, fine = [], [], []
    for s in have:
        df = storage.load(a.market, s, tf)
        if df is None or len(df) < MIN_CANDLES:
            thin.append((s, 0 if df is None else len(df)))
        elif storage.is_stale(df, tf, max_bars=STALE_BARS, market=a.market):
            behind = storage.bars_behind(df, tf, market=a.market) or 0
            old.append((s, behind))
        else:
            fine.append(s)
    print(f"  {DOT} أقلّ من {MIN_CANDLES} شمعة: {len(thin)}"
          + (f"  ({', '.join(f'{s}:{n}' for s, n in thin[:5])})" if thin else ""))
    print(f"  {DOT} أقدم من {STALE_BARS} جلسات: {len(old)}"
          + (f"  ({', '.join(f'{s}:{b:.1f}' for s, b in old[:5])})" if old else ""))
    print(f"  {OK} تعبر: {len(fine)}")
    if old and len(old) == len(have) and have:
        print(f"      {WARN} **كلّها** قديمة — القياس بزمن السوق، فهذا")
        print("        يعني توقّف الجلب فعلاً لا عطلة نهاية أسبوع.")

    # ── ٥) الخلاصة ──
    expected = len(fine) + len(lack)
    print("\n" + "=" * 62)
    print(f"  اكتُشف        {discovered:5}  {_bar(discovered, discovered)}")
    print(f"  له ملف صالح   {len(fine):5}  {_bar(len(fine), discovered)}")
    print(f"  سيُجلَب       {len(lack):5}  {_bar(len(lack), discovered)}")
    print(f"  المتوقَّع مسحه {expected:5}  {_bar(expected, discovered)}")
    print("=" * 62)

    # ── ٦) آخر دورة محفوظة — الفجوة بين المتوقَّع والمعروض ──
    try:
        import sqlite3

        db = ROOT / "data" / "dashboard.sqlite3"
        if db.exists():
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            row = con.execute(
                "SELECT id, started_at, symbols_scanned, "
                "COALESCE(universe_source,'—') FROM dashboard_scanrun "
                "WHERE market=? AND kind='scan' ORDER BY id DESC LIMIT 1",
                (a.market,)).fetchone()
            if row:
                print(f"\n  آخر دورة محفوظة: #{row[0]} · {str(row[1])[:19]} "
                      f"· {row[2]} رمزاً · مصدر={row[3]}")
                if row[2] < expected * 0.5:
                    print(f"  {WARN} اللوحة تعرض {row[2]} بينما المتوقَّع "
                          f"{expected} — الدورة قديمة، أعد المسح.")
            else:
                print(f"\n  {WARN} لا دورة محفوظة لهذا السوق بعد.")
    except Exception as exc:  # noqa: BLE001
        print(f"\n  ({DOT} تعذّرت قراءة سجلّ الدورات: {str(exc)[:60]})")

    print(f"\n  للمسح: python web/manage.py scan --market {a.market}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
