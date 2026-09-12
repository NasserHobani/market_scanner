# -*- coding: utf-8 -*-
"""مساهمة المستشار الذكي — بالأرقام لا بالانطباع.

    python tools_ai_contribution.py            # التقرير
    python tools_ai_contribution.py --relink   # ربط أثري ثم التقرير

═══ لماذا هذا الملف ═══

كان المستشار يُشغَّل على كل توصية جاهزة ويُخزَّن رأيه تحت حقل اسمه
``trade_id``، وهو في الحقيقة معرّف صفّ ``ScanResult``. فتراكمت 149
مراجعة لا تنضمّ إلى أي نتيجة: **134 دقيقة من زمن النموذج أنتجت رأياً
لا يمكن الحكم عليه**.

والحكم هنا ليس ترفاً. مبدأ المشروع صريح: *الميزة لا توجد حتى تُقاس
مساهمتها*. ومستشار لا تُقاس مساهمته ليس ميزة بل كلفة — كلفة زمن،
وكلفة ثقة، وكلفة قرارات تتأثّر برأي لم يُختبر.

═══ ما يقيسه ═══

يضمّ كل مراجعة إلى الصفقة التي حكمت عليها، ثم يسأل السؤال الوحيد
المهمّ: **هل الصفقات التي وافق عليها أفضل من التي عارضها؟**

ويعرض فاصل ثقة لكل شريحة. الفرق الذي تتداخل فواصله ليس فرقاً — وهذا
تحديداً ما يميّز القياس عن الانطباع: مستشار عشوائي سيُظهر فرقاً في
عيّنة صغيرة، ولن يُظهر فاصلين منفصلين.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.tracking import summarize

DB = ROOT / "data" / "dashboard.sqlite3"
HISTORY = ROOT / "data" / "advisor_history.jsonl"
LOCAL = ROOT / "data" / "local_ai_history.jsonl"

AGREEMENTS = ("agree", "partial", "disagree")


def read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _scan_key_map(db) -> dict:
    """معرّف صفّ المسح ← مفتاحه الطبيعي."""
    return {
        str(r["id"]): (r["symbol"], r["market"], r["timeframe"],
                       str(r["candle_time"]))
        for r in db.execute("SELECT id,symbol,market,timeframe,candle_time "
                            "FROM dashboard_scanresult")
    }


def _trade_by_key(db) -> dict:
    out: dict = {}
    for r in db.execute("SELECT id,symbol,market,timeframe,candle_time,source "
                        "FROM dashboard_trade"):
        key = (r["symbol"], r["market"], r["timeframe"], str(r["candle_time"]))
        # الآلية أولاً: المراجعة تحكم على توصية المحرّك لا على صفقة يدوية
        if key not in out or r["source"] == "auto":
            out[key] = str(r["id"])
    return out


def relink(rows: list[dict], db) -> tuple[list[dict], dict]:
    """يستنتج معرّف الصفقة الصحيح لكل مراجعة.

    المسار: ``trade_id`` المسجَّل (وهو معرّف صفّ مسح) ← المفتاح الطبيعي
    لذلك الصفّ ← الصفقة التي تحمل المفتاح نفسه. والمفتاح الطبيعي هو
    الرابط الصحيح لأن الصفقة والصفّ يشتركان في (رمز · سوق · فريم ·
    وقت الشمعة) بحكم إنشائهما، لا بحكم تقارب أرقامهما.
    """
    scan_keys = _scan_key_map(db)
    trades = _trade_by_key(db)
    stats = {"total": len(rows), "already": 0, "relinked": 0,
             "no_scan_row": 0, "no_trade": 0}

    out: list[dict] = []
    live_trade_ids = {str(r["id"]) for r in
                      db.execute("SELECT id FROM dashboard_trade")}
    for r in rows:
        raw = str(r.get("trade_id") or "")
        if raw and raw in live_trade_ids:
            stats["already"] += 1
            out.append({**r, "_trade_id": raw})
            continue
        key = scan_keys.get(raw)
        if key is None:
            key = _key_from_review(r, db)
        if key is None:
            stats["no_scan_row"] += 1
            continue
        tid = trades.get(key)
        if not tid:
            stats["no_trade"] += 1
            continue
        stats["relinked"] += 1
        out.append({**r, "_trade_id": tid})
    return out, stats


def _key_from_review(r: dict, db) -> tuple | None:
    """احتياط: مراجعة تحمل الرمز والوقت بلا معرّف صفّ صالح."""
    sym = r.get("symbol")
    ct = r.get("candle_time")
    if not sym or not ct:
        return None
    row = db.execute(
        "SELECT symbol,market,timeframe,candle_time FROM dashboard_scanresult "
        "WHERE symbol=? AND candle_time=? LIMIT 1", (sym, ct)).fetchone()
    return (row["symbol"], row["market"], row["timeframe"],
            str(row["candle_time"])) if row else None


def discrimination(rows: list[dict]) -> dict:
    """هل الحكم يحمل معلومة أصلاً — قبل السؤال عن صحّته؟

    قاضٍ يقول «جزئي» تسع مرّات من عشر لا يميّز شيئاً مهما بلغت دقّته:
    مخرجه شبه ثابت، فلا يمكن أن يفصل صفقة عن أخرى. وهذا يُقاس قبل
    الأداء ولا يحتاج نتائج — وهو ما يجعله الفحص الأول لا الأخير.

    المقياس إنتروبيا شانون منسوبةً إلى أقصاها: 100٪ يعني توزيعاً
    متوازناً بين الأحكام الثلاثة، وصفر يعني حكماً واحداً دائماً.

    القياس الفعلي فرّق بين المزوّدَين تفريقاً حاداً:

        advisor : 48 موافق · 55 جزئي · 46 معارض  ⇒ 100٪
        local   :  1 موافق · 48 جزئي ·  5 معارض  ⇒  36٪

    الثاني يكاد لا يقول شيئاً، وزمنه ضعف الأول.
    """
    import math
    from collections import Counter

    counts = Counter(r.get("agreement") for r in rows if r.get("agreement"))
    total = sum(counts.values())
    if not total:
        return {"total": 0, "entropy_pct": 0.0, "top": "", "top_pct": 0.0,
                "usable": False}
    entropy = -sum((v / total) * math.log2(v / total)
                   for v in counts.values() if v)
    ceiling = math.log2(len(AGREEMENTS))
    top, top_n = counts.most_common(1)[0]
    pct = entropy / ceiling * 100 if ceiling else 0.0
    return {"total": total, "counts": dict(counts), "entropy_pct": pct,
            "top": top, "top_pct": top_n / total * 100,
            # دون النصف: الحكم شبه ثابت فلا يصلح للتمييز مهما كان دقيقاً
            "usable": pct >= 50.0}


def print_discrimination(rows: list[dict], label: str) -> None:
    d = discrimination(rows)
    if not d["total"]:
        return
    mark = "✓" if d["usable"] else "✗"
    print(f"  {mark} {label:<10}{d['counts']}")
    print(f"     تمييز {d['entropy_pct']:.0f}٪ · الأغلب «{d['top']}» "
          f"بنسبة {d['top_pct']:.0f}٪")
    if not d["usable"]:
        print(f"     ⇒ حكم شبه ثابت: لا يفصل صفقة عن أخرى مهما كان صائباً.")


def report(linked: list[dict], db) -> None:
    trades = {str(r["id"]): dict(r)
              for r in db.execute("SELECT * FROM dashboard_trade")}
    joined = []
    for r in linked:
        t = trades.get(r["_trade_id"])
        if t:
            joined.append({**t, "agreement": r.get("agreement"),
                           "confidence": r.get("confidence"),
                           "grounding": r.get("grounding_score"),
                           "latency_ms": r.get("latency_ms")})
    closed = [x for x in joined if x["status"] in ("won", "lost")]

    print(f"\n{'═' * 70}")
    print(f"مراجعات مضمومة إلى صفقات: {len(joined)} · منها محسومة {len(closed)}")
    print("═" * 70)
    if not closed:
        print("\n⚠ لا صفقة محسومة بعد. لا حكم ممكن — وهذا ليس فشلاً بل "
              "\n  انتظاراً: المستشار يحتاج نتائج ليُقاس عليها.")
        return

    print(f"\n{'حكم المستشار':<14}{'صفقات':>7}{'نجاح':>9}{'التوقّع':>11}"
          f"{'فاصل الثقة 95%':>18}")
    seen = {}
    for a in AGREEMENTS:
        part = [x for x in closed if x.get("agreement") == a]
        if not part:
            continue
        s = summarize(part)
        seen[a] = s
        flag = "" if s["reliable"] else "  ⚠عيّنة صغيرة"
        print(f"{a:<14}{s['closed']:>7}{s['win_rate']:>8.1f}%"
              f"{s['expectancy']:>+10.2f}R"
              f"{s['win_rate_low']:>12.0f}–{s['win_rate_high']:.0f}%{flag}")

    base = summarize(closed)
    print(f"{'الكل':<14}{base['closed']:>7}{base['win_rate']:>8.1f}%"
          f"{base['expectancy']:>+10.2f}R"
          f"{base['win_rate_low']:>12.0f}–{base['win_rate_high']:.0f}%")

    a, d = seen.get("agree"), seen.get("disagree")
    print()
    if a and d:
        gap = a["expectancy"] - d["expectancy"]
        overlap = not (a["win_rate_low"] > d["win_rate_high"]
                       or d["win_rate_low"] > a["win_rate_high"])
        print(f"  الفرق «موافق − معارض»: {gap:+.2f}R")
        if overlap:
            print("  ✗ فاصلا الثقة متداخلان — الفرق **غير مثبت**.")
            print("    مستشار عشوائي يُنتج فرقاً كهذا في عيّنة بهذا الحجم.")
        else:
            print("  ✓ الفاصلان منفصلان — الفرق حقيقي على هذه العيّنة.")
    else:
        print("  ✗ لا تكفي الشرائح للمقارنة (يلزم «موافق» و«معارض» معاً).")

    lat = [x["latency_ms"] for x in joined if x.get("latency_ms")]
    if lat:
        lat.sort()
        total_min = sum(lat) / 1000 / 60
        print(f"\n  الكلفة الزمنية: وسيط {lat[len(lat) // 2] / 1000:.0f}ث "
              f"للمراجعة · {total_min:.0f} دقيقة إجمالاً")
        if a and d and gap and abs(gap) > 0.01:
            print(f"  ⇒ {total_min / max(1, len(closed)):.1f} دقيقة لكل صفقة "
                  f"محسومة مقابل {gap:+.2f}R من التمييز")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="قياس مساهمة المستشار")
    ap.add_argument("--relink", action="store_true",
                    help="اكتب المعرّفات المصحَّحة إلى ملف الربط")
    ap.add_argument("--source", default="advisor",
                    choices=("advisor", "local", "both"))
    args = ap.parse_args(argv)

    if not DB.exists():
        print("لا قاعدة بيانات.")
        return 1
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    rows: list[dict] = []
    if args.source in ("advisor", "both"):
        rows += read_jsonl(HISTORY)
    if args.source in ("local", "both"):
        rows += read_jsonl(LOCAL)
    if not rows:
        print("لا مراجعات مسجّلة.")
        return 0

    # التمييز أولاً: لا معنى لسؤال «هل حكمه صائب» قبل «هل يحكم أصلاً»
    print("══ قدرة التمييز (لا تحتاج نتائج) ══")
    if args.source in ("advisor", "both"):
        print_discrimination(read_jsonl(HISTORY), "advisor")
    if args.source in ("local", "both"):
        print_discrimination(read_jsonl(LOCAL), "local")
    print()

    linked, stats = relink(rows, db)
    print(f"مراجعات: {stats['total']}")
    print(f"  مربوطة أصلاً بصفقة صحيحة : {stats['already']}")
    print(f"  أُصلح ربطها               : {stats['relinked']}")
    print(f"  بلا صفّ مسح مطابق         : {stats['no_scan_row']}")
    print(f"  صفّ موجود بلا صفقة        : {stats['no_trade']}")

    if args.relink:
        out = ROOT / "data" / "advisor_links.jsonl"
        with out.open("w", encoding="utf-8") as fh:
            for r in linked:
                fh.write(json.dumps(
                    {"review_id": r.get("review_id"),
                     "trade_id": r["_trade_id"],
                     "agreement": r.get("agreement")},
                    ensure_ascii=False) + "\n")
        print(f"\n✓ كُتبت الروابط في {out.name}")

    report(linked, db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
