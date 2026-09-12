# -*- coding: utf-8 -*-
"""المهامّ المجدولة وسجلّ تشغيلها.

كانت الحلقات الأربع خيوطاً في الذاكرة: فترتها في متغيّر بيئة،
وحالتها تُمحى عند إعادة التشغيل، ولا سجلّ لما جرى. فصارت بيانات.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0015_company"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64, unique=True,
                                          verbose_name="المفتاح")),
                ("handler", models.CharField(db_index=True, max_length=32,
                                             verbose_name="المعالج")),
                ("name", models.CharField(max_length=120,
                                          verbose_name="الاسم")),
                ("active", models.BooleanField(db_index=True, default=True,
                                               verbose_name="نشِطة")),
                ("interval_number", models.PositiveIntegerField(
                    default=5, verbose_name="كل")),
                ("interval_type", models.CharField(
                    choices=[("minutes", "دقيقة"), ("hours", "ساعة"),
                             ("days", "يوم")],
                    default="minutes", max_length=10, verbose_name="الوحدة")),
                ("payload", models.JSONField(blank=True, default=dict,
                                             verbose_name="الوسائط")),
                ("priority", models.IntegerField(default=10,
                                                 verbose_name="الأولوية")),
                ("next_run", models.DateTimeField(
                    db_index=True, verbose_name="الموعد القادم")),
                ("last_run_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="آخر تشغيل")),
                ("last_duration_ms", models.IntegerField(
                    blank=True, null=True, verbose_name="المدّة (ms)")),
                ("last_status", models.CharField(
                    choices=[("ok", "نجحت"), ("fail", "فشلت"),
                             ("skipped", "تُخطّيت"), ("running", "تعمل الآن"),
                             ("never", "لم تعمل بعد")],
                    default="never", max_length=10,
                    verbose_name="آخر حالة")),
                ("last_message", models.CharField(
                    blank=True, max_length=300, verbose_name="آخر رسالة")),
                ("run_count", models.IntegerField(
                    default=0, verbose_name="مرّات التشغيل")),
                ("fail_count", models.IntegerField(
                    default=0, verbose_name="مرّات الفشل")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "مهمّة مجدولة",
                "verbose_name_plural": "المهامّ المجدولة",
                "ordering": ["priority", "code"],
            },
        ),
        migrations.CreateModel(
            name="JobRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("started_at", models.DateTimeField(
                    db_index=True, verbose_name="البداية")),
                ("duration_ms", models.IntegerField(
                    default=0, verbose_name="المدّة (ms)")),
                ("status", models.CharField(
                    choices=[("ok", "نجحت"), ("fail", "فشلت"),
                             ("skipped", "تُخطّيت"), ("running", "تعمل الآن"),
                             ("never", "لم تعمل بعد")],
                    default="ok", max_length=10, verbose_name="الحالة")),
                ("message", models.CharField(
                    blank=True, max_length=300, verbose_name="الرسالة")),
                ("manual", models.BooleanField(
                    default=False, verbose_name="يدويّ")),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="runs", to="dashboard.scheduledjob")),
            ],
            options={
                "verbose_name": "تشغيل مهمّة",
                "verbose_name_plural": "سجلّ التشغيل",
                "ordering": ["-started_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scheduledjob",
            index=models.Index(fields=["active", "next_run"],
                               name="dashboard_s_active_84e0dc_idx"),
        ),
        migrations.AddIndex(
            model_name="jobrun",
            index=models.Index(fields=["job", "-started_at"],
                               name="dashboard_j_job_id_02a1c9_idx"),
        ),
    ]
