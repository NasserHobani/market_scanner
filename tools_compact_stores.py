# -*- coding: utf-8 -*-
"""تقليم المخازن الإلحاقية — أرشفةٌ لا حذف، والقرار لك.

    python tools_compact_stores.py              # تقرير فقط
    python tools_compact_stores.py --apply      # يؤرشف ويقلّم

═══ لماذا ═══

قاتل الذاكرة زار مرّتين (``oom_kill 2``)، والذروة ٣٫٢٢ غ.ب على جهازٍ
متاحه ٢٫٤٦. والملفّات:

    v3_snapshots.jsonl   691 م.ب
    records.jsonl        429 م.ب   ← يُحمَّل كاملاً داخل المسح
    events.jsonl          80 م.ب

مخازن **إلحاقية**: كل مسحٍ يضيف إليها ولا شيء يُنقص منها أبداً.
فما كان يمرّ قبل شهرٍ يتجاوز الذاكرة اليوم، ويتجاوزها أكثر غداً.
وليس في الكود ما يوقف هذا — وهو العطب الجذريّ، لا حجمٌ بعينه.

═══ ما يُحفَظ في قاعدة المعرفة ═══

بحث التشابه يسأل: «ماذا حدث في مواقف تشبه هذا؟». والجواب يحتاج
**نتيجة** — موقفٌ بلا نتيجة لا يقول شيئاً عن المستقبل.

    يبقى دائماً   كل نتيجة وصفقة وتجربة ونموذج
                  وكل سجلٍّ لحدثٍ **له نتيجة** — التاريخ الموسوم
    يبقى مؤقّتاً  ما عمره دون ‎--days‎ (افتراضاً ٣٠) — قد تأتيه نتيجة
    يُؤرشَف       لقطاتٌ قديمة لم تُحسم ولن تُحسم

والأرشيف ‎gzip‎ في ``data/archive/`` — يُستعاد بفكّه وإلحاقه.

═══ وما لا يُلمس ═══

``v3_snapshots.jsonl`` هو **بيانات تدريب** LightGBM. وتقليمه يغيّر
ما يتعلّمه النموذج بصمت. فيُعرض حجمه ولا يُقلَّم هنا — ذلك قرارٌ
في مجموعة التدريب لا في التخزين.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATA = ROOT / "data"
ARCHIVE = DATA / "archive"

KNOWLEDGE = DATA / "knowledge" / "records.jsonl"
#: سجلّات أحداثٍ للمراقبة — يكفي آخرها
LOGS = [DATA / "feature_snapshots" / "events.jsonl",
        DATA / "market_sync" / "events.jsonl"]
#: ما يُعرَض ولا يُقلَّم
REPORT_ONLY = [DATA / "feature_snapshots" / "v3_snapshots.jsonl",
               DATA / "features" / "snapshots.jsonl"]

KEEP_KINDS = {"outcome", "trade", "experiment", "model"}


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _mb(n: float) -> str:
    return f"{n / 1e6:,.1f} م.ب"


def _when(row: dict) -> datetime | None:
    s = str(row.get("created_at") or "")
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _lines(path: Path, limit: int):
    """سطراً سطراً بايتاتٍ حتى ``limit`` — لا الملفّ كاملاً في الذاكرة.

    والحدّ هو الحجم لحظة البدء: ما أُلحق بعدها يُنسخ كما هو في
    ``_swap``، فقراءته هنا أيضاً تجعله يظهر مرّتين.
    """
    read = 0
    with path.open("rb") as fh:
        for raw in fh:
            if read + len(raw) > limit or not raw.endswith(b"\n"):
                break
            read += len(raw)
            yield raw


def _swap(path: Path, kept_tmp: Path, start_size: int) -> None:
    """يستبدل الملفّ بالمقلَّم — وما أُلحق أثناء التقليم لا يضيع.

    المسح قد يُلحق بالملفّ ونحن نقرؤه. فما زاد بعد ``start_size``
    يُنسخ إلى آخر الجديد قبل الاستبدال. ويبقى شبّاكٌ ضيّق بين النسخ
    والاستبدال — لذلك يُفضَّل التشغيل والمسح متوقّف.
    """
    with path.open("rb") as src, kept_tmp.open("ab") as dst:
        src.seek(start_size)
        shutil.copyfileobj(src, dst)
    os.replace(kept_tmp, path)


def compact_knowledge(days: int, apply: bool) -> None:
    print(f"═══ قاعدة المعرفة · {_rel(KNOWLEDGE)} ═══")
    if not KNOWLEDGE.exists():
        print("  غير موجودة")
        return
    size = KNOWLEDGE.stat().st_size
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # ── المرور الأوّل: أيّ الأحداث لها نتيجة ──
    labelled: set[str] = set()
    kinds: Counter[str] = Counter()
    total = 0
    for raw in _lines(KNOWLEDGE, size):
        total += 1
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        k = str(row.get("kind") or "")
        kinds[k] += 1
        if k == "outcome":
            labelled.add(str(row.get("event_id") or ""))

    # ── المرور الثاني: القرار لكل سطر ──
    keep_n = arch_n = keep_b = arch_b = 0
    why: Counter[str] = Counter()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tmp = KNOWLEDGE.with_suffix(".jsonl.compact")
    out = tmp.open("wb") if apply else None
    arc = None
    if apply:
        (ARCHIVE / "knowledge").mkdir(parents=True, exist_ok=True)
        arc = gzip.open(ARCHIVE / "knowledge" / f"records.{stamp}.jsonl.gz",
                        "wb")
    try:
        for raw in _lines(KNOWLEDGE, size):
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            k = str(row.get("kind") or "")
            ev = str(row.get("event_id") or "")
            w = _when(row)
            if k in KEEP_KINDS:
                reason = "نوعٌ يُحفظ دائماً"
            elif ev in labelled:
                reason = "حدثٌ له نتيجة"
            elif w is None or w >= cutoff:
                reason = f"أحدث من {days} يوماً"
            else:
                reason = ""
            if reason:
                keep_n += 1
                keep_b += len(raw)
                why[reason] += 1
                if out:
                    out.write(raw)
            else:
                arch_n += 1
                arch_b += len(raw)
                if arc:
                    arc.write(raw)
    finally:
        if out:
            out.close()
        if arc:
            arc.close()

    print(f"  الحجم {_mb(size)} · {total:,} سجلّاً · "
          f"{len(labelled):,} حدثاً له نتيجة")
    print("  الأنواع: " + " · ".join(f"{k} {n:,}"
                                      for k, n in kinds.most_common()))
    print(f"  يبقى     {keep_n:>9,}  {_mb(keep_b):>10}")
    for r, n in why.most_common():
        print(f"    {r:20s} {n:,}")
    print(f"  يُؤرشَف  {arch_n:>9,}  {_mb(arch_b):>10}")
    if apply:
        _swap(KNOWLEDGE, tmp, size)
        print(f"  ✓ قُلِّم — الأرشيف في data/archive/knowledge/")


def trim_logs(keep_mb: float, apply: bool) -> None:
    print(f"\n═══ سجلّات المراقبة — يبقى آخر {keep_mb:g} م.ب ═══")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for p in LOGS:
        if not p.exists():
            continue
        size = p.stat().st_size
        keep = int(keep_mb * 1e6)
        if size <= keep:
            print(f"  {_rel(p)}: {_mb(size)} — لا حاجة")
            continue
        print(f"  {_rel(p)}: {_mb(size)} ← {_mb(keep)}")
        if not apply:
            continue
        cut = size - keep
        tmp = p.with_suffix(".jsonl.compact")
        (ARCHIVE / "logs").mkdir(parents=True, exist_ok=True)
        with p.open("rb") as src:
            with gzip.open(ARCHIVE / "logs" / f"{p.parent.name}-{p.stem}."
                           f"{stamp}.jsonl.gz", "wb") as arc:
                left = cut
                while left > 0:
                    buf = src.read(min(1 << 20, left))
                    if not buf:
                        break
                    arc.write(buf)
                    left -= len(buf)
                # بقيّة السطر المقطوع تذهب للأرشيف أيضاً: لا نصف سطر
                arc.write(src.readline())
            with tmp.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        _swap(p, tmp, size)
        print("    ✓ قُلِّم")


def report_only() -> None:
    print("\n═══ لا يُلمس هنا ═══")
    for p in REPORT_ONLY:
        if p.exists():
            print(f"  {_rel(p)}: {_mb(p.stat().st_size)}")
    print("  بيانات تدريبٍ وتقارير — تقليمها يغيّر ما يتعلّمه النموذج.")
    print("  ولا يقرؤها المسح كاملةً (يقرأ اللقطة بإزاحتها في الفهرس).")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--log-mb", type=float, default=10.0)
    a = ap.parse_args()
    print(__doc__.strip().splitlines()[0])
    print("الوضع:", "تنفيذ" if a.apply else "تقرير فقط (أضف --apply)")
    print()
    compact_knowledge(a.days, a.apply)
    trim_logs(a.log_mb, a.apply)
    report_only()
    if a.apply:
        print("\n⚠ إن كان المسح يعمل الآن فأعد تشغيل الحاويتين بعدها:")
        print("  الذاكرة المؤقّتة في العمليات الجارية ما زالت تحمل القديم.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
