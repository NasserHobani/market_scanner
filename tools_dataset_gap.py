# -*- coding: utf-8 -*-
"""لماذا لا يتدرّب LightGBM — بالأرقام لا بالظنّ.

    python tools_dataset_gap.py

يقيس الفجوة بين ما لدينا وما يلزم، ويعزو كل صفٍّ مرفوض إلى سببه.
والفرق بين «الالتقاط فشل» و«لا سابقة بعد» هو الفرق بين عطبٍ
يُصلَح وحقيقةٍ تُنتظر.
"""
from __future__ import annotations

import collections
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))


def trades_from_db(db: Path) -> list[dict]:
    """يقرأ من **نسخة** لا من القاعدة الحيّة.

    الخادم يكتب في القاعدة نفسها، وقراءةُ ملفّ ‏SQLite أثناء
    الكتابة تُخرج ``disk I/O error`` — وقع فعلاً هنا. والنسخة
    تكلّف أجزاء من الثانية وتُبعد الأداة عن طريق الخادم تماماً.
    """
    import shutil
    import tempfile

    tmp = Path(tempfile.gettempdir()) / "gap_snapshot.sqlite3"
    shutil.copyfile(db, tmp)
    con = sqlite3.connect(str(tmp))
    con.row_factory = sqlite3.Row
    cols = ("id,symbol,market,timeframe,side,status,r_multiple,entry,stop,"
            "target1,grade,score,signal_at,closed_at,candle_time,"
            "feature_snapshot_id,pit_snapshot_id")
    rows = []
    for r in con.execute(f"SELECT {cols} FROM dashboard_trade "
                         "WHERE status IN ('won','lost')"):
        d = dict(r)
        d["trade_id"] = d.pop("id")
        rows.append(d)
    return rows


def main() -> int:
    from scanner.feature_snapshots import tiers
    from scanner.feature_snapshots.config import DEFAULT_RUNTIME_CONFIG as CFG
    from scanner.feature_snapshots.store import iter_snapshots

    db = ROOT / "data" / "dashboard.sqlite3"
    if not db.exists():
        print("لا قاعدة بيانات")
        return 1
    trades = trades_from_db(db)
    snaps = list(iter_snapshots())
    need = int(CFG.v3_train_min_rows)

    print(f"صفقات محسومة: {len(trades)}")
    print(f"لقطات مخزّنة:  {len(snaps)}")
    print(f"المطلوب للتدريب: {need} صفّاً\n")

    # ── الربط ──
    linked = [t for t in trades
              if t.get("pit_snapshot_id") or t.get("feature_snapshot_id")]
    print(f"مربوطة بلقطة: {len(linked)} من {len(trades)}"
          f" = {100 * len(linked) / max(1, len(trades)):.0f}٪")
    if len(linked) < len(trades):
        print(f"  ← {len(trades) - len(linked)} صفقة لا تعرف من أيّ ميزات"
              " وُلدت. غير قابلة للاسترداد.")

    # ── التغطية بالقاعدتين ──
    by_id = {s.snapshot_id: s for s in snaps}
    old_ok = new_ok = 0
    gaps = collections.Counter()
    core_miss = collections.Counter()
    for t in linked:
        s = by_id.get(t.get("pit_snapshot_id") or "")
        if s is None:
            continue
        f = (s.to_dict().get("features") or {})
        if float(getattr(s, "coverage", 0) or 0) >= 0.70:
            old_ok += 1
        if tiers.core_coverage(f) >= tiers.CORE_MIN_COVERAGE:
            new_ok += 1
        else:
            for m in tiers.missing_core(f):
                core_miss[m] += 1
        for _, why in tiers.optional_gaps(f).items():
            gaps[why] += 1

    print(f"\n{'':─<46}")
    print(f"مؤهّلة بالقاعدة القديمة (تغطية كلّية ≥0.70):  {old_ok}")
    print(f"مؤهّلة بالقاعدة الجديدة (أساسية ≥0.90):      {new_ok}")
    print(f"{'':─<46}")
    print(f"الفارق: {new_ok - old_ok:+d} صفّاً")
    left = need - new_ok
    print(f"\nالمتبقّي للحدّ: {max(0, left)} صفّاً"
          if left > 0 else "\n✓ الحدّ مُتجاوَز — التدريب ممكن")

    if core_miss:
        print("\nأعطاب التقاطٍ حقيقية (ميزات أساسية غائبة):")
        for k, v in core_miss.most_common(8):
            print(f"  {k:<28} {v}")
    if gaps:
        print("\nغيابٌ مشروع (لا يُحاسَب):")
        for k, v in gaps.most_common(8):
            print(f"  {k:<28} {v}")

    # ── وتيرة النموّ ──
    days = len({str(t.get("closed_at") or "")[:10] for t in trades
                if t.get("closed_at")})
    if days and left > 0:
        recent = [t for t in linked if t.get("pit_snapshot_id")]
        rate = len(recent) / max(1, days)
        print(f"\nوتيرة الصفقات المربوطة: {rate:.1f}/يوم"
              f" → نحو {int(left / max(0.1, rate))} يوماً للحدّ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
