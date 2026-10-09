# -*- coding: utf-8 -*-
"""قاعدة المعرفة تُقرأ ذيلاً لا كاملاً — والمسح لم يعد يُقتل.

═══ ما وقع ═══

    ✓ اكتمل الفحص: 231 رمزاً في 46ث
    … الحفظ (لقطات + نتائج + مراقبات) — قد يطول
    Killed

في مرحلة الحفظ يُلحِق المسح بـ``records.jsonl`` ثمّ يقرؤه بحث
التشابه فوراً. والإلحاق يُبطل المذاكرة، فيُعاد تحليل الملفّ كاملاً
— لكل صفّ — بنصّه وأسطره وكائناته معاً. عملٌ تربيعيّ وذروة ذاكرة
تتضاعف مع نموّ الملفّ، حتى تقتل النواةُ العملية.

وهذه الفواحص **تُشغّل** المستودع لا تقرأ مصدره.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner.knowledge import repository as R  # noqa: E402
from scanner.knowledge.schemas import KnowledgeRecord  # noqa: E402
from tests_helpers import Checks  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])


def _rec(i: int) -> dict:
    return {"record_id": f"r{i}", "kind": "market", "event_id": f"e{i % 3}",
            "payload": {"symbol": f"S{i}"},
            "created_at": f"2026-10-{1 + i % 9:02d}T00:00:00+00:00"}


with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "records.jsonl"
    R.clear_cache()
    repo = R.KnowledgeRepository(p)
    for i in range(5):
        repo._append(_rec(i))

    a = repo._read_all()
    c("١ القراءة الأولى كاملة", len(a) == 5, str(len(a)))

    # ═══ الإلحاق يُقرأ ذيلاً ═══
    #
    # نُحصي التحليلات: إن أُعيد الملفّ كاملاً لظهرت السجلّات الخمسة
    # القديمة في العدّ مرّةً ثانية.
    parsed = {"n": 0}
    real = KnowledgeRecord.from_dict

    def counting(d):
        parsed["n"] += 1
        return real(d)

    KnowledgeRecord.from_dict = staticmethod(counting)
    try:
        repo._append(_rec(5))
        repo._append(_rec(6))
        b = repo._read_all()
    finally:
        KnowledgeRecord.from_dict = staticmethod(real)
    c("٢ الإلحاق يُضاف", len(b) == 7, str(len(b)))
    c("  ويُحلَّل الجديد وحده", parsed["n"] == 2,
      f"حُلّل {parsed['n']} سطراً بدل ٢")
    c("  والقائمة القديمة لم تتغيّر تحت حاملها", len(a) == 5)

    # بلا تغيير: لا تحليل البتّة
    parsed["n"] = 0
    KnowledgeRecord.from_dict = staticmethod(counting)
    try:
        b2 = repo._read_all()
    finally:
        KnowledgeRecord.from_dict = staticmethod(real)
    c("٣ بلا تغيير لا تحليل", parsed["n"] == 0 and b2 is b)

    # ═══ السطر الناقص لا يُتلف ولا يُعدّ مرّتين ═══
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(7))[:20])          # نصف كتابة
    d = repo._read_all()
    c("٤ نصف السطر يُترك", len(d) == 7, str(len(d)))
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(_rec(7))[20:] + "\n")    # اكتملت
    e = repo._read_all()
    c("  ويُقرأ حين يكتمل", len(e) == 8, str(len(e)))
    c("  مرّةً واحدة", sum(1 for r in e if r.record_id == "r7") == 1)

    # ═══ الملفّ إن صغُر يُعاد كاملاً ═══
    p.write_text(json.dumps(_rec(0)) + "\n", encoding="utf-8")
    f = repo._read_all()
    c("٥ القصّ يُعيد القراءة كاملة", len(f) == 1, str(len(f)))

    # ═══ البحث لا يرتّب المذاكرة في مكانها ═══
    for i in range(1, 6):
        repo._append(_rec(i))
    before = [r.record_id for r in repo._read_all()]
    repo.search(limit=3)
    after = [r.record_id for r in repo._read_all()]
    c("٦ البحث لا يغيّر ترتيب المذاكرة", before == after,
      f"{before} ← {after}")

# ═══════════ ٦ب) فهرس الأحداث ═══════════
#
# ``history`` كانت تمشي على كل السجلّات لكل مرشّح تشابه — حتى خمسة
# آلاف مرّة في النداء الواحد، على ملفٍّ بـ429 م.ب.
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp) / "records.jsonl"
    R.clear_cache()
    repo = R.KnowledgeRepository(p)
    for i in range(9):
        repo._append(_rec(i))                     # e0 · e1 · e2
    h = repo.history("e1")
    c("٦ب الفهرس يجد الحدث", [r.record_id for r in h] ==
      sorted([r.record_id for r in h], key=lambda x: x) and len(h) == 3,
      str([r.record_id for r in h]))
    repo._append(_rec(10))                        # e1 جديد
    c("  ويتّسع بالإلحاق", len(repo.history("e1")) == 4)
    c("  والحدث الغائب فارغ", repo.history("zz") == [])
    c("  والبحث بالحدث يستعمله",
      len(repo.search(event_id="e1", limit=99)) == 4)
    p.write_text(json.dumps(_rec(1)) + "\n", encoding="utf-8")
    c("  والقصّ يُعيد بناءه", len(repo.history("e1")) == 1)


# ═══════════ ٧) واللقطة خارج معاملة الحفظ ═══════════
#
# كانت داخل ``transaction.atomic()``، فموتُ العملية أثناءها تراجع
# بالمسح كلّه: لا صفّ يُحفظ، والشاشة على مسحٍ قديم.
from tests_helpers import code_of  # noqa: E402

sc = code_of(ROOT / "web" / "dashboard" / "management" / "commands"
             / "scan.py")
atomic = sc.split("with transaction.atomic():")[1].split(
    "self._capture_pits(")[0]
c("٧ لا التقاط داخل المعاملة", "capture_from_scan_row" not in atomic)
c("  بل يُؤجَّل", "pit_jobs.append(" in atomic)
c("  ويجري بعدها", "self._capture_pits(pit_jobs" in sc)
cp = sc.split("def _capture_pits")[1].split("def _one_pass")[0]
c("  وخدمةٌ واحدة لا لكل صفّ",
  cp.index("PointInTimeSnapshotService()") < cp.index("for sym, row"))
c("  ويُربط بالنتيجة", "ScanResult.objects.filter(**key).update(" in cp)
c("  وبالصفقة بلا استبدال", 'pit_snapshot_id="").update(' in cp)
c("  وفشلُ صفٍّ لا يوقف غيره", "except Exception" in cp)

sys.exit(c.report())
