# -*- coding: utf-8 -*-
"""ذاكرة كون الرموز — والفحصُ الذي كان يسبّب العطب الذي يفحصه.

═══ العطب ═══

قال القِمع::

    ✗ تعثّر الاكتشاف: Alpaca 429: too many requests
        النزول إلى الملف: 10 رمزاً

و‏429 لا يعني مفتاحاً خاطئاً ولا شبكةً مقطوعة — يعني أنّ النظام
أرهق المزوّد بنفسه.

وكان في المحوّل ``_universe_cache`` بمهلة ساعة، لكنّه **متغيّر
صنف في الرام**. وكل أمر سطر أوامر عمليّةٌ جديدة، فيبدأ بارداً
دائماً ويعيد الحساب كاملاً: اثنا عشر ألفاً وخمسمئة أصل، لكلٍّ
شموع عشرين يوماً.

فذاكرةٌ لا تتجاوز عمر العمليّة ليست ذاكرة — هي تعليقٌ يقول
«محفوظ» ولا يحفظ.

والأسوأ: ``tools_check_universe`` نجحت وأعادت 400 رمزاً، ثمّ فشل
المسح الذي تلاها بـ 429. أي أنّ **الفحص كان يسبّب العطب الذي
يفحصه** — وهذا يجعل التشخيص نفسه مضلّلاً: تفحص فينجح، ثمّ تشغّل
فيفشل، فتظنّ العطب متقطّعاً.

═══ والسلّم الخاطئ ═══

وحين يفشل الاكتشاف كان النزول إلى عشرة رموز في الملف — بينما على
القرص كونٌ كامل اكتُشف قبل ساعات. السلّم الصحيح ثلاث درجات:
حيّ → محفوظ → قائمة الملف.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from scanner import storage  # noqa: E402
from scanner import universe_cache as U  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


BIG = [f"S{i:04d}" for i in range(400)]
VOL = {s: float(1e9 - i) for i, s in enumerate(BIG)}

tmp = Path(tempfile.mkdtemp())
with mock.patch.object(storage, "DATA_DIR", tmp):

    # ── ١) الحفظ والقراءة يعبران حدّ العمليّة ──
    check("١ الحفظ ينجح", U.save("t", BIG, VOL))
    got = U.load("t")
    check("  والقراءة تعيد العدد نفسه",
          got is not None and len(got["symbols"]) == 400)
    check("  والترتيب محفوظ", got["symbols"] == BIG)
    check("  والأحجام معه", got["volumes"]["S0000"] == VOL["S0000"])
    check("  والعمر محسوب", got["age_seconds"] < 5)
    check("  والملف على القرص فعلاً", U.path_for("t").exists())

    # ── ٢) الطزاجة تُحترم، والقديم يبقى متاحاً عند الطلب ──
    check("٢ الطازج يُقبل", U.fresh_symbols("t", ttl=3600) is not None)
    check("  والمنتهي يُرفض في وضع الطزاجة",
          U.fresh_symbols("t", ttl=0.0) is None)
    # وهذا هو بيت القصيد: عند الفشل نريد القديم لا الرفض
    check("  لكنّه يبقى متاحاً بلا حدّ عمر",
          U.load("t", max_age=None) is not None)

    check("  والاسم غير الموجود يعيد None", U.load("لا_يوجد") is None)
    check("  والحفظ الفارغ يُرفض", U.save("t2", []) is False)

    # ── ٣) الملف التالف لا يُسقط النظام ──
    p = U.path_for("bad")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ليس JSON", encoding="utf-8")
    check("٣ الملف التالف يعيد None بلا استثناء", U.load("bad") is None)
    p.write_text('{"saved_at": 1, "symbols": []}', encoding="utf-8")
    check("  والمحفوظ الفارغ كذلك", U.load("bad") is None)

    # ── ٤) السلّم الثلاثي في المحوّل ──
    from scanner.adapters.alpaca import AlpacaAdapter  # noqa: E402

    calls: list[int] = []

    def _mk(compute):
        AlpacaAdapter._universe_cache = None
        a = AlpacaAdapter.__new__(AlpacaAdapter)
        a.last_volumes = {}
        a.last_universe_note = ""
        a.name = "alpaca"
        a._compute_universe = compute
        return a

    def _ok(diagnose=False):
        calls.append(1)
        return BIG, VOL

    n1 = len(_mk(_ok).usdt_universe(0, top_n=None))
    check("٤ أوّل نداء يحسب ويعيد الكون", n1 == 400 and len(calls) == 1,
          f"{n1} · حسابات={len(calls)}")

    # عمليّة جديدة = رام باردة. القرص هو ما يجب أن ينقذها.
    a2 = _mk(_ok)
    n2 = len(a2.usdt_universe(0, top_n=None))
    check("  وعمليّة جديدة لا تعيد الحساب الثقيل",
          n2 == 400 and len(calls) == 1, f"{n2} · حسابات={len(calls)}")
    check("  وتقول إنّها من المحفوظ",
          "المحفوظ" in a2.last_universe_note, a2.last_universe_note[:60])

    # ٤٢٩ مع كون محفوظ — لا نزول إلى العشرة
    def _429(diagnose=False):
        raise RuntimeError('Alpaca 429: {"message": "too many requests."}')

    _saved_ttl = U.DEFAULT_TTL
    U.DEFAULT_TTL = 0.0                     # نُجبر انتهاء الطزاجة
    a3 = _mk(_429)
    n3 = len(a3.usdt_universe(0, top_n=None))
    check("  و429 يُخدَم من الكون المحفوظ", n3 == 400, str(n3))
    check("  والسبب مذكور لا مبتلَع",
          "429" in a3.last_universe_note, a3.last_universe_note[:70])

    # وبلا كون محفوظ يجب أن **يرمي** لا أن يصمت: الصمت هنا يعني
    # مسحاً على لا شيء بلا سبب معلن.
    try:
        U.path_for("alpaca").unlink(missing_ok=True)
        _mk(_429).usdt_universe(0, top_n=None)
        raised = False
    except Exception:  # noqa: BLE001
        raised = True
    check("  وبلا محفوظ يرمي ليعالجه المسح", raised)
    U.DEFAULT_TTL = _saved_ttl

    # ── ٥) الوصف للعرض بلا كشف ──
    U.save("t", BIG, VOL)
    d = U.describe("t")
    check("٥ الوصف يذكر العدد", "400" in d, d)
    check("  والعمر", "دقيقة" in d or "ساعة" in d, d)
    check("  ولا شيء لغير الموجود", U.describe("لا_يوجد") == "لا كون محفوظ")

    # ── ٦) المسح يفضّل المحفوظ على قائمة الملف ──
    #
    # نصّاً لا سلوكاً: تشغيل أمر Django هنا يحتاج قاعدة وبيئة كاملة،
    # والمقصود أنّ الترتيب مكتوب في الرمز لا أنّه يعمل مرّة.
    scan_src = (ROOT / "web" / "dashboard" / "management" / "commands"
                / "scan.py").read_text(encoding="utf-8")
    code = "\n".join(ln for ln in scan_src.splitlines()
                     if not ln.strip().startswith("#"))
    check("٦ المسح يقرأ الكون المحفوظ", "universe_cache" in code)
    check("  ويسجّله مصدراً مستقلاً", '"cached"' in code)
    check("  ولا يفضّله على قائمة أكبر",
          "len(saved[\"symbols\"]) > len(cfg.symbols or [])" in code)

    views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
    check("  واللوحة تُعلن أنّ الاكتشاف الحيّ معطّل",
          '"cached"' in views)

shutil.rmtree(tmp, ignore_errors=True)


# ── ٧) لا اختبار يكتب في بيانات التشغيل ──
#
# ═══ لماذا فحصٌ بنيويّ لا تنظيف ═══
#
# لمّا صار ``usdt_universe`` يحفظ على القرص، كتب ``tests_alpaca``
# كوناً من رمزين — ``['AAPL','SPY']`` — في ``data/universe/`` الحقيقي.
# ولو شُغّل المسح بعده لقرأه، فمسح رمزين وظنّ أنّه اكتشف السوق.
#
# وهذا أخطر من فشل اختبار: **الاختبار يصنع العطب في الإنتاج**، ولا
# يظهر إلّا كنقصٍ صامت في النتائج بعد ساعات.
#
# والتنظيف بعد كل اختبار علاجٌ يعتمد على التذكّر — وقد نُسي مرّتين
# في هذه الجلسة وحدها. فالحارس أن يُفحص **الرمز**: كل ملفّ يستدعي
# ``usdt_universe`` يجب أن يزيح ``storage.DATA_DIR`` أوّلاً.
_writers = []
for _p in sorted(ROOT.glob("tests_*.py")):
    _src = _p.read_text(encoding="utf-8", errors="replace")
    if "usdt_universe(" not in _src:
        continue
    isolated = ("DATA_DIR = _TMP_DATA" in _src
                or "patch.object(storage" in _src
                or "patch.object(_storage" in _src
                or "storage.DATA_DIR =" in _src)
    if not isolated:
        _writers.append(_p.name)
check("٧ كل من ينادي usdt_universe يعزل قرصه",
      not _writers, " · ".join(_writers))

# وبيانات التشغيل نظيفة الآن فعلاً — لا كون من رمزين تركه اختبار
_live = Path(storage.DATA_DIR) / "universe"
_tiny = []
if _live.exists():
    import json as _json

    for _f in _live.glob("*.json"):
        try:
            _d = _json.loads(_f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if 0 < len(_d.get("symbols") or []) < 5:
            _tiny.append(f"{_f.name}:{len(_d['symbols'])}")
check("  ولا كون هزيل في بيانات التشغيل", not _tiny, " · ".join(_tiny))


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
