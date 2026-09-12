# -*- coding: utf-8 -*-
"""دليل الشركات — الجلب على مرحلتين، والتقدّم المرئيّ.

═══ ما يحرسه ═══

  ١. **المرحلتان منفصلتان.** «من في السوق؟» مجاني ورخيص، و«ما تاريخ
     هذا السهم؟» غالٍ. وربطهما يعني أن تعثّر الثاني يُضيّع الأوّل.

  ٢. **النقص لا يُلفَّق.** الأساسيات تحتاج باقة Starter. وتصفير
     مكرّر ربحيةٍ غائب يجعل السهم يبدو رخيصاً بلا حدّ — والصفر رقمٌ
     يُحسب عليه، والغياب حالةٌ تُعرَض.

  ٣. **المهمّة تنتهي دائماً.** استثناءٌ غير متوقّع كان سيترك الحالة
     ``running`` أبداً: الزرّ معطّل والصفحة تستعلم بلا نهاية.

  ٤. **الضغط المزدوج لا يضاعف الطلبات.** مضاعفة الطلبات هي ما
     استدعت ``429`` الذي أوقف اكتشاف السوق الأمريكي.

═══ ولماذا تُنفَّذ لا تُقرأ ═══

في هذه الجلسة مرّ ١٢٤ فحصاً على دالّة لا وجود لها، لأنّها كانت
تفحص ``"def api_trade_review(" in src`` — نصّاً لا تنفيذاً. فما
يمكن تشغيله هنا يُشغَّل فعلاً.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

import pandas as pd  # noqa: E402

from scanner.adapters.sahmk import SahmkAdapter, SahmkError  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


class Fake(SahmkAdapter):
    def __init__(self, routes: dict) -> None:
        super().__init__(api_key="shmk_test")
        self.routes = routes
        self.calls: list[str] = []

    def _get(self, path, params=None):  # noqa: ANN001
        self.calls.append(path)
        for pat, val in self.routes.items():
            if pat in path:
                if isinstance(val, Exception):
                    raise val
                return val
        raise SahmkError(f"مسار غير معرَّف: {path}")


# ── ١) سعر الرمز الواحد — بديل المجانية عن /quotes/ ──
a = Fake({"/quote/": {"quote": {"price": 30.5, "volume": 1_000_000,
                                "change_percent": 1.25}}})
q = a.quote_one("2222.SR")
check("١ يقرأ السعر", q["price"] == 30.5, str(q))
check("  والحجم", q["volume"] == 1_000_000)
check("  والتغيّر", q["change_pct"] == 1.25)
# الرمز يصل مجرّداً وإن أُعطي بلاحقة ياهو
check("  ويرسل الرمز مجرّداً", "/quote/2222/" in a.calls[0], a.calls[0])

# ── ٢) ملفّ الشركة — النقص يُترَك لا يُصفَّر ──
full = Fake({"/company/": {"company": {
    "name_ar": "أرامكو", "name_en": "Aramco",
    "sector_name_ar": "الطاقة", "security_type": "Equity",
    "pe": 15.2, "eps": 1.8, "book_value": 9.4,
    "week_52_high": 40.0, "week_52_low": 24.0}}})
info = full.company_info("2222.SR")
check("٢ الاسم العربي", info["name_ar"] == "أرامكو")
check("  والقطاع", info["sector"] == "الطاقة")
check("  ومكرّر الربحية عدد", info["pe"] == 15.2)
check("  ونطاق ٥٢ أسبوعاً", info["week52_high"] == 40.0)

# باقة مجانية: الوصفيّ يصل والأساسيات غائبة
free = Fake({"/company/": {"company": {
    "name_ar": "سابك", "sector_name_ar": "المواد الأساسية",
    "security_type": "Equity"}}})
finfo = free.company_info("2010")
check("  والوصفيّ يصل بلا أساسيات", finfo["name_ar"] == "سابك")
check("  والأساسيات الغائبة لا تُصفَّر",
      "pe" not in finfo and "eps" not in finfo, str(sorted(finfo)))

# رفض الباقة لا يرمي — يعيد فارغاً فيبقى الاسم من /companies/
denied = Fake({"/company/": SahmkError("403 PLAN_LIMIT")})
check("  ورفض الباقة يعيد فارغاً بلا استثناء",
      denied.company_info("1120") == {})

# قيمة نصّية أو شرطة لا تكسر التحويل
messy = Fake({"/company/": {"company": {"name_ar": "س", "pe": "-",
                                        "eps": "", "book_value": "12.5"}}})
m = messy.company_info("1")
check("  والشرطة تُهمَل لا تصير صفراً", "pe" not in m, str(m))
check("  والنصّ الرقميّ يُحوَّل", m["book_value"] == 12.5)


# ── ٣) آلة التقدّم — تُنفَّذ لا تُقرأ ──
from dashboard import jobs  # noqa: E402

jobs.reset()
check("٣ البداية تنجح", jobs.begin("t", total=10, note="بدء"))
check("  والثانية تُرفَض وهي تعمل", jobs.begin("t") is False)
s = jobs.snapshot("t")
check("  والحالة running", s["state"] == "running", s["state"])
check("  والنسبة صفر", s["percent"] == 0.0)
check("  ولا تقدير قبل أوّل خطوة", s["eta_seconds"] is None)

for i in range(5):
    jobs.step("t", f"خطوة {i}")
s = jobs.snapshot("t")
check("  والخطوات تُحصى", s["done"] == 5, str(s["done"]))
check("  والنسبة نصف", s["percent"] == 50.0, str(s["percent"]))
check("  والملاحظة الأخيرة", s["note"] == "خطوة 4", s["note"])
check("  والتقدير موجود الآن", s["eta_seconds"] is not None)

# التقدير من المعدّل المقاس: ضعف الزمن المنقضي على نصف العمل
s2 = jobs.snapshot("t", now=time.time() + 10)
check("  ويكبر بكِبَر الزمن", s2["eta_seconds"] >= s["eta_seconds"],
      f"{s['eta_seconds']} → {s2['eta_seconds']}")

jobs.finish("t", "تمّ")
s = jobs.snapshot("t")
check("  والإنهاء يضبط done", s["state"] == "done" and s["note"] == "تمّ")
check("  ولا تقدير بعد الانتهاء", s["eta_seconds"] is None)
check("  والبداية تُقبل بعد الانتهاء", jobs.begin("t"))
jobs.finish("t", "", "خطأ ما")
check("  والخطأ يضبط failed",
      jobs.snapshot("t")["state"] == "failed")

# العدد الكلّي قد لا يُعرَف إلّا بعد أوّل نداء شبكة
jobs.reset()
jobs.begin("u")
check("  وبلا كلّي النسبة صفر لا قسمة على صفر",
      jobs.snapshot("u")["percent"] == 0.0)
jobs.set_total("u", 4)
jobs.step("u")
check("  ويُضبط لاحقاً", jobs.snapshot("u")["percent"] == 25.0)
# تجاوز العدد الكلّي لا يعطي نسبةً فوق المئة
for _ in range(10):
    jobs.step("u")
check("  والتجاوز لا يتخطّى ١٠٠٪",
      jobs.snapshot("u")["percent"] == 100.0,
      str(jobs.snapshot("u")["percent"]))


# ── ٤) استثناءٌ في الخيط لا يترك المهمّة معلّقة أبداً ──
#
# بلا الغلاف تبقى الحالة ``running``: الزرّ معطّل والصفحة تستعلم
# بلا نهاية، والمستخدم لا يعلم أنّ شيئاً مات.
jobs.reset()
jobs.begin("boom")


def _explode() -> None:
    raise RuntimeError("انفجار غير متوقّع")


jobs.run_in_thread("boom", _explode)
for _ in range(50):
    if jobs.snapshot("boom")["state"] != "running":
        break
    time.sleep(0.02)
s = jobs.snapshot("boom")
check("٤ الاستثناء يُنهي المهمّة", s["state"] == "failed", s["state"])
check("  والسبب محفوظ", "انفجار" in s["error"], s["error"])

# ودالّة تنتهي بلا إعلان نتيجة لا تُترك معلّقة كذلك
jobs.reset()
jobs.begin("silent")
jobs.run_in_thread("silent", lambda: None)
for _ in range(50):
    if jobs.snapshot("silent")["state"] != "running":
        break
    time.sleep(0.02)
check("  والصمت يُنهيها أيضاً",
      jobs.snapshot("silent")["state"] == "failed",
      jobs.snapshot("silent")["state"])
check("  برسالة تقول إنّه صمت",
      "إعلان" in jobs.snapshot("silent")["error"],
      jobs.snapshot("silent")["error"])

check("  و any_running يعرف من يعمل", jobs.any_running("boom") == "")
jobs.reset()
jobs.begin("x")
check("  ويجده وهو يعمل", jobs.any_running("x", "y") == "x")
jobs.reset()


# ── ٥) الربط: النموذج والهجرة والمسارات والواجهة ──
models_src = (ROOT / "web" / "dashboard" / "models.py").read_text(encoding="utf-8")
mig = (ROOT / "web" / "dashboard" / "migrations"
       / "0015_company.py").read_text(encoding="utf-8")

check("٥ النموذج موجود", "class Company(models.Model)" in models_src)
FIELDS = ("market", "symbol", "name_ar", "sector", "price", "change_pct",
          "volume", "pe", "eps", "week52_high", "week52_low", "candles",
          "last_candle")
missing = [f for f in FIELDS if f'("{f}"' not in mig and f'"{f}"' not in mig]
check("  وكل حقوله في الهجرة", not missing, " · ".join(missing))
# الرمز الواحد مرّة واحدة لكل سوق — وإلّا تضاعف الشركة في كل جلب
check("  والرمز فريد في سوقه",
      "uniq_company_market_symbol" in mig and "uniq_company_market_symbol"
      in models_src)

urls = (ROOT / "web" / "dashboard" / "urls.py").read_text(encoding="utf-8")
for name in ("api_companies", "api_companies_fetch",
             "api_companies_history", "api_companies_status"):
    check(f"  المسار {name}", f'name="{name}"' in urls)

# النقاط الأربع موجودة فعلاً في الوحدة — لا مجرّد اسم في المسارات.
# (هذا بالضبط ما فات في عطب ``get_provider``: المسار موجود والدالّة لا.)
views_src = (ROOT / "web" / "dashboard"
             / "companies_views.py").read_text(encoding="utf-8")
import ast  # noqa: E402

tree = ast.parse(views_src)
defined = {n.name for n in ast.walk(tree)
           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
for fn in ("api_companies", "api_companies_fetch", "api_companies_history",
           "api_companies_status", "_fetch_info", "_fetch_history"):
    check(f"  والدالّة {fn} معرَّفة", fn in defined)

# كل اسم يستورده الملف من ``scanner`` موجود فعلاً
for mod, attr in (("scanner.storage", "last_time_on_disk"),
                  ("scanner.storage", "bars_needed"),
                  ("scanner.storage", "merge"),
                  ("scanner.adapters.sahmk", "SahmkAdapter")):
    import importlib

    check(f"  و{mod}.{attr} موجود",
          hasattr(importlib.import_module(mod), attr))

tpl = (ROOT / "web" / "dashboard" / "templates" / "dashboard"
       / "scanner.html").read_text(encoding="utf-8")
check("  واللوحة في القالب", 'id="companies-panel"' in tpl)
check("  وسعوديّة فقط", 'market == "saudi"' in tpl)
# أحوج ما تكون إليها حين لا تكون هناك دورة بعد
check("  وخارج شرط وجود الدورة",
      tpl.index('id="companies-panel"') < tpl.index("{% if not has_run %}"))
check("  والزرّان موجودان",
      'id="co-fetch"' in tpl and 'id="co-history"' in tpl)
check("  وشريط التقدّم", 'id="co-progress-bar"' in tpl)

js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "companies.js").read_text(encoding="utf-8")
check("  والسكربت يستعلم عن التقدّم", "/api/companies/status/" in js)
# مؤقّتٌ لا يُلغى يبقى يطرق الخادم إلى ما لا نهاية
check("  ويوقف الاستعلام عند الانتهاء", "clearInterval" in js)
check("  ويستعمل postJSON للـ CSRF", "postJSON" in js)
check("  والقالب يحمّله عند السعودي فقط",
      "companies.js" in tpl and tpl.count("companies.js") == 1)


# ── ٦) تحليل القطاعات — يعلن ما لا يعرف ──
#
# ═══ العطب الذي يحرسه ═══
#
# طُلب تحليل القطاعات وكان ٢٩٨ من ٣٢٦ شركة **بلا قطاع**. فأي جدول
# كان سيصف ٨٫٥٪ من السوق ويبدو كأنّه يصفه كلّه.
#
# وهذا أخطر من الامتناع: قارئ الجدول لا يرى ما ليس فيه. يقرأ
# «المواد الأساسية ١٠ شركات +١٫٨٪» فيظنّها القطاع، وهي عشرٌ من
# خمسين — والتسع والثلاثون الباقية قد تكون هابطة.
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_cv", ROOT / "web" / "dashboard" / "companies_views.py")
_src = (ROOT / "web" / "dashboard"
        / "companies_views.py").read_text(encoding="utf-8")

# ``_median`` منطقٌ خالص — يُستخرج ويُنفَّذ فعلاً لا يُقرأ نصّاً
_ns: dict = {}
_tree = ast.parse(_src)
for _n in _tree.body:
    if isinstance(_n, ast.FunctionDef) and _n.name == "_median":
        exec(compile(ast.Module([_n], []), "<median>", "exec"), _ns)
_median = _ns["_median"]

check("٦ الوسيط لعدد فردي", _median([3.0, 1.0, 2.0]) == 2.0)
check("  ولعدد زوجي", _median([1.0, 2.0, 3.0, 4.0]) == 2.5)
check("  والفارغ None", _median([]) is None)
# الغياب يُحذَف لا يُعامل صفراً: صفرٌ دخيل يجرّ الوسيط نحوه
check("  والغائب يُحذَف لا يُصفَّر", _median([None, 4.0, 6.0]) == 5.0)
check("  وكلّه غائب None", _median([None, None]) is None)

# الحدّان مذكوران صراحةً ومستعملان
check("  وحدّ التغطية معرَّف", "MIN_COVERAGE_PCT" in _src)
check("  وحدّ حجم القطاع", "MIN_SECTOR_N" in _src)
_code = "\n".join(l for l in _src.splitlines()
                  if not l.strip().startswith("#"))
check("  والقراءة مشروطة بالتغطية",
      "readable = cov_sector >= MIN_COVERAGE_PCT" in _code)
check("  والعيّنة الضئيلة مُعلَّمة", '"thin"' in _code)
# الترتيب بالعدد لا بالأداء: الترتيب بالأداء على تغطية ناقصة يضع
# أصغر القطاعات عيّنةً في القمّة — ترتيبٌ للضجيج
check("  والترتيب بالعدد لا بالأداء",
      'key=lambda s: (-s["count"]' in _code)
check("  وغير المصنَّف يُحصى", '"unclassified"' in _code)

# المسار موصول والدالّة معرَّفة فعلاً
check("  والمسار موصول", 'name="api_companies_sectors"' in urls)
check("  والدالّة معرَّفة",
      "api_companies_sectors" in {n.name for n in ast.walk(_tree)
                                  if isinstance(n, ast.FunctionDef)})

check("  والقالب فيه الجدول", 'id="co-sec-table"' in tpl)
check("  وموضع تحذير التغطية", 'id="co-cov-warn"' in tpl)
check("  والسكربت يقرأ التغطية", '"/api/companies/sectors/' in js)
check("  ويُظهر التحذير عند النقص", "co-cov-warn" in js or "elCovWarn" in js)

# الاستئناف: الإثراء يتخطّى المكتمل بدل إعادة الثلاثمئة
check("  والإثراء يستأنف", "only_missing" in _code and 'exclude(sector="")' in _code)
check("  والزرّ يمرّر الخيار", "only_missing" in js)
check("  والقالب فيه مفتاحه", 'id="co-resume"' in tpl)


# ── ٧) أمر التجهيز: كل نداء يطابق توقيعه ──
#
# ═══ العطب الذي يحرسه ═══
#
# ``cannot import name 'get_provider'`` — مرّ ١٢٤ فحصاً على دالّة
# لا وجود لها، لأنّ الفحص كان يطابق نصّاً. والنداء بوسيطٍ زائد أو
# باسمٍ خاطئ عطبٌ من العائلة نفسها: لا يظهر إلّا لحظة التشغيل، وهي
# لحظةٌ تقع بعد دقائق من الجلب الثقيل.
BOOT = ROOT / "web" / "dashboard" / "management" / "commands" / "bootstrap_market.py"
check("٧ أمر التجهيز موجود", BOOT.exists())
_bsrc = BOOT.read_text(encoding="utf-8")
_btree = ast.parse(_bsrc)

_sigs = {}
for _n in ast.parse(_src).body:
    if isinstance(_n, ast.FunctionDef):
        _sigs[_n.name] = ([a.arg for a in _n.args.args],
                          [a.arg for a in _n.args.kwonlyargs],
                          len(_n.args.defaults))

_bad = []
_seen = 0
for _n in ast.walk(_btree):
    if not (isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute)):
        continue
    if not (isinstance(_n.func.value, ast.Name) and _n.func.value.id == "cv"):
        continue
    _seen += 1
    _name = _n.func.attr
    if _name not in _sigs:
        _bad.append(f"{_name} غير معرَّفة")
        continue
    _pos, _kwo, _ndef = _sigs[_name]
    _lo, _hi = len(_pos) - _ndef, len(_pos)
    if not (_lo <= len(_n.args) <= _hi):
        _bad.append(f"{_name}: {len(_n.args)} وسيطاً والتوقيع {_lo}..{_hi}")
    for _k in _n.keywords:
        if _k.arg not in _pos + _kwo:
            _bad.append(f"{_name}: وسيط مسمّى غريب {_k.arg}")

check("  ويستدعي دوالّ الجلب فعلاً", _seen >= 2, f"{_seen} نداء")
check("  وكل نداء يطابق توقيعه", not _bad, " · ".join(_bad))

# المراحل الثلاث موجودة ومرتَّبة: معلومات ← تاريخ ← مسح
for _m in ("_phase_info", "_phase_history", "_phase_scan", "_state", "_delta"):
    check(f"  والمرحلة {_m}", _m in _bsrc)
check("  والترتيب صحيح",
      _bsrc.index("_phase_info(") < _bsrc.index("_phase_history(")
      < _bsrc.index("_phase_scan("))
# «تمّ» تصدق حتى حين لا يتغيّر شيء — الفرق وحده يقول هل نفعت
check("  ويطبع الفرق لا «تمّ»", "لم يتغيّر شيء" in _bsrc)
check("  و --check لا يكتب شيئاً",
      _bsrc.index('opts["check"]') < _bsrc.index("_phase_info(market"))


# ── ٨) الشارت والتحليل داخل الصفّ ──
#
# ═══ ولماذا من ``/api/chart/`` نفسه ═══
#
# مصدران يرسمان السهم نفسه يختلفان يوماً ما، وحينها لا يُعرَف أيّهما
# الصادق. فاللوحة تستعمل النقطة التي تستعملها صفحة الرمز — لا حساب
# ثانٍ ولا تعريف ثانٍ لـ«النقاط» أو «القرار».
check("٨ الصفّ يفتح على الشارت", "co-toggle" in js and "toggleRow" in js)
check("  ومن نقطة الشارت الرسمية", '"/api/chart/" + MARKET' in js)
check("  ولا ينشئ حساباً موازياً",
      "score_with_recommendation" not in js and "/api/companies/chart" not in js)

# شموع لا خطّ إغلاق: الخطّ يُخفي الفتيل، والفتيل موضع الوقف غالباً
check("  ويرسم شموعاً لا خطّاً", "drawCandles" in js
      and "k.high" in js and "k.low" in js)
check("  والصاعد والهابط متمايزان", "#3ddc97" in js and "#ff6b6b" in js)

# التحليل يعرض ما يُتصرَّف به لا الرقم وحده
for _k in ("score", "decision", "confluence", "rsi", "rvol", "atr_pct",
           "blocker", "ready"):
    check(f"  ويعرض {_k}", _k in js)
check("  والتوصية بمستوياتها",
      "reco.entry" in js and "reco.stop" in js and "reco.targets" in js)

# صفٌّ واحد مفتوح: فتح الجميع يطلب عشرات الشارتات دفعةً واحدة
check("  وصفٌّ واحد مفتوح", "openRow" in js and "openRow.el.remove()" in js)
check("  والمرجع يسقط عند إعادة البناء",
      "openRow = null;   // الجدول" in js)

# الرمز بلا شموع لا يُعطى زرّاً يكذب
check("  وبلا شموع لا زرّ", "canOpen" in js)

# ونقطة الشارت تعطي فعلاً ما يقرأه السكربت — لا نصّاً متوقّعاً
_views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
for _f in ('"score"', '"decision"', '"confluence"', '"rsi"', '"rvol"',
           '"atr_pct"', '"blocker"', '"ready"', '"htf_text"',
           '"candles_count"', '"recommendation"'):
    check(f"  و api_chart يُرجع {_f}", _f in _views)
_ov = (ROOT / "scanner" / "analysis"
       / "overlay.py").read_text(encoding="utf-8")
check("  والشموع فيها high/low", '"high": float(h)' in _ov
      and '"low": float(l)' in _ov)


# ── ٩) تعليق القالب لا يُطبع للمستخدم ──
#
# ‏Django يطابق ``{#.*?#}`` بلا ``re.DOTALL``. فالتعليق الممتدّ على
# سطرين لا يُطابَق ويُطبَع حرفيّاً — ظهر شرحٌ داخليّ كامل فوق جدول
# القطاعات في اللوحة. والقالب يُصرَّف بلا خطأ، فلا شيء ينبّه.
_leaks = []
for _p in (ROOT / "web").rglob("*.html"):
    for _i, _ln in enumerate(_p.read_text(encoding="utf-8").splitlines(), 1):
        if "{#" in _ln and "#}" not in _ln.split("{#", 1)[1]:
            _leaks.append(f"{_p.name}:{_i}")
check("٩ لا تعليق ممتدّ يتسرّب", not _leaks, " · ".join(_leaks))
check("  والفاحص يمسكه",
      "ممتدّ على أكثر من سطر" in (ROOT / "tools_check_templates.py")
      .read_text(encoding="utf-8"))


failed = [r for r in results if not r[0]]
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name + (f" — {extra}" if extra and not ok else ""))
print()
print(f"✓ {len(results)} اختباراً" if not failed
      else f"✗ فشل {len(failed)} من {len(results)}")
sys.exit(1 if failed else 0)
