# -*- coding: utf-8 -*-
"""زمن المسح — ولماذا بدا معلّقاً وهو يعمل.

═══ العطب المقيس ═══

وقف المخرَج عند ``… 150/150`` ثمّ صمت، فبدا معلّقاً. ولم يكن:

    ‏PointInTimeSnapshotService.capture_from_scan_row
        = 60,734 ms **للرمز الواحد**
        = 9,110 ثانية لمئة وخمسين رمزاً  ←  ساعتان ونصف

والمُشرِّح دلّ على المصدر بلا لبس::

    608,371 نداءً لـ json.loads  ·  25.6 ثانية
    ← scanner/knowledge/repository.py::_read_all

‏``_read_all`` تقرأ ملفّ المعرفة كاملاً (٩٣٥٩ سجلّاً) وتحلّل كل سطر
في **كل نداء**. وبحث التشابه ينادِيها خمساً وستّين مرّة للرمز.
فالحصيلة واحدٌ وتسعون مليون تحليل JSON لمسحةٍ واحدة.

═══ العلاجان ═══

  ١. **مذاكرة على حالة الملفّ** (mtime, size) — لا على الزمن، لأن
     الملفّ يُلحَق به أثناء المسح نفسه، ومذاكرةٌ بمهلة كانت ستُرجع
     سجلّات قديمة بعد أوّل كتابة.
     القياس: 60,734 ms  →  ~2,000 ms   (×30)

  ٢. **الإثراء لمن له توصية وحده.** السياق الثقيل يلزم من يُبنى
     عليه قرار، لا كل رمزٍ مُسِح.
     القياس: ~2,000 ms  →  37 ms       (×54 أخرى)

  المحصّلة لمئة وخمسين رمزاً: ساعتان ونصف  →  ستّ ثوانٍ.

═══ ولماذا الصمت نفسه عطب ═══

الصمت لا يفرّق بين «يعمل» و«علّق»، فيقتل المستخدمُ عمليّةً كانت
على وشك الانتهاء — وهذا ما وقع. فالمراحل تُعلن نفسها الآن.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ── ١) المذاكرة تعمل ولا تكذب ──
from scanner.knowledge import repository as repo  # noqa: E402

tmp = Path(tempfile.mkdtemp())
path = tmp / "records.jsonl"
# السجلّات بالمخطّط الحقيقي — لا شكلٍ مخترَع.
#
# النسخة الأولى ولّدت صفوفاً بمفاتيح مختلَقة، فرفضها ``from_dict``
# كلّها وأعادت صفراً. والمذاكرة كانت تعمل، لكنّ الاختبار كان يقيس
# سرعة **لا شيء**: أسرع نظامٍ في العالم هو الذي لا يقرأ شيئاً.
from scanner.knowledge.schemas import SnapshotKind  # noqa: E402

_kind = list(SnapshotKind)[0].value
rows = [{"record_id": f"rec_{i}", "kind": _kind, "event_id": f"evt_{i}",
         "created_at": "2026-01-01T00:00:00+00:00", "payload": {"i": i}}
        for i in range(2000)]
# سطرٌ أخير في نهاية الملفّ — وإلّا التحق أوّل ملحَقٍ بآخر سطر
# فأفسدهما معاً. و``_append`` الحقيقية تنهي كل سطر بفاصلٍ سطريّ،
# فالملفّ الحقيقي سليم؛ الخلل كان في الاختبار وحده.
path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                        for r in rows), encoding="utf-8")

repo.clear_cache()
store = repo.KnowledgeRepository(path=path) if hasattr(
    repo, "KnowledgeRepository") else None
if store is None:
    # اسم الصنف قد يختلف — نأخذ أوّل صنف فيه ``_read_all``
    cand = [v for v in vars(repo).values()
            if isinstance(v, type) and hasattr(v, "_read_all")]
    store = cand[0](path=path) if cand else None

if store is None:
    check("١ وُجد مستودع المعرفة", False, "لا صنف فيه _read_all")
else:
    t = time.perf_counter()
    first = store._read_all()
    cold = (time.perf_counter() - t) * 1000
    t = time.perf_counter()
    second = store._read_all()
    warm = (time.perf_counter() - t) * 1000

    check("١ القراءة الأولى تعطي السجلّات", len(first) == 2000, str(len(first)))
    check("  والثانية تعطي المثل", len(second) == len(first))
    # ×5 حدٌّ متحفّظ: المقيس ×30 على الملفّ الحقيقي
    check(f"  وأسرع بكثير ({cold:.1f}ms → {warm:.1f}ms)",
          warm * 5 < cold or warm < 1.0, f"{cold:.2f} → {warm:.2f}")

    # ═══ والمذاكرة لا تُرجع قديماً ═══
    #
    # الملفّ يُلحَق به أثناء المسح. مذاكرةٌ بمهلة زمنية كانت ستُخفي
    # ما كُتب للتوّ — وهو أسوأ من البطء: جوابٌ سريعٌ خاطئ.
    time.sleep(0.01)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"record_id": "rec_new", "kind": _kind,
                             "event_id": "evt_new",
                             "created_at": "2026-01-01T00:00:00+00:00",
                             "payload": {}}, ensure_ascii=False) + "\n")
    third = store._read_all()
    check("  والإلحاق يُبطلها فوراً", len(third) == 2001, str(len(third)))

    # ولا تتراكم: مدخلٌ واحد لكل ملف
    check("  ولا تتضخّم بالنسخ", len(repo._CACHE) <= 1, str(len(repo._CACHE)))

repo.clear_cache()
shutil.rmtree(tmp, ignore_errors=True)


# ── ٢) الإثراء مشروط بوجود توصية ──
scan_src = (ROOT / "web" / "dashboard" / "management" / "commands"
            / "scan.py").read_text(encoding="utf-8")
code = "\n".join(l for l in scan_src.splitlines()
                 if not l.strip().startswith("#"))

check("٢ الإثراء مشروط", "skip_enrichment=not _actionable(reco)" in code)
check("  ودالّة الحكم معرَّفة", "def _actionable(" in code)

sys.path.insert(0, str(ROOT / "web"))
import ast  # noqa: E402

tree = ast.parse(scan_src)
ns: dict = {}
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name == "_actionable":
        exec(compile(ast.Module([n], []), "<a>", "exec"), ns)
act = ns.get("_actionable")
check("  وتُنفَّذ فعلاً", act is not None)
if act:
    check("  والفارغ ليس قابلاً للتنفيذ", act(None) is False)
    check("  و«لا توصية» كذلك", act({"action": "لا توصية"}) is False)
    check("  و none كذلك", act({"action": "none"}) is False)
    check("  والشرطة كذلك", act({"action": "—"}) is False)
    check("  والتوصية الحقيقية نعم", act({"action": "شراء عند الارتداد"}) is True)
    # كائنٌ له as_dict — الطريق الآخر في المسح
    class _R:
        def as_dict(self):
            return {"action": "شراء"}
    check("  وكائن as_dict يُقرأ", act(_R()) is True)


# ── ٣) المراحل تُعلن نفسها ──
#
# الصمت لا يفرّق بين «يعمل» و«علّق».
check("٣ اكتمال الفحص يُعلَن", "اكتمل الفحص" in scan_src)
check("  ومرحلة الحفظ تُعلَن", "الحفظ (لقطات" in scan_src)
check("  وتقدّمها يُعرَض", "حفظ {_i_row}/{n_rows}" in scan_src)
check("  والزمن يُفصَّل فحصاً وحفظاً",
      "فحص {t_persist - started:.0f}ث" in scan_src)
# «٣.٨ث» كانت تصف الجلب وحده بينما الحفظ دقائق — رقمٌ صادق يضلّل
check("  فلا يصف رقمٌ واحد مرحلتين", "t_persist" in code)


# ── ٤) التوازي: خيارٌ مقيس لا مفترَض ──
#
# ═══ لماذا الافتراضي متسلسل ═══
#
# القياس على آلة التطوير (نواتان)::
#
#     متسلسل     2.44ث  (122 ms/رمز)
#     خيوط ×4    3.15ث   ×0.77   أبطأ
#     عمليّات ×4  5.23ث   ×0.47   أبطأ
#
# ‏pandas يُمسك قفل المفسّر في أجزاء كثيرة، فالخيوط تتنازع عليه.
# و``spawn`` على ويندوز يعيد استيراد pandas و numpy والحزمة كاملةً
# في كل عامل — كلفةٌ ثابتة لا تُقسَّم.
#
# والجلب عكسه: انتظار شبكة خالص، ولذلك يبقى مُخيَّطاً.
check("٤ للتحليل خيار توزيع", '"--analyze"' in scan_src)
check("  وافتراضه متسلسل", 'default="serial"' in scan_src)
check("  وخياراته الثلاثة",
      '("serial", "threads", "processes")' in scan_src)
check("  وعدد العمّال قابل للضبط", '"--jobs"' in scan_src)
check("  ودالّة الدفعة معرَّفة", "def _analyze_batch(" in code)

# ‏spawn صراحةً: ‏fork على لينكس يعطي قياساً متفائلاً لا يُنقَل لويندوز
check("  والعمليّات بـ spawn لا fork",
      'mp.get_context("spawn")' in code and 'get_context("fork")' not in code)
# وفشل التوازي لا يُسقط المسح
check("  وتعذّر العمليّات يسقط إلى الخيوط",
      'mode="threads"' in code and "سقوط إلى الخيوط" in scan_src)

bench = ROOT / "tools_bench_parallel.py"
check("  والمقياس موجود", bench.exists())
_b = bench.read_text(encoding="utf-8")
check("  ويقيس الثلاثة", "ThreadPoolExecutor" in _b
      and "ProcessPoolExecutor" in _b and "متسلسل" in _b)
check("  وبـ spawn كذلك", 'get_context("spawn")' in _b)
# عيّنةٌ صغيرة تُنتج قياساً ضجيجياً — يُرفض لا يُعرَض
check("  ويرفض العيّنة الصغيرة", "القياس عليها ضجيج" in _b)
# ربحٌ دون ٣٠٪ قد يكون ضجيج تشغيلٍ واحد
# ═══ الحكم يحتاج هامشاً ═══
#
# قياس المستخدم قال «الأسرع: عمليّات ×4 — ×1.04» فأوصت الأداة به.
# و×1.04 ضجيج لا ربح: من يقرأ التوصية يبدّل إعداده ويدفع تعقيداً
# مقابل لا شيء. والعيب في الأداة لا في القارئ.
_b_code = "\n".join(l for l in _b.splitlines()
                    if not l.strip().startswith("#"))
check("  ولا يوصي دون هامش", "MIN_GAIN" in _b_code)
check("  والهامش معقول (١.١–٢.٠)",
      any(f"MIN_GAIN = {v}" in _b_code
          for v in ("1.1", "1.15", "1.2", "1.25", "1.3", "1.5", "2.0")),
      "غير معرَّف أو خارج المدى")
check("  ودونه يُعلَن المتسلسل فائزاً",
      'best_name = "متسلسل"' in _b_code and "if gain < MIN_GAIN" in _b_code)

# تشغيلةٌ واحدة تقيس الضجيج مع العمل
check("  ويُعاد القياس", "REPEAT" in _b_code and "def timeit(" in _b_code)
check("  ويُؤخذ أسرعه لا متوسّطه", "min(best," in _b_code)

# عيّنةٌ صغيرة لا تُطفئ كلفة spawn فتُظلم التوازي
check("  والعيّنة الافتراضية تشبه العمل الحقيقي",
      "default=60" in _b_code or "default=100" in _b_code)
# والرقم الذي يهمّ: زمن السوق كاملاً لا زمن العيّنة
check("  ويُسقِط على السوق كاملاً", "FULL_MARKET" in _b_code)


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
