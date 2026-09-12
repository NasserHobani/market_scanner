# -*- coding: utf-8 -*-
"""تمييز قفل قاعدة البيانات العابر عن العطب البنيوي.

═══ لماذا ═══

حلقتا الحسم والمراقبة كانتا تُعيدان رفع كل ``DatabaseError``. والنيّة
سليمة: خطأ في القاعدة يعني شيئاً يستحقّ التوقّف لا الابتلاع.

لكنّ «database is locked» ليس عطباً — بل ازدحام لحظي بين كاتبين، وهو
حالة **متوقَّعة** في نظام فيه ثلاثة كتّاب متزامنين. ومعاملته معاملة
العطب كان يُجهض الدورة كلّها: تموت حلقة الحسم عند الصفقة التي صادفت
القفل، فما بعدها لا يُحسم في تلك الدورة.

وهذا يمسّ غرض المشروع مباشرةً: الحسم هو ما يقيس نتائج التوصيات. دورة
تسقط في منتصفها تعني صفقات بلغت هدفها أو وقفها ولم تُسجَّل، لسبب لا
علاقة له بالسوق.

أما الأخطاء الأخرى — جدول مفقود، قرص ممتلئ، ملف تالف — فتبقى على
حالها: تُرفَع ولا تُبتلع، لأن إخفاءها يجعل النظام يعمل على بيانات
ناقصة وهو يظنّ نفسه سليماً.

═══ لماذا الانتظار عشوائي ═══

خيطان يصطدمان ثم ينتظران المدّة نفسها يصطدمان ثانيةً. فالتشويش
العشوائي يفرّق بينهما بدل أن يُبقيهما متزامنين.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

# عبارات SQLite و PostgreSQL للازدحام العابر. المقارنة بالنصّ لأن
# رمز الخطأ لا يصل عبر غلاف Django بشكل موحَّد بين المحرّكات.
_LOCK_HINTS = (
    "database is locked",
    "database table is locked",
    "deadlock detected",
    "could not obtain lock",
)

DEFAULT_ATTEMPTS = 4
BASE_DELAY = 0.25       # ثانية — تتضاعف مع كل محاولة
MAX_DELAY = 4.0


def _database_error() -> type[BaseException]:
    """صنف خطأ القاعدة — أو ``Exception`` إن تعذّر.

    اختبارات هذا المشروع تُبدّل Django بنسخة صورية (فـ ``scanner``
    مستقلّة عنه عمداً). واستيراد صارم هنا كان يجعل كل حسم يفشل تحت
    الاختبار برسالة استيراد لا علاقة لها بالقفل — أي أن الحارس نفسه
    يصير هو العطب.

    والتمييز الحقيقي في :func:`is_lock_error` لا في صنف الاستثناء،
    فالتوسيع إلى ``Exception`` لا يبتلع شيئاً: ما ليس قفلاً يُرفَع.
    """
    try:
        from django.db import DatabaseError

        return DatabaseError
    except Exception:  # noqa: BLE001
        return Exception


def is_lock_error(exc: BaseException) -> bool:
    """أهو ازدحام عابر أم عطب يستحقّ التوقّف؟"""
    text = str(exc).lower()
    return any(hint in text for hint in _LOCK_HINTS)


def retry_on_lock(fn: Callable[[], T], *, attempts: int = DEFAULT_ATTEMPTS,
                  what: str = "عملية") -> T:
    """ينفّذ ``fn`` ويعيد المحاولة عند القفل وحده.

    كل خطأ آخر يُرفَع فوراً بلا محاولة ثانية: إعادة محاولة جدول مفقود
    تضيّع الوقت ولا تغيّر النتيجة.
    """
    DatabaseError = _database_error()

    delay = BASE_DELAY
    last: BaseException | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return fn()
        except DatabaseError as exc:
            if not is_lock_error(exc):
                raise
            last = exc
            if attempt >= attempts:
                break
            # تشويش ±40٪ حتى لا يعيد الخيطان المحاولة في اللحظة نفسها
            wait = min(MAX_DELAY, delay) * (0.6 + 0.8 * random.random())
            log.debug("قفل عند %s — محاولة %s بعد %.2f ث", what, attempt + 1, wait)
            time.sleep(wait)
            delay *= 2
    log.warning("تعذّر %s بعد %s محاولات: القاعدة مقفلة", what, attempts)
    raise last  # type: ignore[misc]


def try_on_lock(fn: Callable[[], T], *, default: Any = None,
                what: str = "عملية") -> Any:
    """كـ :func:`retry_on_lock` لكن يعيد ``default`` بدل الرفع عند القفل.

    للمواضع التي يكون فيها تخطّي عنصر واحد أهون من إسقاط الدورة كلّها.
    """
    try:
        return retry_on_lock(fn, what=what)
    except Exception as exc:  # noqa: BLE001
        if is_lock_error(exc):
            return default
        raise
