# -*- coding: utf-8 -*-
"""ربط المحفظة — والمواضع التي يكذب فيها أو يُخطر.

═══ الأوّل: أمرٌ يُرسَل ═══

المنصّة استشارية بنصّ المادّة ١٣ §٣٣. ولا يوجد في المشروع كلّه
سطرٌ يرسل أمراً إلى Binance — والغياب أقوى من راية تمنع، لأنّ
الراية تُقلَب سطراً واحداً.

═══ الثاني: مفتاحٌ يستطيع أكثر من القراءة ═══

مفتاحٌ يسمح بالتداول أو السحب على خادمٍ بلا HTTPS خطرٌ حقيقيّ.
و``canTrade`` في ``/api/v3/account`` يصف **الحساب** لا المفتاح —
فالصلاحيات الحقيقية في ‎/sapi/v1/account/apiRestrictions‎.

═══ الثالث: تكلفةٌ مجهولة تُعرَض كأنّها معروفة ═══

السوق الفوريّ بلا «مراكز»: الرصيد قد يأتي من إيداعٍ لا شراء.
وحسابُ ربحٍ غير محقّق على تكلفةٍ مجهولة يُنتج رقماً واثقاً كاذباً.

═══ والرابع: بيانات محفظةٍ بلا استيثاق ═══

لم يكن في هذا المشروع ``login_required`` واحد. ونتائج المسح شيء،
ورصيدُ الحساب شيءٌ آخر.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner.portfolio.binance_positions import cost_basis  # noqa: E402
from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

ACC = ROOT / "scanner" / "adapters" / "binance_account.py"
acc_src = source_of(ACC)
acc_code = code_of(ACC)


# ═══════════ ١) لا أمرَ يُرسَل ═══════════
#
# فحصٌ على الغياب: كل مسارات Binance التي تغيّر شيئاً.
for bad in ("/api/v3/order", "/sapi/v1/capital/withdraw"):
    c(f"١ لا مسار {bad}", bad not in acc_code, "موجود!")
c("  ولا طلب غير GET", "def _get" in acc_code and "_post" not in acc_code)
c("  والسبب مكتوب", "المادّة ١٣ §٣٣" in acc_src)
# والعرض لا يرسل أيضاً
wv = code_of(ROOT / "web" / "dashboard" / "wallet_views.py")
for bad in ("place_order", "create_order", "cancel_order"):
    c(f"  ولا {bad} في العرض", bad not in wv)
wm = code_of(ROOT / "web" / "dashboard" / "wallet_monitor.py")
c("  والمراقب يُرسل رسالة لا أمراً",
  "telegram.send" in wm and "order" not in wm.lower())


# ═══════════ ٢) صلاحيات المفتاح تُفحَص ═══════════
c("٢ يسأل عن قيود المفتاح", "apiRestrictions" in acc_code)
c("  ولا يكتفي بـ‎canTrade‎", "canTrade" not in acc_code)
c("  والسحب أخطر ما يُحذَّر منه", "enableWithdrawals" in acc_code)
c("  والسبب مكتوب", "يصف الحساب لا المفتاح" in acc_src)
c("  والمجهول ليس آمناً", '"safe": None' in acc_code)
# والتحذير يصل الشاشة
js = (ROOT / "web" / "dashboard" / "static" / "dashboard"
      / "wallet-page.js").read_text(encoding="utf-8")
c("  والشاشة تعرضه", "يستطيع أكثر من القراءة" in js)
c("  والمفتاح الآمن يُعلَن", "للقراءة فقط" in js)


# ═══════════ ٣) التوقيع والساعة ═══════════
c("٣ توقيع HMAC-SHA256", "hashlib.sha256" in acc_code
  and "hmac.new" in acc_code)
# ═══ السلسلة تُبنى مرّةً ═══
#
# إعادة ترميز القاموس بعد التوقيع قد تعطي ترتيباً مختلفاً فيسقط
# التوقيع — وهو خطأٌ يقود إلى الشكّ في المفتاح لا في الترميز.
c("  والسلسلة تُوقَّع كما تُرسَل", "qs}&signature=" in acc_code)
c("  وفارق الساعة يُصحَّح", "_server_time_drift" in acc_code)
c("  و‎-1021‎ يُقال باسمه", "-1021" in acc_code)
c("  والمفتاح لا يُطبع", "log.info(\"مفتاح" not in acc_code)


# ═══════════ ٤) متوسّط التكلفة ═══════════
def T(price, qty, buy=True, fee=0.0, fa="", sym="BTCUSDT", t=0):
    return {"price": price, "qty": qty, "is_buyer": buy, "time": t,
            "commission": fee, "commission_asset": fa, "symbol": sym}


b = cost_basis([T(100, 1, t=1), T(200, 1, t=2)])
c("٤ المتوسّط المرجّح", b["avg_cost"] == 150.0, str(b["avg_cost"]))
c("  والكمّية", b["qty_from_trades"] == 2.0)

# ═══ البيع لا يغيّر متوسّط الدخول ═══
#
# الخطأ الشائع إعادة حسابه بسعر البيع — فيصير «متوسّط الدخول»
# متأثّراً بالخروج وهو ليس دخولاً.
b2 = cost_basis([T(100, 1, t=1), T(200, 1, t=2), T(500, 1, False, t=3)])
c("  والبيع لا يغيّر المتوسّط", b2["avg_cost"] == 150.0, str(b2["avg_cost"]))
c("  والمحقّق من متوسّط الشراء", b2["realized"] == 350.0, str(b2["realized"]))
c("  والباقي واحد", b2["qty_from_trades"] == 1.0)

# ═══ العمولة تُحتسب ═══
#
# إهمالُها يجعل كل مركزٍ يبدو أربح بنحو ٠٫١٪ لكل صفقة — ويتراكم.
bq = cost_basis([T(100, 1, fee=0.1, fa="USDT")])
c("  وعمولة الاقتباس تزيد التكلفة", bq["avg_cost"] == 100.1,
  str(bq["avg_cost"]))
ba_ = cost_basis([T(100, 1, fee=0.001, fa="BTC")])
c("  وعمولة الأصل تُنقص الكمّية",
  abs(ba_["qty_from_trades"] - 0.999) < 1e-9, str(ba_["qty_from_trades"]))

# ═══ وبيعٌ بلا شراءٍ مسجَّل ═══
#
# رصيدٌ من إيداع: لا يُحتسب ربحاً — تكلفته مجهولة.
bs = cost_basis([T(500, 1, False, t=1)])
c("  وبيعٌ بلا شراء لا يُربِح", bs["realized"] == 0.0, str(bs["realized"]))
c("  ولا متوسّط بلا كمّية", cost_basis([])["avg_cost"] is None)


# ═══════════ ٥) الفجوة تُقال ═══════════
bp = code_of(ROOT / "scanner" / "portfolio" / "binance_positions.py")
c("٥ الفجوة تُقاس", "basis_partial" in bp)
c("  وتُشرَح نصّاً", "basis_note" in bp)
c("  والسبب مكتوب",
  "إيداعٌ من محفظة خارجية" in source_of(
      ROOT / "scanner" / "portfolio" / "binance_positions.py"))
c("  والشاشة تحذّر", "basis_partial" in js)
# ولا تدخل المجموع: تكلفةٌ ناقصة تُنتج «ربحاً» وهمياً
c("  ولا تدخل المجموع", "if (p.basis_partial) { partial++; return; }" in js)
# ═══ والربح المجهول ‎null‎ لا صفر ═══
#
# الصفر يُجمَع ويُلوَّن ويُقرأ «لا ربح ولا خسارة» — وهو «لا أعرف».
c("  والمجهول null لا صفر", "return null;" in js.split("function pnl")[1][:400])


# ═══════════ ٦) قواعد الخروج ═══════════
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location(
    "_wm_probe", ROOT / "web" / "dashboard" / "wallet_monitor.py")
_m = _ilu.module_from_spec(_spec)
try:
    _spec.loader.exec_module(_m)
    _ok = True
except Exception as exc:  # noqa: BLE001
    _ok = False
    c("٦ تحميل المراقب", False, f"{type(exc).__name__}: {str(exc)[:70]}")

if _ok:
    def R(kind, **kw):
        d = {"kind": kind, "active": True, "price": None, "pct": None,
             "peak": None}
        d.update(kw)
        return SimpleNamespace(**d)

    c("٦ الوقف يتحقّق عند النزول",
      _m.evaluate(R("stop", price=100), 99)["hit"])
    c("  ولا فوقه", not _m.evaluate(R("stop", price=100), 101)["hit"])
    c("  والهدف عند الصعود",
      _m.evaluate(R("target", price=100), 101)["hit"])
    # ═══ والتراجع بلا قمّةٍ لا يتحقّق ═══
    #
    # حسابُه من قمّةٍ فارغة يقارن بصفرٍ فيتحقّق **دائماً** — أوّل
    # دورةٍ بعد التفعيل كانت سترسل تنبيهاً كاذباً.
    c("  وتراجعٌ بلا قمّة لا يتحقّق",
      not _m.evaluate(R("trail", pct=10), 100)["hit"],
      str(_m.evaluate(R("trail", pct=10), 100)))
    c("  ومع قمّة يتحقّق",
      _m.evaluate(R("trail", pct=10, peak=200), 179)["hit"])
    c("  ولا دونه",
      not _m.evaluate(R("trail", pct=10, peak=200), 185)["hit"])
    # والموقوفة لا تُطلق مهما بلغ السعر
    c("  والموقوفة لا تُطلق",
      not _m.evaluate(R("stop", price=100, active=False), 1)["hit"])
    # والناقصة لا تُطلق: وقفٌ بلا سعر
    c("  والناقصة لا تُطلق", not _m.evaluate(R("stop"), 50)["hit"])
    # وإشارة المنصّة من الحالات نفسها لا من معيارٍ ثانٍ
    c("  والإشارة من حالات المنصّة",
      _m.evaluate(R("signal"), 100,
                  signal={"state": "ALREADY_EXPANDED"})["hit"])
    c("  وبلا تحليلٍ لا تُطلق", not _m.evaluate(R("signal"), 100)["hit"])

# ═══ والتكرار يُمنَع ═══
#
# قاعدةٌ تُفحَص كل دقيقتين وسعرٌ بقي تحت الوقف ساعةً = ثلاثون رسالة.
c("  ومهلةٌ تمنع التكرار", "COOLDOWN_MINUTES" in wm)
c("  ولا تُطفأ تلقائياً", "active = False" not in wm,
  "يُطفئ القاعدة — والقرار لصاحبها")
# والقمّة تُصفَّر عند التعديل: نسبةٌ جديدة على قمّةٍ قديمة تُطلق فوراً
c("  والقمّة تُصفَّر عند التعديل", "rule.peak = None" in wv)


# ═══════════ ٧) الاستيثاق ═══════════
ag = code_of(ROOT / "web" / "dashboard" / "authgate.py")
c("٧ الوسيط موجود", "class LoginRequiredMiddleware" in ag)
st = code_of(ROOT / "web" / "config" / "settings.py")
c("  ومسجَّل في الإعدادات",
  "dashboard.authgate.LoginRequiredMiddleware" in st)
# ═══ بعد الاستيثاق ═══
#
# يحتاج ``request.user`` — فلا بدّ أن يلي ``AuthenticationMiddleware``.
c("  وبعد AuthenticationMiddleware",
  st.index("AuthenticationMiddleware") < st.index("authgate"))
# ═══ وقائمة سماحٍ لا منع ═══
#
# منعُ ما يُذكر يعني أنّ كل صفحةٍ جديدة تُولد مكشوفة.
c("  وقائمة سماح", "PUBLIC_PREFIXES" in ag)
c("  و‎/healthz‎ مستثنى", '"/healthz"' in ag)
c("  وصفحة الدخول", '"/accounts/login"' in ag)
# ═══ والافتراض هو التشغيل ═══
#
# راية تُشغّل الحماية: نسيانها يترك الباب مفتوحاً.
c("  والافتراض مُفعَّل", '"REQUIRE_LOGIN", "1"' in ag)
# ═══ والنداء يُردّ ‎401‎ لا يُحوَّل ═══
#
# ‏fetch يتبع التحويل ويستقبل HTML فيسقط بـ«Unexpected token <».
c("  والنداء يُردّ 401", "status=401" in ag)
c("  والواجهة تعرف", "/accounts/login/" in js)


sys.exit(c.report())
