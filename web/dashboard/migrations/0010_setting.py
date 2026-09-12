# -*- coding: utf-8 -*-
"""تخزين إعدادات المستخدم."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0009_breakout_source")]

    operations = [
        migrations.CreateModel(
            name="Setting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64, unique=True,
                                         verbose_name="المفتاح")),
                ("value", models.JSONField(blank=True, null=True,
                                           verbose_name="القيمة")),
                ("updated_at", models.DateTimeField(auto_now=True,
                                                    verbose_name="آخر تعديل")),
            ],
            options={
                "verbose_name": "إعداد",
                "verbose_name_plural": "الإعدادات",
                "ordering": ["key"],
            },
        ),
    ]
