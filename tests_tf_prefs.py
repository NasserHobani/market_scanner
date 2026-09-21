# -*- coding: utf-8 -*-
"""فريمات كل سوق — والمسافة التي لم تكن فاصلاً.

═══ العطب المُبلَّغ ═══

كُتب في خانة «فريمات المزامنة لكل سوق»، وهي خانةُ سطرٍ واحد:

    crypto=4h,1d,1h,15m saudi=1d,4h gold=4h,1d us=1d,4h

وكان المحلّل يفصل بالسطر والنقطة والفاصلة المنقوطة **لا
بالمسافة**. فالسطر كلّه صار قيمةَ ``crypto``: ضاع ``15m`` لأنّه
التصق بـ``saudi=1d``، وبقيت الأسواق الثلاثة على الافتراض.

بلا خطأ ولا تنبيه. والإعداد الذي يُقرأ خطأً بصمتٍ أسوأ من الذي
يُرفَض: المستخدم يراه مكتوباً فيظنّه يعمل.

وتعليمات الحقل نفسها كانت تقول «بسطرٍ أو نقطة» — في خانةٍ لا
تقبل سطراً ثانياً أصلاً.

═══ والعطب الثاني: مزامنةٌ ليست مسحاً ═══

الإعداد يضبط ما **يُجلب**. والمسح يقرأ ``config/<سوق>.yaml``.
فمن أضاف ``1h`` ثمّ ضغط «١ ساعة» في شاشة المسح أعادته الشاشة إلى
‎4h‎: لا جولة مسحٍ على ‎1h‎ قطّ، والشاشة تستبدل المطلوب بأحدث ما
مُسح فعلاً.

فصار للمسح إعدادُه، بالصيغة نفسها والمحلّل نفسه.

═══ والقاعدة التي تربطهما ═══

كلّ فريمٍ يُمسح يُزامَن قسراً. وإلّا فالماسح يقرأ القرص فيجده
فارغاً: صفر نتائج، بلا خطأ ولا رسالة.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from scanner import tf_prefs as P  # noqa: E402
from tests_helpers import Checks, code_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

ONE_LINE = "crypto=4h,1d,1h,15m saudi=1d,4h gold=4h,1d us=1d,4h"


# ═══════════ ١) الفواصل الأربعة ═══════════
p = P.parse(ONE_LINE)
c("١ المسافة تفصل الأسواق", set(p) == {"crypto", "saudi", "gold", "us"},
  str(sorted(p)))
c("  ولا يضيع آخر فريمٍ في السوق",
  p.get("crypto") == ["4h", "1d", "1h", "15m"], str(p.get("crypto")))
c("  والسوق الثاني كامل", p.get("saudi") == ["1d", "4h"], str(p.get("saudi")))
c("  والأخير كذلك", p.get("us") == ["1d", "4h"], str(p.get("us")))
c("  والسطر يفصل", set(P.parse("crypto=4h\nsaudi=1d")) == {"crypto", "saudi"})
c("  والنقطة تفصل", set(P.parse("crypto=4h · saudi=1d")) == {"crypto", "saudi"})
c("  والفاصلة المنقوطة",
  set(P.parse("crypto=4h;saudi=1d")) == {"crypto", "saudi"})
# مسافاتٌ حول العلامة — يكتبها الناس
c("  ومسافات حول ‎=‎", P.parse("crypto = 4h , 1d")["crypto"] == ["4h", "1d"],
  str(P.parse("crypto = 4h , 1d")))
c("  والمسافة وحدها تفصل الفريمات",
  P.parse("crypto=4h 1d")["crypto"] == ["4h", "1d"], str(P.parse("crypto=4h 1d")))
c("  وحالة الأحرف لا تهمّ", "crypto" in P.parse("CRYPTO=4h"))


# ═══════════ ٢) اسم السوق لا يُخلَط بالفريم ═══════════
#
# الحدّ يُوضع قبل كل «اسم=». والفريم يبدأ برقم دائماً (‎4h‎ ·
# ‎15m‎)، فلا يمكن أن يُقرأ اسماً مهما كُتب.
c("٢ الفريم لا يصير سوقاً",
  P.parse("crypto=15m,1h,4h,1d") == {"crypto": ["15m", "1h", "4h", "1d"]},
  str(P.parse("crypto=15m,1h,4h,1d")))
c("  والتكرار يُزال", P.parse("crypto=4h,4h,1d")["crypto"] == ["4h", "1d"])


# ═══════════ ٣) الخطأ لا يوقف شيئاً ═══════════
c("٣ الفارغ يعيد فراغاً", P.parse("") == {} and P.parse(None) == {})
c("  والمعطوب يعيد فراغاً", P.parse("????") == {})
c("  والفريم المجهول يُهمَل وحده",
  P.parse("crypto=4h,7x,1d")["crypto"] == ["4h", "1d"],
  str(P.parse("crypto=4h,7x,1d")))
# ═══ وسوقٌ بلا فريمٍ صالح = لم يُذكر ═══
#
# إفراغُه كان سيوقف مزامنته بالكامل بسبب خطأٍ إملائيّ واحد.
c("  وسوقٌ كلّه مجهول يسقط", "crypto" not in P.parse("crypto=7x,9y"),
  str(P.parse("crypto=7x,9y")))


# ═══════════ ٤) المُهمَل يُقال ═══════════
#
# التجاهل الصامت هو ما أضاع ``15m``.
c("٤ المجهول يُبلَّغ", any("7x" in n for n in P.review("crypto=4h,7x")),
  str(P.review("crypto=4h,7x")))
c("  والصحيح بلا شكوى", P.review("crypto=4h,1d") == [],
  str(P.review("crypto=4h,1d")))
c("  والسطر المكتوب صحيحاً بلا شكوى", P.review(ONE_LINE) == [],
  str(P.review(ONE_LINE)))
c("  والمعطوب يُبلَّغ", P.review("????") != [])
c("  والفارغ لا يشكو", P.review("") == [])


# ═══════════ ٥) مصدرٌ واحد للاثنين ═══════════
_svc = code_of(ROOT / "scanner" / "market_sync" / "service.py")
c("٥ المزامنة تقرأ ‎sync_timeframes‎", "tf_prefs.sync_for" in _svc)
_cron = code_of(ROOT / "web" / "dashboard" / "cron.py")
c("  والمسح يقرأ ‎scan_timeframes‎", "tf_prefs.scan_for" in _cron)
# ═══ وما يُمسح يُزامَن ═══
#
# سوقٌ يُمسح على ‎1h‎ بلا شموع ‎1h‎ يعطي صفر نتائج بلا خطأ.
c("  وفريم المسح يدخل المزامنة قسراً",
  "tf_prefs.scan_for" in _svc, _svc.split("def _timeframes_for")[-1][:200])
c("  ولا محلّل ثانٍ في الماسح",
  'partition("=")' not in _cron)


# ═══════════ ٦) الشاشة تدلّ على ما يمكن فعله ═══════════
#
# كانت رسالة الاستبدال تحيل إلى ``config/<سوق>.yaml`` — ملفٍّ
# داخل الصورة لا يبلغه المستخدم إلّا بإعادة نشر.
_views = code_of(ROOT / "web" / "dashboard" / "views.py")
c("٦ الرسالة تحيل إلى الإعدادات", "فريمات المسح لكل سوق" in _views)
c("  ولا إلى ملفّ الصورة",
  "config/{market}.yaml" not in _views)
c("  والشاشة تقرأ المصدر نفسه", "def _scan_frames" in _views)
_sch = code_of(ROOT / "scanner" / "settings_schema.py")
c("  والحقلان في المخطّط",
  '"sync_timeframes"' in _sch and '"scan_timeframes"' in _sch)
# والتعليمات لا تَعِد بما لا تقبله الخانة: خانةُ سطرٍ واحد
_sch_raw = (ROOT / "scanner" / "settings_schema.py").read_text(encoding="utf-8")
_hint = _sch_raw.split('"sync_timeframes"')[1][:1400]
c("  والتعليمات تذكر المسافة", "بمسافة" in _hint, _hint[:120])


sys.exit(c.report())
