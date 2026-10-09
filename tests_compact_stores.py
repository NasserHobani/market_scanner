# -*- coding: utf-8 -*-
"""التقليم يؤرشف ولا يحذف — ولا يمسّ التاريخ الموسوم.

قاتل الذاكرة زار مرّتين، وقاعدة المعرفة ‏429 م.ب تُحمَّل كاملةً داخل
المسح. والتقليم يكتب على بياناتٍ لا تُستعاد إن أخطأ — فهذه الفواحص
**تشغّله** على ملفّاتٍ مؤقّتة وتعدّ ما بقي وما أُرشف سطراً سطراً.
"""
from __future__ import annotations

import gzip
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import tools_compact_stores as T  # noqa: E402
from tests_helpers import Checks  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])
now = datetime.now(timezone.utc)


def row(rid, kind, ev, days_ago):
    return {"record_id": rid, "kind": kind, "event_id": ev,
            "created_at": (now - timedelta(days=days_ago)).isoformat(),
            "payload": {}}


rows = [
    row("old_feat_labelled", "feature", "E1", 200),   # له نتيجة ← يبقى
    row("outcome_E1", "outcome", "E1", 150),          # نتيجة ← يبقى
    row("old_feat_orphan", "feature", "E2", 200),     # بلا نتيجة، قديم ← أرشيف
    row("old_market_orphan", "market", "E2", 90),     # بلا نتيجة، قديم ← أرشيف
    row("new_feat", "feature", "E3", 2),              # حديث ← يبقى
    row("old_trade", "trade", "E4", 400),             # نوعٌ دائم ← يبقى
]

with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    T.DATA = d
    T.ARCHIVE = d / "archive"
    T.KNOWLEDGE = d / "knowledge" / "records.jsonl"
    T.KNOWLEDGE.parent.mkdir(parents=True)
    T.KNOWLEDGE.write_text("".join(json.dumps(r) + "\n" for r in rows),
                           encoding="utf-8")
    before = T.KNOWLEDGE.read_bytes()

    # ── التقرير لا يكتب ──
    T.compact_knowledge(30, apply=False)
    c("١ التقرير لا يلمس الملفّ", T.KNOWLEDGE.read_bytes() == before)
    c("  ولا يُنشئ أرشيفاً", not T.ARCHIVE.exists())

    # ── التنفيذ ──
    T.compact_knowledge(30, apply=True)
    kept = [json.loads(l)["record_id"]
            for l in T.KNOWLEDGE.read_text(encoding="utf-8").splitlines()]
    c("٢ التاريخ الموسوم يبقى", "old_feat_labelled" in kept
      and "outcome_E1" in kept, str(kept))
    c("  والحديث يبقى", "new_feat" in kept)
    c("  والنوع الدائم يبقى", "old_trade" in kept)
    c("  والقديم بلا نتيجة يخرج", "old_feat_orphan" not in kept
      and "old_market_orphan" not in kept, str(kept))

    arcs = list((T.ARCHIVE / "knowledge").glob("*.jsonl.gz"))
    c("٣ أرشيفٌ واحد", len(arcs) == 1, str(arcs))
    archived = [json.loads(l)["record_id"] for l in
                gzip.open(arcs[0], "rt", encoding="utf-8").read().splitlines()]
    c("  فيه ما خرج بالضبط",
      sorted(archived) == ["old_feat_orphan", "old_market_orphan"],
      str(archived))
    c("  ولا سطر ضاع ولا تكرّر",
      sorted(kept + archived) == sorted(r["record_id"] for r in rows))

    # ── ما أُلحق أثناء التقليم لا يضيع ولا يتكرّر ──
    #
    # يُحاكى بإلحاقٍ بعد لحظة البدء: ``_lines`` تقف عند الحجم الأوّل،
    # و``_swap`` تنسخ الزائد.
    T.KNOWLEDGE.write_text("".join(json.dumps(r) + "\n" for r in rows),
                           encoding="utf-8")
    size0 = T.KNOWLEDGE.stat().st_size
    late = json.dumps(row("late", "feature", "E9", 0)) + "\n"
    with T.KNOWLEDGE.open("a", encoding="utf-8") as fh:
        fh.write(late)
    got = list(T._lines(T.KNOWLEDGE, size0))
    c("٤ القراءة تقف عند حجم البدء", len(got) == len(rows), str(len(got)))
    tmp_out = T.KNOWLEDGE.with_suffix(".jsonl.compact")
    tmp_out.write_bytes(b"".join(got))
    T._swap(T.KNOWLEDGE, tmp_out, size0)
    ids = [json.loads(l)["record_id"]
           for l in T.KNOWLEDGE.read_text(encoding="utf-8").splitlines()]
    c("  والمُلحَق يُنقل", "late" in ids)
    c("  مرّةً واحدة", ids.count("late") == 1)

    # ── السجلّات: يبقى الذيل، ولا نصف سطر ──
    log = d / "feature_snapshots" / "events.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text("".join(json.dumps({"i": i, "pad": "x" * 80}) + "\n"
                           for i in range(2000)), encoding="utf-8")
    T.LOGS = [log]
    T.trim_logs(0.02, apply=True)                 # ~20 ك.ب
    lines = log.read_text(encoding="utf-8").splitlines()
    ok = all(json.loads(l) for l in lines)
    c("٥ السجلّ قُصّ", log.stat().st_size < 30_000, str(log.stat().st_size))
    c("  وكل سطرٍ باقٍ سليم", ok)
    c("  والباقي هو الأحدث", json.loads(lines[-1])["i"] == 1999)
    alog = list((T.ARCHIVE / "logs").glob("*.gz"))
    total = len(lines) + len(gzip.open(alog[0], "rt").read().splitlines())
    c("  ولا سطر ضاع", total == 2000, str(total))

# ── وبيانات التدريب لا تُلمس ──
src = (ROOT / "tools_compact_stores.py").read_text(encoding="utf-8")
c("٦ v3_snapshots في التقرير وحده",
  "v3_snapshots.jsonl" in src.split("REPORT_ONLY = [")[1].split("]")[0])

sys.exit(c.report())
