# -*- coding: utf-8 -*-
"""شاشة المهامّ المجدولة — العرض والتحكّم.

كل تغيير هنا يمسّ ما يعمل في الخلفية، فالتحقّق قبل الحفظ لا بعده:
فترةٌ صفرية تجعل المهمّة تدور بلا توقّف، ومعالجٌ مجهول يجعلها تفشل
في كل دورة إلى الأبد.
"""
from __future__ import annotations

import logging

from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import cron
from .jsonsafe import JsonResponse
from .models import JobRun, ScheduledJob

log = logging.getLogger("dashboard.jobs")


def _row(job) -> dict:
    from django.utils import timezone

    now = timezone.now()
    due_in = None
    if job.next_run:
        due_in = int((job.next_run - now).total_seconds())
    return {
        "id": job.id, "code": job.code, "name": job.name,
        "handler": job.handler,
        "handler_label": cron.HANDLER_LABELS.get(job.handler, job.handler),
        "active": job.active,
        "interval_number": job.interval_number,
        "interval_type": job.interval_type,
        "interval_label": f"{job.interval_number} "
                          f"{dict(ScheduledJob.INTERVAL_TYPES).get(job.interval_type, '')}",
        "payload": job.payload or {},
        "priority": job.priority,
        "next_run": job.next_run.isoformat() if job.next_run else None,
        # ═══ الثواني المتبقّية لا الوقت المطلق ═══
        #
        # «12:44» يتطلّب من القارئ حساب الفرق ومعرفة المنطقة.
        # والسالب يُعرض «مستحقّة» لا «قبل 3 دقائق» — فالمهمّة
        # المتأخّرة حالةٌ لا تاريخ.
        "due_in": due_in,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "last_status": job.last_status,
        "last_message": job.last_message,
        "last_duration_ms": job.last_duration_ms,
        "run_count": job.run_count, "fail_count": job.fail_count,
    }


def jobs_page(request):
    return render(request, "dashboard/jobs.html", {
        "nav_page": "jobs",
        "interval_types": ScheduledJob.INTERVAL_TYPES,
        "handlers": [{"key": k, "label": cron.HANDLER_LABELS.get(k, k)}
                     for k in sorted(cron.HANDLERS)],
    })


@require_GET
def api_jobs(request):
    from django.db.utils import OperationalError, ProgrammingError

    try:
        jobs = list(ScheduledJob.objects.all())
    except (OperationalError, ProgrammingError):
        return JsonResponse({"ok": False,
                             "reason": "شغّل: python web/manage.py migrate"},
                            status=503)
    # البذر عند أوّل فتح: من فتح الصفحة قبل أن تدور نبضة يجد جدولاً
    # فارغاً ويظنّ الميزة معطّلة.
    if not jobs:
        cron.ensure_defaults()
        jobs = list(ScheduledJob.objects.all())

    return JsonResponse({
        "ok": True,
        "jobs": [_row(j) for j in jobs],
        "engine": cron.status(),
        "tick_seconds": cron.TICK_SECONDS,
    })


@require_GET
def api_job_runs(request, job_id: int):
    limit = min(100, max(1, int(request.GET.get("limit") or 25)))
    runs = (JobRun.objects.filter(job_id=job_id)
            .order_by("-started_at")[:limit])
    return JsonResponse({"ok": True, "runs": [
        {"started_at": r.started_at.isoformat(),
         "duration_ms": r.duration_ms, "status": r.status,
         "message": r.message, "manual": r.manual}
        for r in runs
    ]})


@require_POST
def api_job_run_now(request, job_id: int):
    """«شغّل الآن» — في خيط، فلا ينتظر المتصفّح دقائق.

    الموعد المجدول لا يُزاح: تشغيلٌ يدويّ في منتصف الفترة لا يعني
    أنّ المستخدم يريد إزاحة الإيقاع كلّه.
    """
    import threading

    job = ScheduledJob.objects.filter(pk=job_id).first()
    if job is None:
        return JsonResponse({"ok": False, "reason": "لا مهمّة بهذا الرقم"},
                            status=404)
    threading.Thread(target=cron.run_job, args=(job,),
                     kwargs={"manual": True},
                     name=f"cron-manual-{job.code}", daemon=True).start()
    return JsonResponse({"ok": True, "started": job.code})


@require_POST
def api_job_toggle(request, job_id: int):
    from django.utils import timezone

    job = ScheduledJob.objects.filter(pk=job_id).first()
    if job is None:
        return JsonResponse({"ok": False, "reason": "لا مهمّة"}, status=404)
    job.active = not job.active
    # ═══ الاستئناف من الآن لا من الماضي ═══
    #
    # مهمّةٌ أُوقفت أسبوعاً موعدها في الماضي البعيد. فتفعيلها يجعلها
    # مستحقّة فوراً — وهو مقبول — لكنّ الموعد يبقى قديماً فيُحسب
    # التقدّم من هناك. فيُضبط الآن كي يبدأ الإيقاع من لحظة التفعيل.
    if job.active and (not job.next_run or job.next_run < timezone.now()):
        job.next_run = timezone.now()
    job.save(update_fields=["active", "next_run", "updated_at"])
    return JsonResponse({"ok": True, "active": job.active, "job": _row(job)})


@require_POST
def api_job_save(request, job_id: int):
    """تعديل الفترة والأولوية والاسم."""
    from django.utils import timezone

    job = ScheduledJob.objects.filter(pk=job_id).first()
    if job is None:
        return JsonResponse({"ok": False, "reason": "لا مهمّة"}, status=404)

    try:
        number = int(request.POST.get("interval_number") or job.interval_number)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "reason": "الفترة ليست رقماً"},
                            status=400)
    itype = (request.POST.get("interval_type") or job.interval_type).strip()
    valid = {k for k, _ in ScheduledJob.INTERVAL_TYPES}
    if itype not in valid:
        return JsonResponse({"ok": False, "reason": "وحدة غير معروفة"},
                            status=400)
    # ═══ الصفر يُرفض هنا لا يُصحَّح صامتاً ═══
    #
    # ``interval_seconds`` يفرض حدّاً أدنى ثلاثين ثانية، لكنّ قبول
    # «0» في الواجهة يجعل المستخدم يرى صفراً محفوظاً ويظنّ أنّ
    # المهمّة تعمل بلا توقّف. فيُقال له.
    if number < 1:
        return JsonResponse({"ok": False,
                             "reason": "الفترة يجب أن تكون 1 فأكثر"},
                            status=400)

    changed_interval = (number != job.interval_number
                        or itype != job.interval_type)
    job.interval_number = number
    job.interval_type = itype
    name = (request.POST.get("name") or "").strip()
    if name:
        job.name = name[:120]
    try:
        job.priority = int(request.POST.get("priority") or job.priority)
    except (TypeError, ValueError):
        pass

    # تغيير الفترة يُعيد جدولة الموعد القادم من الآن: إبقاؤه على
    # القديم يجعل «كل دقيقة» تنتظر الساعة القديمة قبل أن تبدأ.
    if changed_interval:
        job.next_run = timezone.now()
    job.save()
    return JsonResponse({"ok": True, "job": _row(job)})


@require_POST
def api_jobs_seed(request):
    """يعيد إنشاء المهامّ الافتراضية الناقصة — ولا يلمس القائم."""
    made = cron.ensure_defaults()
    return JsonResponse({"ok": True, "created": made})
