# -*- coding: utf-8 -*-
"""كل سرٍّ يقرؤه الكود يصل الحاوية فعلاً.

═══ العطب الذي أوجب هذا الفحص ═══

ضُبط ``BINANCE_API_KEY`` في بورتينر ← ``Environment variables``،
وقالت الشاشة «مفاتيح Binance غير مضبوطة».

وكلاهما صادق. فخانة بورتينر تملأ متغيّرات **الاستيفاء** — أي ما
يُستبدَل في ``${...}`` داخل ``docker-compose.yml``. ولا يصل شيءٌ
منها إلى العملية داخل الحاوية ما لم يُذكر تحت ``environment:``
في الخدمة.

ونسيتُ ذكرهما. فصار المستخدم يرى المفتاح مكتوباً أمامه والتطبيق
يقرأ فراغاً — ولا شيء في أيّ سجلٍّ يقول أين انقطع الخيط.

═══ ولماذا فحصٌ لا حذر ═══

هذا العطب وقع **ثلاث مرّات** في هذا المشروع: مرّةً بأسماء Alpaca
المختلفة، ومرّةً بتوكن تيلغرام، وهذه الثالثة. وعلاجُ كلٍّ منها
كان يدوياً — إضافة سطر — فيتكرّر مع كل مفتاحٍ جديد.

والعلاج البنيويّ أن يُقارَن **ما يُقرأ** بـ**ما يُمرَّر**، آلياً.

═══ والمجدول كالويب ═══

الخدمتان تشتركان في الكود. فمفتاحٌ يصل الويب ولا يصل المجدول
يجعل الشاشة تعمل والمهمّة الدورية تصمت — وهو أخبث من ألّا يعمل
شيء، لأنّه يبدو سليماً.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from tests_helpers import Checks  # noqa: E402

c = Checks(__doc__.strip().splitlines()[0])

COMPOSE = ROOT / "docker-compose.yml"
TPL = ROOT / ".env.docker.example"

# ما يُبحَث عنه: أسماءٌ تحمل سرّاً أو تضبط سلوكاً يُعدّ من الخارج
SECRET_RE = re.compile(
    r"""os\.(?:environ\.get|getenv)\(\s*["']"""
    r"""([A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|CHAT_ID))["']""")

EXTRA_VARS = ("REQUIRE_LOGIN", "ADMIN_USERNAME")

# ═══ ما لا يُنتظَر في ``environment:`` ═══
#
#   DJANGO_SECRET_KEY / POSTGRES_PASSWORD  مذكوران أصلاً
#   APCA_* و ALPACA_SECRET_KEY             مرادفات يملؤها ``env.ALIASES``
#   ORPHAN_KEY                             اسمٌ في فحصٍ آخر لا في الكود
ALIAS_OR_INTERNAL = {
    "APCA_API_SECRET_KEY", "ALPACA_SECRET_KEY", "ALPACA_API_SECRET_KEY",
    "ORPHAN_KEY", "BINANCE_SECRET", "BINANCE_KEY",
}

# الملفّات التي لا تُعدّ «كوداً يعمل في الحاوية»
SKIP_DIRS = ("tests_", "tools_")


def read_vars() -> set[str]:
    """أسماء الأسرار التي يقرؤها الكود فعلاً."""
    found: set[str] = set()
    for path in list((ROOT / "scanner").rglob("*.py")) + \
            list((ROOT / "web").rglob("*.py")):
        if any(path.name.startswith(p) for p in SKIP_DIRS):
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        found.update(SECRET_RE.findall(src))
    return found


def compose_env(service: str) -> set[str]:
    """مفاتيح ``environment:`` لخدمةٍ — بقراءة نصّية لا YAML.

    ``yaml`` ليس من متطلّبات الفواحص، وهذا القسم بسيط الشكل:
    مفتاحٌ ثمّ نقطتان. والقراءة النصّية تكفي وتبقي الفحص يعمل بلا
    اعتماد.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    # من اسم الخدمة إلى الخدمة التالية بنفس المسافة البادئة
    m = re.search(rf"^  {service}:$", text, re.M)
    if not m:
        return set()
    rest = text[m.end():]
    nxt = re.search(r"^  [a-z_]+:$", rest, re.M)
    block = rest[:nxt.start()] if nxt else rest

    e = re.search(r"^    environment:$", block, re.M)
    if not e:
        return set()
    after = block[e.end():]
    stop = re.search(r"^    [a-z_]+:", after, re.M)
    env_block = after[:stop.start()] if stop else after
    return set(re.findall(r"^\s{6}([A-Z][A-Z0-9_]*):", env_block, re.M))


# ═══════════ ١) الملفّات موجودة ═══════════
c("١ ‎docker-compose.yml‎ موجود", COMPOSE.exists())
c("  والقالب موجود", TPL.exists())

wanted = (read_vars() | set(EXTRA_VARS)) - ALIAS_OR_INTERNAL
c("  والأسرار تُستخرَج", len(wanted) >= 6, str(sorted(wanted)))

web = compose_env("web")
sched = compose_env("scheduler")
c("  و‎environment:‎ الويب تُقرأ", len(web) >= 10, str(len(web)))
c("  والمجدول كذلك", len(sched) >= 10, str(len(sched)))


# ═══════════ ٢) ما يُقرأ يُمرَّر ═══════════
#
# وهذا هو الفحص الذي كان ناقصاً.
missing_web = sorted(v for v in wanted if v not in web)
c("٢ كل سرٍّ يصل الويب", not missing_web, " · ".join(missing_web))

missing_sched = sorted(v for v in wanted if v not in sched)
c("  ويصل المجدول", not missing_sched, " · ".join(missing_sched))

# ═══ والخدمتان متّفقتان ═══
#
# الكود واحد، فاختلافُ ما يصلهما يجعل الشاشة تعمل والمهمّة تصمت.
drift = sorted((web ^ sched) - {"RUN_MIGRATIONS", "SCHEDULER_ENGINE",
                                "AUTO_SCAN", "WEB_CONCURRENCY"})
c("  ولا انحراف بينهما", not drift, " · ".join(drift))


# ═══════════ ٣) والقالب يذكرها ═══════════
#
# متغيّرٌ يُمرَّر ولا يُذكر في القالب لا يعرف المستخدم أنّه موجود.
tpl = TPL.read_text(encoding="utf-8") if TPL.exists() else ""
missing_tpl = sorted(v for v in wanted if f"{v}=" not in tpl)
c("٣ القالب يذكر كل سرّ", not missing_tpl, " · ".join(missing_tpl))
# وبلا قيمة: قالبٌ بقيمة يُنسخ كما هو فيصير السرّ معروفاً
filled = sorted(v for v in wanted
                if re.search(rf"^{v}=.+$", tpl, re.M))
c("  وبلا قيمٍ فيه", not filled, " · ".join(filled))


# ═══════════ ٤) بينانس بالذات ═══════════
for v in ("BINANCE_API_KEY", "BINANCE_API_SECRET"):
    c(f"٤ {v} في الويب", v in web)
    c(f"  وفي المجدول", v in sched)
# والبوّابة تصل: بلا المتغيّر تعمل بالافتراض — وهو التشغيل، فلا
# ضرر. لكنّ من أطفأها في بورتينر يجب أن يراها مُطفأة فعلاً.
c("  والبوّابة تصل", "REQUIRE_LOGIN" in web)


sys.exit(c.report())
