# -*- coding: utf-8 -*-
"""اتّصالٌ مُعاد الاستعمال — لأنّ المصافحة كانت أغلى من البيانات.

═══ القياس الذي أوجب هذا الملفّ ═══

على خادمك، طلبُ شموعٍ واحد من Binance:

    طلبٌ شبكيّ واحد    997 مللي ثانية

وهو رقمٌ لا تفسّره البيانات: الطلب المقيس كان ‎limit=5‎ — بضعة
كيلوبايتات. ولا تفسّره المسافة وحدها.

يفسّره أنّ ``urllib.request.urlopen`` يفتح **اتّصالاً جديداً لكل
طلب**: بحثُ DNS، ثمّ مصافحة TCP ثلاثية، ثمّ مصافحة TLS كاملة
(دورتان إضافيتان)، ثمّ يُغلَق الاتّصال فور انتهاء الطلب.

فأربع دورات ذهابٍ وإياب إلى سنغافورة قبل أن يصل بايتٌ واحد من
الشموع. والبيانات نفسها دورةٌ واحدة.

═══ وما تغيّر ═══

مجمّعُ اتّصالاتٍ واحد يبقى مفتوحاً: المصافحة مرّةً لكل اتّصال لا
لكل طلب. والطلبات التالية تعيد استعماله.

والمتوقَّع نظرياً: نحو ١٥٠ مللي ثانية بدل ٩٩٧ — والقياس بعد
النشر هو الحكم، لا هذا التقدير.

═══ ولماذا لا يُزاد عدد الخيوط بدلاً من هذا ═══

حدّ Binance على الوزن لكل **IP** لا لكل اتّصال. فعشرون خيطاً
بمصافحةٍ لكل طلب تصل الحدّ أسرع وتُنتج نفس الزمن تقريباً — بل
تزيد الفشل (٣٣٥ في دورتك). وإعادةُ الاستعمال تُنقص الزمن بلا
أن تلمس الحدّ.

═══ والارتداد إن غاب ``requests`` ═══

الحزمة مثبّتة في الصورة، وليست من متطلّبات المشروع. فمن يشغّل
على جهازه بلا تثبيتها يعمل كما كان — أبطأ لا معطوباً.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger("scanner.adapters.http_pool")

__all__ = ["get_json", "available", "stats", "DEFAULT_TIMEOUT"]

DEFAULT_TIMEOUT = 20

#: حجم المجمّع — يجب أن يبلغ عدد الخيوط وإلّا اصطفّت عليه
#: ``crypto.yaml`` يطلب ١٢ خيطاً، والمزامنة تحدّها بـ``max_workers``
POOL_SIZE = 32

_session = None
_lock = threading.Lock()
_stats = {"requests": 0, "pooled": 0, "fallback": 0, "errors": 0}


def available() -> bool:
    try:
        import requests  # noqa: F401
    except ImportError:
        return False
    return True


def _get_session():
    """جلسةٌ واحدة لكل العملية — تُبنى مرّةً عند أوّل طلب."""
    global _session
    if _session is not None:
        return _session
    with _lock:
        if _session is not None:
            return _session
        # ═══ مفتاحٌ للفواحص ═══
        #
        # فواحص المحوّلات تستبدل ``urllib.request.urlopen`` لتختبر
        # منطق الإعادة وتبديل المضيف بلا شبكة. والمجمّع يتجاوز
        # ``urlopen`` — فصارت تلك الفواحص تطلب الشبكة الحقيقية دون
        # أن يلاحظ أحد. وهذا يعيدها إلى المسار الذي تستبدله.
        if os.getenv("HTTP_POOL_DISABLE") == "1":
            return None
        try:
            import requests
            from requests.adapters import HTTPAdapter
        except ImportError:
            return None

        s = requests.Session()
        # ═══ لا إعادة محاولةٍ هنا ═══
        #
        # المنادي يعيد المحاولة بتباعدٍ تصاعديّ ويبدّل المضيف.
        # وإعادةٌ ثانية داخل المحوّل تضاعف الانتظار بلا أن يعلم
        # المنادي — فتصير مهلةُ عشرين ثانية ستّين.
        adapter = HTTPAdapter(pool_connections=8, pool_maxsize=POOL_SIZE,
                              max_retries=0)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        # ═══ وافتراضٌ يقبله الجميع ═══
        #
        # كان ``market-scanner/0.1``. وياهو ترفض من لا ترويسةَ
        # متصفّحٍ له — فردّت على السوق السعودي كلّه حين أسقطتُ
        # ``headers=UA`` من ``_get``. والمحوّل يمرّر هويّته صريحةً
        # الآن، وهذا الافتراض شبكةُ أمانٍ لمن ينساها بعدُ.
        s.headers.update({"User-Agent":
                          "Mozilla/5.0 (compatible; market-scanner/0.1)",
                          "Accept": "application/json",
                          # صريحةٌ وإن كانت الافتراض: إغلاقُها هو
                          # بالضبط ما نتجنّبه
                          "Connection": "keep-alive"})
        _session = s
        log.info("مجمّع اتّصالات مُفعَّل (حتى %d اتّصالاً)", POOL_SIZE)
        return _session


def get_json(url: str, *, timeout: int = DEFAULT_TIMEOUT,
             headers: dict | None = None):
    """‏GET يعيد JSON — بمجمّعٍ إن أمكن، وبـ``urllib`` إن لم يُمكن.

    يرفع ما يرفعه ``urllib`` من أصنافٍ كي لا يتغيّر تعامل
    المنادين: ``HTTPError`` و``URLError`` و``OSError``.

    ═══ و``headers`` لا تُضاف إلى الجلسة ═══

    جلسةٌ واحدة تخدم Binance و‏Yahoo و‏Alpaca. ووضعُ مفتاح Alpaca
    في ترويساتها يرسله إلى الجميع — تسريبٌ صامت.
    """
    _stats["requests"] += 1
    s = _get_session()
    if s is None:
        _stats["fallback"] += 1
        return _urllib_json(url, timeout, headers)

    try:
        resp = s.get(url, timeout=timeout, headers=headers or None)
    except Exception as exc:  # noqa: BLE001
        _stats["errors"] += 1
        # ═══ يُترجَم إلى صنفٍ يعرفه المنادي ═══
        #
        # ``requests.ConnectionError`` لا يلتقطه ``except
        # urllib.error.URLError`` — فيهرب الاستثناء من كل طبقات
        # إعادة المحاولة المكتوبة فوقه.
        raise urllib.error.URLError(str(exc)[:200]) from exc

    if resp.status_code >= 400:
        _stats["errors"] += 1
        raise urllib.error.HTTPError(
            url, resp.status_code, resp.text[:200], resp.headers, None)

    _stats["pooled"] += 1
    return resp.json()


def _urllib_json(url: str, timeout: int, headers: dict | None = None):
    req = urllib.request.Request(
        url, headers={"User-Agent":
                      "Mozilla/5.0 (compatible; market-scanner/0.1)",
                      **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stats() -> dict:
    return {**_stats, "pool_enabled": _session is not None,
            "requests_lib": available()}


def warm(url: str, *, timeout: int = 5) -> float | None:
    """يفتح الاتّصال قبل أن يُحتاج — ويعيد زمن المصافحة.

    الطلب الأوّل يدفع ثمن المصافحة. وفتحُه قبل بدء الخيوط يعني
    أنّ أوّل اثني عشر طلباً لا يدفعونه معاً.
    """
    t0 = time.perf_counter()
    try:
        get_json(url, timeout=timeout)
    except Exception:  # noqa: BLE001
        return None
    return round((time.perf_counter() - t0) * 1000, 1)
