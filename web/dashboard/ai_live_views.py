# -*- coding: utf-8 -*-
"""نقطة المحادثة الحيّة — خفيفة بما يكفي لتُستعلَم كل ثانيتين.

لا حساب ولا شبكة هنا: قراءة من ذاكرة العملية فقط. القاعدة التي
انتُهكت مرّتين في هذا المشروع محفوظة — طبقة العرض لا تنتظر شيئاً.
"""
from __future__ import annotations

from .jsonsafe import JsonResponse


def api_ai_live(request):
    """حالة المحادثة الجارية وآخر المحفوظات.

    ``since`` اختياري: عدد المحارف التي وصلت المتصفّح من الإجابة، فلا
    يُعاد إرسال ما لديه. إجابة بعشرات الكيلوبايتات تُنقل كاملةً كل
    ثانيتين تُثقل الشبكة بلا فائدة.
    """
    try:
        from scanner.ai_advisor import live_channel

        snap = live_channel.snapshot()
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"ok": False, "active": False,
                             "reason": str(exc)[:160]})

    cur = snap.get("current")
    if cur:
        try:
            since = max(0, int(request.GET.get("since") or 0))
        except (TypeError, ValueError):
            since = 0
        answer = cur.get("answer") or ""
        # القصّ يقع فقط إن كان ما لدى المتصفّح بادئةً صحيحة لما عندنا؛
        # وإلا (إعادة تحميل أو محادثة جديدة) يُرسَل الكامل
        if 0 < since <= len(answer):
            cur = {**cur, "answer": answer[since:], "answer_from": since}
        else:
            cur = {**cur, "answer_from": 0}
        cur["answer_len"] = len(answer)
        snap = {**snap, "current": cur}

    return JsonResponse({"ok": True, **snap})
