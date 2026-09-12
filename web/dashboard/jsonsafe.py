# -*- coding: utf-8 -*-
"""ترميز JSON يحتمل أنواع numpy — والرسالة التي تكذب عليك.

═══ العطب ═══

انهار ``/api/btc/refresh/`` بالرسالة::

    TypeError: Object of type bool is not JSON serializable
    when serializing dict item 'beats_baseline'

وهذه رسالة **تبدو مستحيلة**: ``bool`` من أبسط ما يُرمَّز في JSON.

والسرّ أن القيمة لم تكن ``bool`` بل ``numpy.bool_``. ففي NumPy 2
صار ``np.bool_.__name__`` يساوي حرفيّاً ``"bool"`` — و``json`` يبني
رسالته من ``o.__class__.__name__``. فالمكتبة تقول لك اسم النوع
بصدق، والاسم نفسه هو الكذبة.

وأصلها سطر بريء: ``lo > best`` حيث الطرفان ``np.float64``. مقارنة
numpy لا تعيد ``bool`` بل ``np.bool_``. والشيء نفسه يقع مع
``np.float64`` و``np.int64`` من أي حساب: تعبر الطبقات كلّها بلا
شكوى — ``if`` يعمل، والطباعة تعمل، والمقارنة تعمل — حتى تصل إلى
حدّ التسلسل فتنفجر.

═══ لماذا العلاج هنا لا عند المصدر وحده ═══

أُصلح المصدر أيضاً (``btc/direction.py`` يُخرج ``bool`` أصيلاً).
لكن الاعتماد على انضباط كل حسبة في كل وحدة رهانٌ خاسر: أي
``mean()`` أو ``sum()`` أو مقارنة جديدة تُعيد العطب. فالحدّ الذي
يجب أن يكون محصّناً هو **حدّ التسلسل** — يُعبر مرّة واحدة.

الاستعمال: ``from .jsonsafe import JsonResponse`` بدل
``from django.http import JsonResponse``. لا شيء آخر يتغيّر.
"""
from __future__ import annotations

import datetime as _dt
import decimal
import json
import math
import uuid
from pathlib import Path, PurePath

from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse as _DjangoJsonResponse


class SafeJSONEncoder(DjangoJSONEncoder):
    """يرث تعامل Django مع التواريخ ويضيف numpy وما شابه.

    ``default()`` لا يُستدعى إلا على نوع لا يعرفه ``json`` — فالمسار
    الشائع (نصّ، عدد، قائمة، قاموس) لا يمرّ من هنا أصلاً، ولا كلفة
    على الاستجابات العادية.
    """

    def default(self, o):  # noqa: ANN001, ANN201
        # ── numpy بلا استيرادها إن لم تكن محمّلة ──
        #
        # الفحص بالبنية لا بالنوع: يعمل مع numpy وpandas وأي مكتبة
        # تتبع بروتوكول المصفوفات، ولا يفرض استيراد numpy على مسار
        # استجابة لا تحتاجها.
        item = getattr(o, "item", None)
        if item is not None and getattr(o, "ndim", None) == 0:
            try:
                return self._clean(item())
            except (ValueError, TypeError):
                pass

        tolist = getattr(o, "tolist", None)
        if callable(tolist):
            try:
                return self._clean(tolist())
            except (ValueError, TypeError):
                pass

        if isinstance(o, (set, frozenset)):
            return sorted(o, key=repr)
        if isinstance(o, decimal.Decimal):
            return self._clean(float(o))
        if isinstance(o, (PurePath, Path)):
            return str(o)
        if isinstance(o, uuid.UUID):
            return str(o)
        if isinstance(o, (_dt.timedelta,)):
            return o.total_seconds()
        if isinstance(o, BaseException):
            return str(o)

        return super().default(o)

    @staticmethod
    def _clean(v):  # noqa: ANN001, ANN205
        """‏NaN و‏Infinity ليسا JSON صالحاً.

        ``json`` يكتبهما نصّاً حرفيّاً ``NaN`` فيقبله Python ويرفضه
        ``JSON.parse`` في المتصفّح — أي عطب يظهر في الواجهة لا في
        السجلّ. يُحوَّلان إلى ``null``: غيابٌ معلَن خير من قيمة
        تكسر القارئ.
        """
        if isinstance(v, float) and not math.isfinite(v):
            return None
        if isinstance(v, list):
            return [SafeJSONEncoder._clean(x) for x in v]
        return v


_UNSET = object()


def sanitize(obj):  # noqa: ANN001, ANN201
    """يُبدّل ‏NaN و‏Infinity بـ ``null`` — ويعيد الأصل إن لم يتغيّر شيء.

    ═══ لماذا لا يكفي المرمِّز ═══

    ``np.float64`` يرث من ``float`` الأصلي. فـ ``json`` يعرفه ويكتبه
    مباشرةً ولا يستدعي ``default()`` عليه أبداً — أي أنّ حارس
    المرمِّز لا يراه. اكتشفتُ هذا لأن اختبار NaN سقط بينما اختبار
    ``np.float64`` مرّ: مرّ **لأن المرمِّز لم يُستدعَ**، لا لأنّه نجح.

    و‏``NaN`` نصّاً حرفيّاً في المخرَج يقبله Python ويرفضه
    ``JSON.parse`` في المتصفّح — فالعطب يظهر في الواجهة بعيداً عن
    سببه.

    ═══ لماذا يُعاد الأصل ═══

    الاستجابة الشائعة لا NaN فيها. إعادة الكائن نفسه عند عدم التغيّر
    تمنع نسخ آلاف الشموع في كل طلب: المرور قراءةٌ فقط، ولا يُبنى
    قاموس أو قائمة جديدة إلا حيث وقع تبديل فعليّ.
    """
    if isinstance(obj, float):
        return None if not math.isfinite(obj) else obj

    if isinstance(obj, dict):
        changed = False
        out = {}
        for k, v in obj.items():
            nv = sanitize(v)
            if nv is not v:
                changed = True
            out[k] = nv
        return out if changed else obj

    if isinstance(obj, (list, tuple)):
        changed = False
        out = []
        for v in obj:
            nv = sanitize(v)
            if nv is not v:
                changed = True
            out.append(nv)
        if not changed:
            return obj
        return out if isinstance(obj, list) else tuple(out)

    return obj


def dumps(data, **kwargs) -> str:
    """‏json.dumps بالمرمِّز الآمن وبلا NaN — لأي مسار خارج الاستجابات."""
    return json.dumps(sanitize(data), cls=SafeJSONEncoder, **kwargs)


class JsonResponse(_DjangoJsonResponse):
    """‏JsonResponse يحتمل numpy ولا يُخرج JSON غير صالح.

    بديل مباشر: لا شيء في نداءات الاستدعاء يتغيّر.
    """

    def __init__(self, data, encoder=SafeJSONEncoder, safe=True,
                 json_dumps_params=None, **kwargs):
        super().__init__(sanitize(data), encoder=encoder, safe=safe,
                         json_dumps_params=json_dumps_params, **kwargs)


__all__ = ["JsonResponse", "SafeJSONEncoder", "dumps", "sanitize"]
