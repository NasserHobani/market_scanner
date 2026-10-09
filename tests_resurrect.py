# -*- coding: utf-8 -*-
"""الشطب كان باباً ذا اتّجاه واحد.

═══ ما وقع ═══

شاشة الماسح على الكريبتو:

    فشل: لا رمز واحد ببيانات صالحة — 1 حرجاً و537 مشطوباً من 538
    تعذّر جلبها: 0

و«تعذّر جلبها: صفر» هي الجملة الكاشفة: لم يفشل جلبٌ واحد، لأنّه
لم يُحاوَل واحد.

═══ ولماذا ═══

``dead`` = «آخر شمعة أقدم من مئة شمعة»، ووُضعت للرمز المشطوب من
المنصّة: ملفٌّ باقٍ والجلب التراكمي يطلب الناقص فلا يعود بشيء.

لكنّ مزامنةً تتوقّف أكثر من مئة شمعة (‎4h‎ ← سبعة عشر يوماً)
تُسقط **السوق كلّه** في الخانة دفعةً واحدة. وبعدها:

    ``resolve_symbols``   يستبعد المشطوبين
    بوّابة المسح          تُنعش ``alive`` وحدهم
    و``incremental_refresh_stale`` لا تلمس ``dead`` أصلاً

فلا شيء يجلب لهم. بابٌ يُغلق ولا يُفتح.

═══ والفارق لا يُحزَر من القرص ═══

رمزٌ شُطب ورمزٌ تعطّلت مزامنته: كلاهما ملفٌّ آخر شمعةٍ فيه قديمة.
والسؤال الوحيد الذي يفرّقهما هو **كون المنصّة اليوم**.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

SVC = ROOT / "scanner" / "market_sync" / "service.py"
code = code_of(SVC)
src = source_of(SVC)


# ═══════════ ١) السؤال يُطرح على المنصّة ═══════════
c("١ كون المنصّة يُسأل", "def live_universe" in code)
_lu = code.split("def live_universe")[1][:900]
c("  من المحوّل", "usdt_universe" in _lu)
# ═══ والجهل يُعلَن لا يُخمَّن ═══
#
# «لا أعرف الكون» و«الرمز ليس في الكون» حكمان متضادّان. وخلطهما
# يعني شطب السوق كلّه حين يتعطّل الاكتشاف وحده.
c("  والجهل يعيد None", "return None" in _lu)
c("  وسببه موثَّق", "الفارق الوحيد" in src)


# ═══════════ ٢) الإحياء موجود ويميّز ═══════════
c("٢ الإحياء موجود", "def resurrect" in code)
_rs = code.split("def resurrect")[1][:3000]
c("  والمشطوب حقاً يُترك",
  "universe is not None and sym not in universe" in _rs)
c("  وحدٌّ زمنيّ", "resurrect_seconds" in _rs)
c("  وحدٌّ عدديّ", "resurrect_max_pairs" in _rs)
c("  ولا يعالج إلّا الميّت",
  'FreshnessStatus.DEAD.value' in _rs and "continue" in _rs)

# ═══ والفجوة الواسعة تُعاد بناءً لا دمجاً ═══
#
# ``bars_needed`` محدودٌ بـ``candles``. وفجوةٌ أوسع تعني إطاراً
# فيه **ثقب** بعد الدمج — والمؤشّرات تُحسب عليه صامتةً.
c("  والفجوة الواسعة تُستبدَل", "behind > cfg.candles" in _rs)
c("    بـ‎storage.save‎ لا ‎merge‎", "storage.save(" in _rs)
c("    والأضيق تُرقَّع", "force=True" in _rs)
c("  وسببه", "أطولَ مثقوب" in src)


# ═══════════ ٣) البوّابة تناديه ═══════════
#
# فرعٌ موجود ولا يُنادى = لا شيء. والفرع القائم يُنعش ``alive``
# وحدهم، والمشطوب ليس منهم — فلزِم فرعٌ ثانٍ.
_g = code.split("def scan_freshness_gate")[1]
c("٣ البوّابة تُحيي", "self.resurrect(" in _g)
c("  عند انعدام الصالح", "not usable and counts[\"dead\"]" in _g)
# ولا تكرار لا نهائي: النداء الثاني بلا إحياء
c("  وبلا تكرار لا نهائيّ",
  _g.count("auto_refresh=False") >= 2, str(_g.count("auto_refresh=False")))
c("  والشرط ‎auto_refresh‎", "if auto_refresh and not usable" in _g)

# ═══ والبوّابة تُسعف ولا تُعالج ═══
#
# ``resurrect`` سقفُه ٦٠٠ث و١٠٠٠ زوج — صحيحٌ للأداة اليدوية. لكنّه
# يُنادى من **داخل المسح**، فبلا تحديد صار المسح يحمل عشر دقائق من
# الجلب قبل أن يحلّل شمعةً واحدة. وهو عطبٌ أُدخل بهذا الفرع نفسه.
_rcall = _g.split("self.resurrect(")[1][:400] if "self.resurrect(" in _g else ""
c("  وبميزانية البوّابة لا ميزانيته",
  "deadline_seconds=" in _rcall and "max_pairs=" in _rcall, _rcall[:160])
c("    وهي ‎gate_refresh_*‎", "gate_refresh_seconds" in _rcall
  and "gate_refresh_max_pairs" in _rcall)
c("  وسببه", "عشر دقائق من الجلب" in src)


# ═══════════ ٣ب) وزمن البوّابة يُقاس ═══════════
#
# البوّابة تجلب شبكياً تسلسلياً داخل المسح، وزمنها كان يدخل في
# ``duration_seconds`` ولا يظهر في أيّ خانة. فتُقرأ «شبكة ٤ث» على
# دورةٍ استغرقت دقيقتين — رقمٌ صادق وتفصيلٌ كاذب.
SCAN = ROOT / "web" / "dashboard" / "management" / "commands" / "scan.py"
sc = code_of(SCAN)
sc_src = source_of(SCAN)
c("٣ب زمن البوّابة يُقاس", "t_gate = time.perf_counter() - _tg" in sc)
c("  ويدخل التفصيل", '"gate": t_gate' in sc)
c("  وزمن القاعدة كذلك", 'timing["db"] = ' in sc)
# ═══ والمجموع يُطابَق ═══
#
# تفصيلٌ لا يُجمع لا يُكتشَف نقصه.
c("  و‎أخرى‎ تكشف غير المقيس", "other = max(0.0, total - known)" in sc)
c("  والأثقل يُسمّى", "الأثقل" in sc)
c("  وسببه", "رقمٌ صادق وتفصيلٌ كاذب" in src
  or "الرقم المعروض صادق والتفصيل ناقص" in sc_src)


# ═══════════ ٤) الرسالة تقول ماذا يُفعل ═══════════
#
# «٥٣٧ مشطوباً من ٥٣٨» رقمٌ صحيح وصامت.
c("٤ الرسالة تفرّق الحالتين", "شطبٌ يعمّ السوق" in code)
c("  وتسمّي الأداة", "tools_resurrect" in code)
c("  عند الكثرة لا دائماً", 'counts["dead"] >= max(5' in code)


# ═══════════ ٥) الأداة تقرأ قبل أن تكتب ═══════════
tool = ROOT / "tools_resurrect.py"
c("٥ الأداة موجودة", tool.exists())
if tool.exists():
    t_code = code_of(tool)
    t_src = source_of(tool)
    c("  والتنفيذ بـ‎--apply‎", '"--apply"' in t_code)
    c("  والافتراض تقرير", "if not args.apply:" in t_code)
    # ═══ والتاريخ يقول القصّة قبل أي سؤال ═══
    #
    # شطبٌ حقيقيّ يتفرّق على شهور. وتوقّفُ مزامنةٍ يترك تاريخاً
    # واحداً يتكرّر عند المئات — توقيعٌ لا يُخطئ.
    c("  وتاريخ الشموع يُعدّ", "byday" in t_code)
    c("  والتوقيع يُفسَّر", "في اليوم نفسه" in t_code)
    c("  وسببه", "شطبٌ جماعيّ في يومٍ واحد لا يحدث" in t_src)


# ═══════════ ٦) والعتبة موثَّقة في الإعداد ═══════════
cfg_src = source_of(ROOT / "scanner" / "market_sync" / "config.py")
cfg_code = code_of(ROOT / "scanner" / "market_sync" / "config.py")
c("٦ الحدّان في الإعداد",
  "resurrect_seconds" in cfg_code and "resurrect_max_pairs" in cfg_code)
c("  والباب الواحد موثَّق", "باباً ذا اتّجاه واحد" in cfg_src)


sys.exit(c.report())
