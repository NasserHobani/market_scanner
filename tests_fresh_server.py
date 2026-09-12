# -*- coding: utf-8 -*-
"""أعطالٌ لا تظهر إلّا على خادمٍ نظيف.

جهازك يخفيها كلّها، لأنّ فيه ملفّاتٍ تراكمت و‎.env‎ مكتوباً باليد.
فما إن يُنشَر النظام على وحدةِ تخزينٍ فارغة حتى تظهر معاً —
وكلّها تُنتج «يعمل» في السجلّ ونتيجةً خاطئة على الشاشة.

═══ الأوّل: ``universe: auto`` لم يعمل قطّ ═══

كان الشرط ``if not symbols`` — لا تكتشف إلّا إن لم يكن هناك شيء.
و``symbols`` تحمل قائمة الـYAML المضافة قبله بسطرين: عشرة رموز
لكريبتو وعشرة للأمريكي. فالاكتشاف معطّلٌ منذ أن كُتبت القائمة.

ولم يظهر محلّياً لأنّ ملفّات القرص تدخل ``symbols`` أيضاً — ٢١٠
رموز كريبتو جُمعت أيّام كانت القائمة فارغة. فبدا يعمل وهو ميّت.

وانكشف على خادمٍ نظيف: «١٠ من ١٠ رموز متأخّرة». السوق كلّه عشرة.

═══ الثاني: ‎${VAR}‎ الفارغة ليست غائبة ═══

``docker compose`` يمرّر ``FOO: ${FOO}`` غير المضبوط بوصفه سلسلةً
فارغة **موجودة**. و``load_env`` كان يسأل ``k not in os.environ``
فيراها مضبوطة ويتخطّى قيمة ‎.env‎.

وأثره: ``DJANGO_SECRET_KEY`` يُولَّد من جديد في كل تشغيل، فتنتهي
كل جلسة وكل رمز CSRF مع كل أمر.

═══ الثالث: المفتاح السرّي في ‎.env‎ ═══

و‎.env‎ يسكن طبقة الصورة. فكل ``Pull and redeploy`` يمحوه. ومكانه
الصحيح ``data/`` — وحدةُ تخزينٍ تبقى، وهي حيث يكتبه الـentrypoint
أصلاً.

═══ الرابع: اسمٌ يُمرَّر واسمٌ يُقرأ ═══

‏compose يمرّر ``ALPACA_API_KEY`` والمحوّل يقرأ ``ALPACA_API_KEY_ID``،
ويمرّر ``TELEGRAM_BOT_TOKEN`` والكود يقرأ ``TELEGRAM_TOKEN``.
فالمفتاح **في الحاوية** والنظام يقول «غير مضبوط»: صفرُ شمعة في
السوق الأمريكي، ولا تنبيه تيليجرام يصل — وغيابُ التنبيه لا
يُنبِّه.

═══ والخامس: إرشادٌ يدلّ على المكان الخطأ ═══

لافتة «الإعداد ناقص» كانت تقول «أضف إلى ‎.env‎ في جذر المشروع» —
وهو داخل الحاوية ملفٌّ يُمحى مع كل نشر. فمن اتّبعها ضبط مفاتيحه
ثمّ فقدها عند أوّل تحديث.
"""
from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


# ═══════════ ١) الاكتشاف يعمل مع البذور ═══════════
from scanner.market_sync import service as SVC  # noqa: E402


class _FakeAdapter:
    def __init__(self, found: list[str] | None = None, boom: bool = False):
        self._found = found or []
        self._boom = boom
        self.calls = 0

    def usdt_universe(self, *a, **k):
        self.calls += 1
        if self._boom:
            raise RuntimeError("المنصّة لا تردّ")
        return list(self._found)


class _Cfg:
    symbols = ["BTCUSDT", "ETHUSDT"]
    universe = "auto"
    adapter = "binance"
    universe_adapter = ""
    timeframes = ["4h"]
    min_quote_volume = 0
    top_n = 0
    workers = 4


def _resolve(found=None, boom=False, seeds=None, universe="auto"):
    """``resolve_symbols`` معزولةً عن القرص والشبكة."""
    fake = _FakeAdapter(found, boom)
    cfg = _Cfg()
    cfg.symbols = list(_Cfg.symbols if seeds is None else seeds)
    cfg.universe = universe
    orig_adapter, orig_load, orig_stored = (
        SVC.get_adapter, SVC.load_market, SVC.storage.stored_symbols)
    SVC.get_adapter = lambda _n: fake
    SVC.load_market = lambda _p: cfg
    SVC.storage.stored_symbols = lambda *_a, **_k: []   # قرصٌ فارغ = خادمٌ جديد
    try:
        return SVC.MarketDataSyncService().resolve_symbols("crypto"), fake
    finally:
        (SVC.get_adapter, SVC.load_market,
         SVC.storage.stored_symbols) = orig_adapter, orig_load, orig_stored


out, fake = _resolve(found=[f"S{i}USDT" for i in range(50)])
check("١ الاكتشاف يعمل رغم وجود البذور", fake.calls == 1)
check("  والكون أكبر من القائمة", len(out) == 52, f"{len(out)}")
# البذور أوّلاً: أهمّ الرموز تُزامَن قبل أن تنفد المهلة
check("  والبذور أوّلاً", out[:2] == ["BTCUSDT", "ETHUSDT"], str(out[:3]))
check("  والمكتشَف بعدها", "S0USDT" in out)

# التكرار بين البذور والمكتشَف يُزال
out2, _ = _resolve(found=["BTCUSDT", "XRPUSDT"])
check("  ولا تكرار", out2.count("BTCUSDT") == 1, str(out2))
check("  والاتّحاد صحيح", sorted(out2) == ["BTCUSDT", "ETHUSDT", "XRPUSDT"],
      str(out2))

# ═══ فشل الاكتشاف لا يُفرغ السوق ═══
#
# الصيغة الأولى كانت ``symbols = list(...)`` — إسناداً لا إضافة.
# فلو رُفع الشرط وحده لصار فشلُ الشبكة يمحو البذور أيضاً.
out3, _ = _resolve(boom=True)
check("  وفشل الاكتشاف يُبقي البذور", out3 == ["BTCUSDT", "ETHUSDT"],
      str(out3))

# و``universe`` غير ``auto`` لا يكتشف أصلاً
out4, fake4 = _resolve(found=["ZZZ"], universe="list")
check("  و‎universe: list‎ لا يكتشف", fake4.calls == 0 and out4 == [
    "BTCUSDT", "ETHUSDT"], str(out4))

# وقائمةٌ فارغة مع auto: السلوك القديم يبقى سليماً
out5, _ = _resolve(found=["AAA", "BBB"], seeds=[])
check("  وبلا بذورٍ يبقى الاكتشاف وحده", out5 == ["AAA", "BBB"], str(out5))


# ═══════════ ٢) الفارغ كالغائب ═══════════
from scanner import env as E  # noqa: E402

with tempfile.TemporaryDirectory() as _d:
    f = Path(_d) / ".env"
    f.write_text("A=من_الملف\nB=من_الملف\nC=من_الملف\n", encoding="utf-8")

    os.environ["A"] = ""            # كما يمرّرها compose
    os.environ["B"] = "   "         # مسافات
    os.environ["C"] = "من_البيئة"   # مضبوطة فعلاً
    E._LOADED.clear()
    E.load_env(f, force=True)

    check("٢ الفارغة تُملأ من ‎.env‎", os.environ["A"] == "من_الملف")
    check("  والمسافات كالفارغة", os.environ["B"] == "من_الملف")
    # ═══ والحدّ الآخر ═══
    #
    # لو صارت ‎.env‎ تدهس كل شيء لانقلب العطب: متغيّرات بورتينر —
    # وفيها كلمة مرور القاعدة — تُدهَس بملفٍّ قديم في الصورة.
    check("  والمضبوطة لا تُدهَس", os.environ["C"] == "من_البيئة")
    for k in "ABC":
        os.environ.pop(k, None)


# ═══════════ ٣) المفتاح السرّي يثبت ═══════════
#
# الفحص بتشغيلٍ حقيقيّ ثلاث مرّات: قراءةُ الكود تقول ما نيّته،
# والتشغيل يقول ما يفعله. والعطب كان في الفرق بينهما بالضبط.
with tempfile.TemporaryDirectory() as _d:
    work = Path(_d) / "proj"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(
        "data", "reports", "ship", ".git", "__pycache__", "*.npz",
        "staticfiles", ".env", "*.sqlite3*"))
    (work / "data").mkdir(exist_ok=True)
    env = dict(os.environ, DJANGO_SECRET_KEY="",   # ‏compose تمرّرها فارغة
               AUTO_SCAN="0", SCHEDULER_ENGINE="off")
    # الدالّة وحدها: بقيّة الإعدادات تحتاج Django وليس هو المقصود
    code = ("import sys;sys.path.insert(0,'web');"
            "s=open('web/config/settings.py',encoding='utf-8').read()"
            ".split('SECRET_KEY = _secret_key()')[0];"
            "g={'__file__':'web/config/settings.py'};"
            "exec(compile(s,'s','exec'),g);print('KEY',g['_secret_key']())")
    keys, gens = [], []
    for _ in range(3):
        r = subprocess.run([sys.executable, "-c", code], cwd=work, env=env,
                           capture_output=True, text=True, timeout=90,
                           encoding="utf-8", errors="replace")
        gens.append("وُلِّد" in r.stdout)
        keys.append(next((l[4:] for l in r.stdout.splitlines()
                          if l.startswith("KEY")), "ERR:" + r.stderr[-120:]))

    check("٣ المفتاح ثابت في ٣ تشغيلات",
          len(set(keys)) == 1 and not keys[0].startswith("ERR"),
          str([k[:10] for k in keys]))
    check("  يُولَّد مرّةً واحدة", gens == [True, False, False], str(gens))
    kf = work / "data" / ".django_secret_key"
    check("  ويُحفظ في ‎data/‎ لا ‎.env‎",
          kf.exists() and not (work / ".env").exists())
    if kf.exists() and os.name != "nt":
        check("  بصلاحيات ‎600‎", oct(kf.stat().st_mode)[-3:] == "600",
              oct(kf.stat().st_mode)[-3:])
    check("  وطوله كافٍ", len(keys[0]) >= 40, str(len(keys[0])))

    # ومفتاحٌ صريح في البيئة يفوز على المحفوظ
    r = subprocess.run([sys.executable, "-c", code], cwd=work,
                       env={**env, "DJANGO_SECRET_KEY": "مفتاحي-الصريح"},
                       capture_output=True, text=True, timeout=90,
                       encoding="utf-8", errors="replace")
    check("  والصريح يفوز على المحفوظ",
          "KEY مفتاحي-الصريح" in r.stdout, r.stdout[-120:])


# ═══════════ ٤) الأسماء المرادفة ═══════════
#
# ═══ العطب الذي تكرّر ═══
#
# ‏compose يمرّر اسماً والكود يقرأ آخر. فالمفتاح **موجود** في
# الحاوية والنظام يقول «غير مضبوط» — والسوق الأمريكي بصفر شمعة،
# ولا تنبيه تيليجرام يصل، وكل شيءٍ آخر يبدو سليماً.
#
# والاختبار يُستورَد بلا ``load_env()``: الصيغة الأولى استوردت
# ``scanner`` فحمّلت ‎.env‎ الجهاز وطبعت مفاتيحه الحقيقية في
# المخرَج. واختبارٌ يقرأ أسرار المستخدم ليفحص منطقاً عطبٌ في
# الاختبار.
_esrc = (ROOT / "scanner" / "env.py").read_text(encoding="utf-8").replace(
    "\nload_env()\n", "\n")
_emod: dict = {"__file__": str(ROOT / "scanner" / "env.py"), "__name__": "_e"}
exec(compile(_esrc, "env.py", "exec"), _emod)   # noqa: S102
_apply, _ALIASES = _emod["apply_aliases"], _emod["ALIASES"]


def _alias_case(**env) -> tuple[str, str, str]:
    for k in list(os.environ):
        if k.startswith(("ALPACA", "APCA", "TELEGRAM")):
            del os.environ[k]
    os.environ.update(env)
    _apply()
    return (os.getenv("ALPACA_API_KEY_ID", ""),
            os.getenv("ALPACA_API_SECRET_KEY", ""),
            os.getenv("TELEGRAM_TOKEN", ""))


check("٤ أسماء compose تصل الكود",
      _alias_case(ALPACA_API_KEY="K1", ALPACA_SECRET_KEY="S1",
                  TELEGRAM_BOT_TOKEN="T1") == ("K1", "S1", "T1"))
check("  وأسماء الكود كما هي",
      _alias_case(ALPACA_API_KEY_ID="K2", ALPACA_API_SECRET_KEY="S2",
                  TELEGRAM_TOKEN="T2") == ("K2", "S2", "T2"))
# والاتّجاه واحد: من ضبط الاسمين يفوز القانونيّ — وهو ما يتوقّعه
check("  والقانونيّ يفوز عند التعارض",
      _alias_case(ALPACA_API_KEY="من_compose",
                  ALPACA_API_KEY_ID="K3")[0] == "K3")
check("  ولا شيء يُختلَق", _alias_case() == ("", "", ""))
for k in list(os.environ):
    if k.startswith(("ALPACA", "APCA", "TELEGRAM")):
        del os.environ[k]

# وتسمية Alpaca الرسمية باقية — من لصق مفاتيحه بها لا يُكسَر
alp = (ROOT / "scanner" / "adapters" / "alpaca.py").read_text(encoding="utf-8")
check("  وتسمية APCA الرسمية باقية", "APCA_API_KEY_ID" in alp)


# ═══════════ ٥) لا متغيّر يُمرَّر ولا يُقرأ ═══════════
#
# هذا هو الحارس الذي كان سيمسك العطبين قبل النشر. والفحص بنيويّ:
# كل متغيّرٍ في ``environment:`` بـcompose يجب أن يُقرأ في كودٍ
# يعمل داخل الحاوية.
import re as _re  # noqa: E402

import yaml as _yaml  # noqa: E402

_c = _yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
_passed = {k for svc in _c["services"].values()
           for k in (svc.get("environment") or {})}

# ما تستهلكه صورة postgres نفسها — لا كودُنا
_IMAGE_OWNED = {"POSTGRES_INITDB_ARGS"}

_src = ""
for _p in (list((ROOT / "scanner").rglob("*.py"))
           + list((ROOT / "web").rglob("*.py"))
           + [ROOT / "docker-entrypoint.sh", ROOT / "docker-scheduler.sh"]):
    try:
        _src += _p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass

_unread = sorted(
    v for v in _passed - _IMAGE_OWNED
    if not _re.search(rf'["\']{_re.escape(v)}["\']|\$\{{?{_re.escape(v)}\b',
                      _src))
check("٥ كل متغيّرٍ مُمرَّر يُقرأ", not _unread, str(_unread))

# والعكس: مُوثَّقٌ في القالب ولا يُمرَّر = وعدٌ لا يُنفَّذ
_tpl = (ROOT / ".env.docker.example").read_text(encoding="utf-8")
_tcode = "\n".join(l for l in _tpl.splitlines()
                   if not l.strip().startswith("#"))
_declared = {m for m in _re.findall(r"^([A-Z_][A-Z0-9_]*)=", _tcode, _re.M)}
# ‏WEB_BIND وWEB_PORT وSCHEDULER_INTERVAL_SECONDS تُستعمل خارج
# ``environment:`` — في ``ports`` وفي أمر المجدول
_OUTSIDE_ENV = {"WEB_BIND", "WEB_PORT"}
_promised = sorted(_declared - _passed - _OUTSIDE_ENV)
check("  ولا موثَّقٌ بلا تمرير", not _promised, str(_promised))


# ═══════════ ٦) الإرشاد يتبع مكان التشغيل ═══════════
#
# لافتة «الإعداد ناقص» كانت تقول: «أضف إلى ملفّ ‎.env‎ في جذر
# المشروع». وهي نصيحةٌ خاطئة داخل حاوية — الملفّ في طبقة الصورة
# يمحوه كل ``Pull and redeploy``. فمن اتّبعها ضبط مفاتيحه ثمّ
# فقدها عند أوّل تحديث، ولا شيء يقول لماذا.
_views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
_vt = ast.parse(_views)
_hint = next((ast.get_source_segment(_views, n) or "" for n in ast.walk(_vt)
              if isinstance(n, ast.FunctionDef) and n.name == "_setup_hint"), "")
_hint_code = "\n".join(l for l in _hint.splitlines()
                       if not l.strip().startswith("#"))

check("٦ اللافتة تعرف أنّها في حاوية", "/.dockerenv" in _hint_code)
check("  فتدلّ على بورتينر", "Environment variables" in _hint_code)
check("  بأسماء compose", "ALPACA_SECRET_KEY" in _hint_code)
check("  وتحذّر من ‎.env‎ داخلها", "يُمحى مع كل نشر" in _hint_code)
# ومسار الجهاز باقٍ بأسمائه: من يعمل محلّياً لا يُرسَل إلى بورتينر
check("  ومسار الجهاز باقٍ", "ALPACA_API_KEY_ID" in _hint_code
      and "جذر المشروع" in _hint_code)


# ═══════════ ٧) الاستبعاد بالرمز لا بالسوق ═══════════
#
# ═══ العطب في اتّجاهين معاً ═══
#
# كانت البوّابة تحجب السوق كلّه إن تجاوز نصفُ رموزه الحدّ:
#
#   عند ٤٩٪ حرجاً  ← تمرّ، فيُمسَح نصف السوق ببياناتٍ قديمة
#   عند ٥١٪ حرجاً  ← تُحجب النتائج كلّها، ومنها ٤٩ رمزاً سليماً
#
# فهي أقلّ أماناً وأقلّ نفعاً في آن. والنسبة تحمي الأغلبية —
# والخطر في الرمز الواحد.
def _gate(statuses: list[str], auto_refresh: bool = False):
    """البوّابة على حالاتٍ مصنوعة، بلا قرصٍ ولا شبكة."""
    syms = [f"S{i}" for i in range(len(statuses))]
    orig_assess, orig_resolve = SVC.assess_freshness, SVC.MarketDataSyncService.resolve_symbols
    SVC.assess_freshness = lambda m, s, tf, **k: {
        "symbol": s, "market": m, "timeframe": tf,
        "status": statuses[syms.index(s)]}
    SVC.MarketDataSyncService.resolve_symbols = lambda self, m, **k: list(syms)
    try:
        return SVC.MarketDataSyncService().scan_freshness_gate(
            "crypto", "4h", symbols=syms, auto_refresh=auto_refresh)
    finally:
        SVC.assess_freshness = orig_assess
        SVC.MarketDataSyncService.resolve_symbols = orig_resolve


g = _gate(["fresh"] * 4 + ["critical"] * 6)      # ٦٠٪ حرجاً: كان يحجب
check("٧ أغلبيةٌ حرجة لا تحجب السوق", g["ok"] is True, g.get("code"))
check("  والكود يقول ‏PARTIAL", g.get("code") == "PARTIAL")
check("  والصالح أربعة", sorted(g["usable"]) == ["S0", "S1", "S2", "S3"],
      str(g.get("usable")))
check("  والمستبعَد ستّة", len(g["excluded"]) == 6, str(g.get("excluded")))
check("  والعدد في الرسالة", "4" in g["reason"] and "6" in g["reason"],
      g.get("reason", ""))

# ═══ والحدّ الآخر: لا رمزٌ قديم يُمسَح ولو كان واحداً من مئة ═══
#
# هذا هو الشقّ الأمنيّ. النسبة كانت تمرّر ٤٩ رمزاً قديماً بلا
# كلمة؛ والاستبعاد بالرمز لا يمرّر واحداً.
g2 = _gate(["fresh"] * 99 + ["critical"])
check("  ورمزٌ قديم واحد يُستبعَد", g2["excluded"] == ["S99"], str(g2["excluded"]))
check("  والباقي يُمسَح", len(g2["usable"]) == 99)

# ═══ الغائب صالح: لا ملفّ = لا سعرٌ قديم ═══
g3 = _gate(["missing"] * 10)
check("  والغائب صالح", g3["ok"] and len(g3["usable"]) == 10, str(g3.get("code")))

# ═══ والحجب الحقيقيّ باقٍ ═══
#
# لا رمز صالح = عطلٌ فعليّ. وإسقاط هذه الحالة يجعل المسح يعمل
# على لا شيء ويحفظ دورةً فارغة تبدو نتيجة.
g4 = _gate(["critical"] * 8 + ["dead"] * 2)
check("  ولا رمز صالح = حجب", g4["ok"] is False and g4["code"] == "MARKET_DATA_STALE")
check("  برسالةٍ تعدّ الحالات",
      "حرجاً" in g4["reason"] and "مشطوباً" in g4["reason"], g4.get("reason", ""))
check("  والميّت يُستبعَد كالحرج", len(g4["excluded"]) == 10)

g5 = _gate(["fresh"] * 10)
check("  والحديث كلّه ‏FRESH", g5["code"] == "FRESH" and not g5["excluded"])

# ═══ والبوّابة تُنفَّذ لا تُطبَع ═══
#
# رأيٌ يُطبع ولا يُنفَّذ أسوأ من غيابه: يَعِد بحمايةٍ لا تقع. فهذا
# يفحص أنّ أمر المسح يقصّ قائمته فعلاً بما أعادته البوّابة.
_scan = (ROOT / "web" / "dashboard" / "management" / "commands"
         / "scan.py").read_text(encoding="utf-8")
_scode = "\n".join(l for l in _scan.splitlines()
                   if not l.strip().startswith("#"))
check("  وأمر المسح يقرأ ‏usable", 'gate.get("usable")' in _scode)
check("  ويقصّ قائمته بها",
      "symbols = [s for s in symbols if s in allowed]" in _scode)
check("  ويعلن ما استُبعد", "استُبعد" in _scode)


# ═══════════ ٨) تمرين الإقلاع البارد موجود ═══════════
_cs = (ROOT / "tools_coldstart.py")
check("٨ تمرين الإقلاع البارد موجود", _cs.exists())
_cst = _cs.read_text(encoding="utf-8") if _cs.exists() else ""
_cscode = "\n".join(l for l in _cst.splitlines()
                    if not l.strip().startswith("#"))
# ═══ وحداتٌ فارغة وإلّا فالتمرين دافئ ═══
#
# ``down`` بلا ‎-v‎ يُبقي الوحدات، فيبدأ التمرين التالي ببياناتٍ
# موجودة — ويمرّ كاذباً على كل عطبٍ وُجد ليمسكه.
check("  يهدم الوحدات معه", "down" in _cscode and "-v" in _cscode)
check("  وباسم مشروعٍ مستقلّ", 'PROJECT = "mscold"' in _cscode)
check("  فلا يمسّ مكدّسك", "market-scanner" not in _cscode.split("COMPOSE =")[1][:200])
for _sig in ("المفتاح السرّي", "أقفال", "credentials", "resolve_symbols",
             "unhealthy", "scan_freshness_gate"):
    check(f"  ويفحص: {_sig}", _sig in _cst)


# ═══════════ التقرير ═══════════
print(__doc__.strip().splitlines()[0])
print()
for ok, name, extra in results:
    print(("✓ " if ok else "✗ ") + name
          + (f"   [{extra}]" if extra and not ok else ""))
bad = [n for ok, n, _ in results if not ok]
print()
print(f"{len(results) - len(bad)}/{len(results)} "
      + ("✓" if not bad else "✗ فشل: " + " · ".join(bad[:5])))
sys.exit(1 if bad else 0)
