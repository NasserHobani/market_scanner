# -*- coding: utf-8 -*-
"""مصدر صفقات ثالث: تنبيهات الاختراق.

تُسجَّل منفصلة عن الآلية عمداً — قياسها الأوّلي كان سالباً على 4h،
فخلطها بالتوصيات كان سيفسد أرقام الاثنين معاً.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0008_liquidity")]

    operations = [
        migrations.AlterField(
            model_name="trade", name="source",
            field=models.CharField(
                choices=[("auto", "آلية"), ("manual", "يدوية"),
                         ("breakout", "اختراق")],
                db_index=True, default="auto", max_length=8,
                verbose_name="المصدر")),
    ]
