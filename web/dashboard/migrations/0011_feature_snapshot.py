# -*- coding: utf-8 -*-
"""ربط النتائج والصفقات بلقطة خصائص."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0010_setting")]

    operations = [
        migrations.AddField(
            model_name="scanresult",
            name="feature_snapshot_id",
            field=models.CharField(blank=True, db_index=True, max_length=40,
                                   verbose_name="معرّف لقطة الخصائص"),
        ),
        migrations.AddField(
            model_name="trade",
            name="feature_snapshot_id",
            field=models.CharField(blank=True, db_index=True, max_length=40,
                                   verbose_name="معرّف لقطة الخصائص"),
        ),
    ]
