# -*- coding: utf-8 -*-
"""تسجيل تغذية السعر التي أطلقت تحقُّق المرصد.

الصفوف القديمة تبقى بقيمة فارغة — وهذا صادق: لم نكن نسجّلها، فلا
نُسند إليها تغذية بأثر رجعي. أي قياس لاحق يقارن iex بـ sip يجب أن
يستثني الفارغ لا أن يعدّه sip.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0012_pit_linkage"),
    ]

    operations = [
        migrations.AddField(
            model_name="watch",
            name="trigger_feed",
            field=models.CharField(blank=True, max_length=12,
                                   verbose_name="تغذية التحقق"),
        ),
    ]
