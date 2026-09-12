# -*- coding: utf-8 -*-
"""قارئ ‎.env‎ — والعطب الذي تكرّر مرّتين لأنّ العلاج كان في المكان الخطأ.

═══ ما وقع ═══

‏``SAHMK_API_KEY`` موجود في ``.env`` — ثمانية وخمسون حرفاً. وقالت
أداة التشخيص: «مفتاح سهمك غير مضبوط».

ولم تكن كاذبة: ``os.getenv("SAHMK_API_KEY")`` أعاد فراغاً حقّاً،
لأن **لا أحد حمّل الملف**. قارئ ``.env`` كان مكتوباً — لكنه داخل
``web/config/settings.py``، فلا يعمل إلا حين تُقلَع Django. وأدوات
سطر الأوامر سكربتات مستقلّة لا تمرّ بها.

فصار السلوك يتفرّع بحسب **كيف** شُغّل الرمز لا **ماذا** يفعل:
النداء نفسه ينجح من اللوحة ويفشل من الطرفية.

═══ ولماذا وقع مرّتين ═══

التعليق فوق القارئ في ``settings.py`` يحكي القصّة ذاتها مع توكن
تلغرام: «تضع التوكن في ‎.env‎ ولا يصل أبداً». عولج هناك بإضافة
القارئ إلى الإعدادات — وهو علاجٌ للعَرَض: أُصلح مسارٌ واحد وبقي
الباقي.

فالعلاج الآن في ``scanner`` نفسها، وتُنادى عند استيراد الحزمة. كل
ما يلمس ``scanner`` — أداة أو اختبار أو Django — يرى الملف نفسه.

═══ الأسبقية ═══

بيئة العمليّة أوّلاً دائماً. ``.env`` يملأ الغائب ولا يُبدّل
الموجود، وإلّا لتعذّر تجاوز قيمة لطلب واحد.
"""
from __future__ import annotations

import os
from pathlib import Path

# جذر المشروع: هذا الملف في ``scanner/`` فالجذر أبوه.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_LOADED: set[str] = set()


def parse_env(text: str) -> dict[str, str]:
    """تحليل نصّ ‎.env‎ — بلا اعتماديات خارجية."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        # ``export KEY=value`` صيغة شائعة تُنسَخ من الشروح
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip().strip("\"'")
        if key:
            out[key] = value
    return out


def load_env(path: str | Path | None = None, *, force: bool = False) -> int:
    """يحمّل ‎.env‎ إلى بيئة العمليّة. يعيد عدد المفاتيح المضافة.

    مُتكرِّرة الاستدعاء بلا ضرر: الملفّ الواحد لا يُقرأ مرّتين ما لم
    يُطلب ``force``.
    """
    p = Path(path) if path is not None else PROJECT_ROOT / ".env"
    key = str(p.resolve()) if p.exists() else str(p)
    if key in _LOADED and not force:
        return 0
    _LOADED.add(key)
    if not p.exists():
        return 0
    try:
        pairs = parse_env(p.read_text(encoding="utf-8"))
    except OSError:
        return 0
    added = 0
    for k, v in pairs.items():
        # ═══ الفارغ كالغائب ═══
        #
        # كان الشرط ``k not in os.environ`` وحده. و‏docker compose
        # يمرّر ``FOO: ${FOO}`` غيرَ المضبوط بوصفه **سلسلةً فارغة
        # موجودة** — لا غائباً. فيرى هذا السطر المفتاح «مضبوطاً»
        # ويتخطّى قيمة ‎.env‎، ويبقى الفارغ.
        #
        # وأثره المقيس على الخادم: ``DJANGO_SECRET_KEY`` يُولَّد من
        # جديد في **كل** تشغيل، ويُلحَق بـ‎.env‎ ولا يُقرأ منه أبداً
        # — فينتهي كل جلسة وكل رمز CSRF مع كل أمر، والملفّ ينمو
        # سطرين في المرّة.
        if not os.environ.get(k, "").strip():
            os.environ[k] = v
            added += 1
    # ‎.env‎ قد يحمل المرادف وحده — فالترجمة بعد كل تحميل لا عند
    # الاستيراد وحده، وإلّا ضاع ما حُمِّل بـ``force`` لاحقاً.
    apply_aliases()
    return added


def env_status(path: str | Path | None = None) -> dict:
    """حالة الملف للتشخيص — بلا كشف أي قيمة.

    الأداة التي تقول «المفتاح غير مضبوط» يجب أن تستطيع القول **لماذا**:
    الملف غائب؟ أم موجود ولا يحوي المفتاح؟ أم يحويه ولم يُحمَّل؟
    وطول القيمة يكفي للتمييز بين «فارغ» و«موجود» بلا طباعة سرّ.
    """
    p = Path(path) if path is not None else PROJECT_ROOT / ".env"
    info: dict = {"path": str(p), "exists": p.exists(), "keys": []}
    if p.exists():
        try:
            info["keys"] = sorted(parse_env(p.read_text(encoding="utf-8")))
        except OSError as exc:
            info["error"] = str(exc)
    return info


def describe_key(name: str) -> str:
    """وصف مفتاح للعرض: من أين جاء وكم طوله — بلا قيمته."""
    val = os.getenv(name, "")
    if val:
        return f"مضبوط ({len(val)} حرفاً)"
    st = env_status()
    if not st["exists"]:
        return f"غير مضبوط — ولا يوجد ملف .env في {st['path']}"
    if name in st["keys"]:
        return "موجود في .env لكنه لم يُحمَّل — أبلغ عن هذا فهو عطب"
    return "غير مضبوط — وليس في .env"


# ═══════════════════════════════════════════════════════════════
#  أسماءٌ مرادفة
# ═══════════════════════════════════════════════════════════════
#
# ═══ عطبٌ وقع مرّتين، وصمت في الحالتين ═══
#
# ‏docker-compose.yml و‎.env.docker.example‎ يمرّران أسماءً، والكود
# يقرأ أسماءً أخرى. فالمفتاح **موجودٌ** في الحاوية ويقول النظام
# «غير مضبوط»:
#
#   compose يمرّر          الكود يقرأ                 الأثر
#   ─────────────────────  ─────────────────────────  ──────────────
#   ALPACA_API_KEY         ALPACA_API_KEY_ID          صفر شمعة في
#   ALPACA_SECRET_KEY      ALPACA_API_SECRET_KEY      السوق الأمريكي
#   TELEGRAM_BOT_TOKEN     TELEGRAM_TOKEN             لا تنبيه يصل
#
# ولم يظهر محلّياً: ‎.env‎ على الجهاز مكتوبٌ بأسماء الكود.
#
# والحلّ ليس تصحيح أحد الطرفين — المستخدم قد لصق أيّهما، وتغييرُ
# الاسم يكسر إعداداً قائماً. فالاسمان يعملان، والترجمة هنا في
# مكانٍ واحد.
ALIASES: dict[str, str] = {
    "ALPACA_API_KEY": "ALPACA_API_KEY_ID",
    "ALPACA_SECRET_KEY": "ALPACA_API_SECRET_KEY",
    "TELEGRAM_BOT_TOKEN": "TELEGRAM_TOKEN",
}


def apply_aliases() -> int:
    """يملأ الاسم القانونيّ من مرادفه. يعيد عدد ما مُلئ.

    والاتّجاه واحد: المرادف يملأ القانونيّ الفارغ، ولا يدهسه. فمن
    ضبط الاسمين معاً يفوز القانونيّ — وهو ما يتوقّعه من كتبه.
    """
    n = 0
    for alias, canon in ALIASES.items():
        val = os.environ.get(alias, "").strip()
        if val and not os.environ.get(canon, "").strip():
            os.environ[canon] = val
            n += 1
    return n


# يُحمَّل عند استيراد ``scanner``. الوضع في الوحدة لا في دالّة
# يُنادى من كل أداة: ما يعتمد على تذكّر المطوّر يُنسى — وقد نُسي.
load_env()
apply_aliases()

__all__ = ["load_env", "parse_env", "env_status", "describe_key",
           "apply_aliases", "ALIASES", "PROJECT_ROOT"]
