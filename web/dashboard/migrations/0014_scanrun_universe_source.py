# -*- coding: utf-8 -*-
"""تسجيل مصدر قائمة الرموز في كل دورة مسح.

الدورات السابقة تبقى بقيمة فارغة. وهذا صادق: لم نكن نسجّلها، فلا
نُسند إليها مصدراً بأثر رجعي — رغم أن السجلّ يدلّ بقوّة على أنها كلّها
ارتدّت إلى قائمة الملف (عشرة رموز متمايزة في كل تاريخ السوق الأمريكي).
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0013_watch_trigger_feed"),
    ]

    operations = [
        migrations.AddField(
            model_name="scanrun",
            name="universe_source",
            field=models.CharField(blank=True, default="", max_length=16,
                                   verbose_name="مصدر الرموز"),
        ),
        migrations.AddField(
            model_name="scanrun",
            name="universe_note",
            field=models.CharField(blank=True, default="", max_length=300,
                                   verbose_name="ملاحظة الرموز"),
        ),
    ]
