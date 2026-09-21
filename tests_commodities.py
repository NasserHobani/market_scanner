# -*- coding: utf-8 -*-
"""سوق الذهب — وفخّان في إضافة سوقٍ جديد.

═══ الأوّل: جلسةٌ غائبة ═══

السوق المجهول يُعامَل «مفتوحاً دائماً». وهو آمنٌ للذهب في بينانس:
‏PAXG و‏XAUT على دفترٍ مفتوح ٢٤/٧ كأيّ زوج، لا جلسة ولا عطلة.

وهي **ليست** جلسة الذهب الفوريّ (٢٤/٥) — وهذا الفرق هو سبب
اختيار رمزي بينانس أصلاً.

═══ الثاني: ‏XAUUSD ليس سوقاً ═══

سعرُ فوركس لا دفترٌ مركزيّ: كل وسيطٍ وسعره، ولا حجم حقيقيّ فيه.
ونصف مؤشّرات هذا النظام حجم — ‏OBV وCMF وMFI وRVOL ورصد الاختراق
— فتصمت كلّها أو تكذب. و‏XAUUSDT لا وجود له في بينانس أصلاً.

═══ الثالث: عتبةٌ منسوخة ═══

‏RVOL في سوقٍ هادئ نادراً ما يبلغ ١٫٥. ونسخُ عتبة الكريبتو يجعل
عامل الحجم صفراً **دائماً** — فيبدو مقيساً وهو معطَّل.
"""
from __future__ import annotations

import sys
from datetime import time as _t
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner import sessions  # noqa: E402

results: list[tuple[bool, str, str]] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    results.append((bool(cond), name, extra))


GOLD = yaml.safe_load((ROOT / "config" / "gold.yaml").read_text(
    encoding="utf-8"))


# ═══════════ ١) المصدر والرموز ═══════════
check("١ الذهب من بينانس", GOLD["adapter"] == "binance", GOLD["adapter"])
check("  ورموزه مغطّاة بالسبائك",
      set(GOLD["symbols"]) == {"PAXGUSDT", "XAUTUSDT"}, str(GOLD["symbols"]))
# ═══ ولا XAUUSD ولا XAUUSDT ═══
#
# الأوّل بلا حجمٍ حقيقيّ، والثاني لا وجود له. وكتابةُ أيّهما تُنتج
# سوقاً يفشل جلبُه كل دورة بلا أن يظهر السبب في الواجهة.
_all = set(GOLD["symbols"])
check("  ولا XAUUSD في القوائم", "XAUUSD" not in _all)
check("  ولا XAUUSDT", "XAUUSDT" not in _all)

# ═══ والنفط حُذف ═══
#
# بقاءُ ``oil.yaml`` بعد حذف السوق من ``MARKETS`` يُنتج ملفّاً
# يُحمَّل ولا يُعرَض: مزامنةٌ تعمل على سوقٍ لا شاشة له.
check("  و‎oil.yaml‎ محذوف",
      not (ROOT / "config" / "oil.yaml").exists(),
      "ما زال موجوداً")

for _n, _c in (("gold", GOLD),):
    check(f"  و‎{_n}‎ قائمةٌ لا اكتشاف", _c["universe"] == "list",
          str(_c.get("universe")))
    check(f"  واسمه يطابق ملفّه", _c["name"] == _n, str(_c.get("name")))
    # ‏4h هو ما تقرؤه الماسحات — وسوقٌ بفريمٍ آخر لا يُمسَح أصلاً
    check(f"  وفريم مسحه 4h", "4h" in (_c.get("timeframes") or []),
          str(_c.get("timeframes")))


# ═══════════ ٢) الجلسة ═══════════
check("٢ الذهب مفتوحٌ دائماً",
      sessions.get_session("gold").always_open is True)
# ═══ وهذا مذكورٌ صراحةً لا متروكٌ للافتراض ═══
#
# المجهول يُعامَل «مفتوحاً دائماً» أيضاً — فالنتيجة واحدة اليوم.
# لكنّ الذكر الصريح يوثّق أنّها **جلسة بينانس** لا سهوٌ عن جلسة
# الذهب الفوريّ (٢٤/٥). ولو تغيّر الافتراض يوماً بقي الذهب
# صحيحاً.
_src = (ROOT / "scanner" / "sessions.py").read_text(encoding="utf-8")
check("  ومذكورٌ في الجلسات", '"gold"' in _src)
check("  ولا جلسة نفط باقية", '"oil"' not in _src, "بقيت")

_sat = pd.Timestamp("2026-09-19 18:00", tz="UTC")     # سبت
check("  ومفتوحٌ في السبت", sessions.is_open("gold", _sat) is True)


# ═══════════ ٣) العتبات معايَرة لا منسوخة ═══════════
import importlib  # noqa: E402

_crypto = yaml.safe_load((ROOT / "config" / "crypto.yaml").read_text(
    encoding="utf-8"))
for _n, _c in (("gold", GOLD),):
    _rv = float((_c.get("params") or {}).get("rvol_mult", 0))
    _cv = float((_crypto.get("params") or {}).get("rvol_mult", 0))
    check(f"٣ ‎{_n}‎ عتبة RVOL أخفض من الكريبتو", 0 < _rv < _cv,
          f"{_rv} مقابل {_cv}")
    # والعتبة الأعلى للإشارة: سوقٌ هادئ بعتبةٍ منخفضة يُنتج إشارةً
    # كل يوم — وإشارةٌ تأتي كل يوم ليست إشارة
    check(f"  و‎{_n}‎ عتبة الإشارة أعلى",
          float(_c["strong_threshold"]) > float(_crypto["strong_threshold"]),
          f"{_c['strong_threshold']} مقابل {_crypto['strong_threshold']}")


# ═══════════ ٤) التسجيل في الواجهة ═══════════
_views = (ROOT / "web" / "dashboard" / "views.py").read_text(encoding="utf-8")
_code = "\n".join(l for l in _views.splitlines()
                  if not l.strip().startswith("#"))
_markets_line = _code.split("MARKETS = ")[1][:120]
check("٤ الذهب في MARKETS", '"gold"' in _markets_line, _markets_line[:90])
# ═══ والنفط منزوعٌ من كل موضع ═══
#
# سوقٌ محذوفٌ من القائمة وباقٍ في خريطة الأسماء يظهر في مكانٍ
# ويغيب عن آخر — وهو ما يُنتج «سوق غير معروف» في نصف الشاشات.
check("  والنفط خارجها", '"oil"' not in _markets_line, _markets_line[:90])
# ═══ والاسم العربيّ لازم ═══
#
# مفتاحٌ بلا ترجمة يظهر «gold» خاماً وسط قائمةٍ عربية — والخريطة
# في موضعٍ واحد كي لا تُضاف في قالبٍ ويُنسى في آخر.
check("  وله اسمٌ عربيّ", '"gold": "الذهب"' in _code)
check("  ولا اسم للنفط", '"النفط"' not in _code)

from scanner.config import load_market  # noqa: E402

try:
    cfg = load_market(ROOT / "config" / "gold.yaml")
    check("  و‎gold.yaml‎ يُحمَّل", cfg.name == "gold", str(cfg.name))
    check("  ومحوّله معروف", bool(cfg.adapter))
except Exception as exc:  # noqa: BLE001
    check("  و‎gold.yaml‎ يُحمَّل", False,
          f"{type(exc).__name__}: {str(exc)[:80]}")


# ═══════════ ٥) فريمات المزامنة قابلة للضبط ═══════════
#
# كانت أربعة لكل سوق دائماً: ‎15m, 1h, 4h, 1d‎ × عدد الرموز.
# ٥٣٠ رمز كريبتو = ٢٬١٢٠ طلباً في الدورة، وجدولٌ مُشبَعٌ ثلاثة
# أضعاف أصلاً.
from scanner.market_sync import service as SVC  # noqa: E402


class _Cfg:
    name = "crypto"
    timeframes = ["4h"]


def _tfs(raw: str, name: str = "crypto", scan=("4h",)) -> list[str]:
    """الفريمات المختارة لإعدادٍ مكتوب — على المحلّل الحقيقيّ.

    ═══ لا يُستبدَل ``_override_for`` ═══

    الصيغة الأولى استبدلته بلامدا تُحاكي التحليل — فكانت تفحص
    ``_timeframes_for`` وتترك **المحلّل نفسه** بلا اختبار، وهو
    موضع الأخطاء: الفاصلة، والمسافة، والسوق غير المذكور.

    فالمحقون هنا مصدرُ الإعداد لا قارئُه.
    """
    import sys as _s
    import types as _ty

    fake = _ty.ModuleType("dashboard")
    fake.appsettings = _ty.SimpleNamespace(
        values=lambda *a, **k: {"sync_timeframes": raw})
    old = _s.modules.get("dashboard")
    _s.modules["dashboard"] = fake
    c = _Cfg()
    c.name, c.timeframes = name, list(scan)
    try:
        return SVC.MarketDataSyncService()._timeframes_for(c)
    finally:
        if old is None:
            _s.modules.pop("dashboard", None)
        else:
            _s.modules["dashboard"] = old


check("٥ بلا إعداد تبقى الأربعة",
      set(_tfs("")) >= {"15m", "1h", "4h", "1d"}, str(_tfs("")))
check("  والإعداد يقصّها",
      set(_tfs("crypto=4h,1d")) == {"4h", "1d"}, str(_tfs("crypto=4h,1d")))
# ═══ وفريم المسح لا يُنزَع ═══
#
# إسقاطه يعني سوقاً يُزامَن ولا يُمسَح: الماسح يقرأ القرص فيجده
# فارغاً لذلك الفريم — بلا خطأ ولا صفر نتائج.
check("  وفريم المسح يبقى ولو لم يُذكر",
      "4h" in _tfs("crypto=1d"), str(_tfs("crypto=1d")))
check("  والسوق غير المذكور لا يتأثّر",
      set(_tfs("saudi=1d", name="crypto")) >= {"15m", "1h", "4h", "1d"},
      str(_tfs("saudi=1d", name="crypto")))
# ═══ صيغٌ يكتبها الناس ═══
#
# مسافاتٌ حول الفاصلة، وأسواقٌ على سطرٍ واحد بنقطة، وحالة أحرفٍ
# مختلفة. وإعدادٌ صحيحُ المعنى يُرفَض بسبب مسافةٍ هو أسوأ من
# غيابه: المستخدم يراه مكتوباً ويظنّه يعمل.
check("  والمسافات تُتجاهَل",
      set(_tfs("crypto = 4h , 1d")) == {"4h", "1d"},
      str(_tfs("crypto = 4h , 1d")))
check("  والنقطة تفصل الأسواق",
      set(_tfs("saudi=1d · crypto=4h,1d")) == {"4h", "1d"},
      str(_tfs("saudi=1d · crypto=4h,1d")))
# ═══ والمسافة تفصل الأسواق — وهذا ما وقع ═══
#
# كُتب الإعداد في سطرٍ واحد بمسافات:
#
#     crypto=4h,1d,1h,15m saudi=1d,4h gold=4h,1d us=1d,4h
#
# وكانت المسافة ليست فاصلاً، فصار السطر كلّه قيمةَ ``crypto``:
# ضاع ``15m`` لالتصاقه بـ``saudi=1d``، وبقيت الأسواق الثلاثة على
# الافتراض. بلا خطأ ولا تنبيه.
_one = "crypto=4h,1d,1h,15m saudi=1d,4h gold=4h,1d us=1d,4h"
check("  والمسافة تفصل الأسواق",
      set(_tfs(_one)) == {"4h", "1d", "1h", "15m"}, str(_tfs(_one)))
check("  والسوق الثاني في السطر يُقرأ",
      set(_tfs(_one, name="saudi", scan=("1d",))) == {"1d", "4h"},
      str(_tfs(_one, name="saudi", scan=("1d",))))
check("  والأخير كذلك",
      set(_tfs(_one, name="us", scan=("1d",))) == {"1d", "4h"},
      str(_tfs(_one, name="us", scan=("1d",))))
check("  وحالة الأحرف لا تهمّ",
      set(_tfs("CRYPTO=4h,1d")) == {"4h", "1d"}, str(_tfs("CRYPTO=4h,1d")))
# وفريمٌ مجهول يُهمَل ولا يُسقط الباقي
check("  والمجهول يُهمَل",
      set(_tfs("crypto=4h,7x,1d")) == {"4h", "1d"},
      str(_tfs("crypto=4h,7x,1d")))
# ونصٌّ معطوب يعود إلى الافتراض ولا يوقف المزامنة
check("  والمعطوب يعود للافتراض",
      set(_tfs("????")) >= {"15m", "1h", "4h", "1d"}, str(_tfs("????")))

_pref_src = (ROOT / "scanner" / "tf_prefs.py").read_text(encoding="utf-8")
_pref_code = "\n".join(l for l in _pref_src.splitlines()
                       if not l.strip().startswith("#"))
check("  والقراءة لا ترمي", "except Exception" in _pref_code)
check("  والفريم المجهول يُهمَل", "UI_TIMEFRAMES" in _pref_code)
# ═══ ومحلّلٌ واحد للاثنين ═══
#
# نسخةٌ ثانية من التحليل في الماسح كانت ستنحرف عن هذه — فيصير
# ‏«crypto=4h,1h» يُزامِن فريمين ويمسح واحداً.
_svc_src = (ROOT / "scanner" / "market_sync" / "service.py").read_text(
    encoding="utf-8")
check("  والمزامنة تستدعي المحلّل المشترك", "tf_prefs" in _svc_src)
_cron_src = (ROOT / "web" / "dashboard" / "cron.py").read_text(
    encoding="utf-8")
check("  والمسح كذلك", "tf_prefs.scan_for" in _cron_src)

_schema = (ROOT / "scanner" / "settings_schema.py").read_text(
    encoding="utf-8")
check("  والحقل في مخطّط الإعدادات", '"sync_timeframes"' in _schema)
check("  وحقل المسح كذلك", '"scan_timeframes"' in _schema)


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
