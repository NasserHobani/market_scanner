# -*- coding: utf-8 -*-
"""الوقت بتوقيت الرياض، وبوّابة المسح لا تزامن بلا حدّ.

═══ الأوّل: ساعةٌ تكذب ═══

‏Django يخزّن بـUTC ويعرض بالمحلّي في القوالب. أمّا الـAPI فيُخرج
‏ISO بـ‎+00:00‎، وكانت الشاشات تقصّه نصّاً:

    String(r.started_at).replace("T", " ").slice(0, 19)

فتُعرَض الساعة بتوقيت غرينتش: صفقةٌ دخلت الثامنة مساءً تظهر
«17:00». وتقارنها بشارتك فلا تتطابق، فتظنّ البيانات خاطئة —
والبيانات صحيحة والعرض كاذب.

═══ والفخّ في التحليل ═══

``new Date("2026-10-07T12:00:00")`` بلا منطقةٍ يُقرأ **محلّياً**
لا UTC. فإلحاق ‎Z‎ لازم، وإلّا انزاح الوقت بفارق منطقة القارئ —
وهو انزياحٌ صامت يبدو صحيحاً لمن هو في غرينتش.

═══ الثاني: المسح يزامن ═══

بوّابة المسح تُنعش المتأخّر قبل أن تسمح بالمسح. وكانت تمرّ على
كل رمزٍ متأخّر **تسلسلياً وبلا سقف** — فصار زمنُ المسح = زمنُ
مزامنة كل ما تأخّر.

والمقيس على الخادم: ``scan:us`` استغرقت **١٩٣ دقيقة** وفترتها
خمس عشرة، و``scan:crypto`` ستّاً وخمسين. وليس التحليل هو ما
طال — بل المزامنة التي تجري داخله.

والعمل الحقيقيّ مكانه ``market_sync``: كل عشر دقائق، بعشرة خيوط
متوازية. والبوّابة تُكمِل ما فاتها لا تحلّ محلّها.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

from tests_helpers import Checks, code_of, source_of  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

STATIC = ROOT / "web" / "dashboard" / "static" / "dashboard"


# ═══════════ ١) مُنسِّقٌ واحد للوقت ═══════════
fmt = (STATIC / "format.js").read_text(encoding="utf-8")
c("١ ‎dateTime‎ موجودة", "function dateTime" in fmt)
c("  والمنطقة الرياض", '"Asia/Riyadh"' in fmt)
c("  وتُصدَّر", "dateTime: dateTime" in fmt and "tz: TZ" in fmt)
# ═══ والمنطقة مثبّتة لا «محلّية» ═══
#
# لوحةٌ تُفتح من هاتفٍ في سفرٍ تعرض أوقاتاً تختلف عن الحاسوب،
# والشموع والصفقات مرجعها واحد.
c("  والسبب مكتوب", "لوحةٌ تُفتح من هاتفٍ في سفر" in fmt)
c("  و‎Intl‎ لا ‎toLocaleString‎ عارياً", "Intl.DateTimeFormat" in fmt)
# ═══ والنصّ بلا منطقة يُلحَق به ‎Z‎ ═══
c("  والـISO بلا منطقة يُصحَّح", 'replace(" ", "T") + "Z"' in fmt)
c("  وسببه", "يُفترضه توقيت الجهاز" in fmt or "يُقرأ **محلّياً**" in fmt)
# والثواني تُميَّز عن الميلي
c("  والثواني تُميَّز", "1e10" in fmt)


# ═══════════ ٢) لا قصٌّ نصّيّ للوقت ═══════════
#
# الفحص على الصنف كلّه لا على ملفٍّ واحد.
bad: list[str] = []
for path in sorted(STATIC.glob("*.js")):
    if path.name == "format.js":
        continue
    txt = path.read_text(encoding="utf-8")
    for pat in ('replace("T", " ")', 'replace("T"," ")'):
        if pat in txt:
            bad.append(path.name)
            break
c("٢ لا قصٌّ نصّيّ للوقت", not bad, " · ".join(sorted(set(bad))))

for name in ("jobs-page.js", "wallet-page.js", "together-ask.js"):
    js = (STATIC / name).read_text(encoding="utf-8")
    c(f"  و{name} تستعمل ‎Fmt‎", "Fmt.dateTime" in js)


# ═══════════ ٣) البوّابة محدودة ═══════════
svc = ROOT / "scanner" / "market_sync" / "service.py"
code = code_of(svc)
src = source_of(svc)
body = code.split("def incremental_refresh_stale")[1][:2600] \
    if "def incremental_refresh_stale" in code else ""

c("٣ حدٌّ زمنيّ", "deadline_seconds" in body, body[:160])
c("  وحدٌّ عدديّ", "max_pairs" in body)
# ═══ والحدّ يُفحَص قبل الجلب ═══
#
# فحصُه بعده يسجّل التجاوز ولا يمنعه.
c("  ويُفحَص قبل الجلب",
  ("budget" in body and "sync_pair" in body
   and body.index("budget > 0") < body.index("sync_pair")), body[:200])
# ═══ وما لم يُنعَش يُعلَن ═══
#
# إخفاؤه يجعل المسح يبدو كاملاً وهو ناقص.
c("  والباقي يُعلَن", '"remaining"' in body)
c("  وسبب التوقّف", '"stopped"' in body)
c("  والزمن المستغرق", '"elapsed"' in body)

cfg = code_of(ROOT / "scanner" / "market_sync" / "config.py")
c("  والحدّان في الإعداد",
  "gate_refresh_seconds" in cfg and "gate_refresh_max_pairs" in cfg)
# والسبب موثَّق بالأرقام المقيسة لا بالرأي
c("  والقياس مكتوب", "١٩٣ دقيقة" in src)
c("  والعمل مكانه المزامنة", "تُكمِل ما فاتها لا تحلّ محلّها" in
  source_of(ROOT / "scanner" / "market_sync" / "config.py"))


# ═══════════ ٤) والمزامنة متوازية والبوّابة لا ═══════════
#
# وهذا هو الفرق الذي يفسّر الزمن: ``sync_market`` بعشرة خيوط،
# والبوّابة رمزاً رمزاً.
c("٤ المزامنة بخيوط", "ThreadPoolExecutor" in code)
c("  والبوّابة تسلسلية", "ThreadPoolExecutor" not in body)
c("  وهذا مقصود ومكتوب", "تعيد تسلسلياً ما تفعله" in src)


sys.exit(c.report())
