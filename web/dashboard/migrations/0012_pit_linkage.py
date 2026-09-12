# -*- coding: utf-8 -*-
"""AIA-12: persist PIT / recommendation linkage on ScanResult and Trade."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0011_feature_snapshot")]

    operations = [
        migrations.AddField(
            model_name="scanresult",
            name="pit_snapshot_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=48, verbose_name="معرّف لقطة PIT",
            ),
        ),
        migrations.AddField(
            model_name="scanresult",
            name="recommendation_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, verbose_name="معرّف التوصية",
            ),
        ),
        migrations.AddField(
            model_name="trade",
            name="pit_snapshot_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=48, verbose_name="معرّف لقطة PIT",
            ),
        ),
        migrations.AddField(
            model_name="trade",
            name="recommendation_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, verbose_name="معرّف التوصية",
            ),
        ),
        migrations.AddField(
            model_name="trade",
            name="decision_timestamp",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="وقت القرار (PIT)",
            ),
        ),
        migrations.AddField(
            model_name="trade",
            name="feature_version",
            field=models.CharField(
                blank=True, default="", max_length=16, verbose_name="إصدار الميزات",
            ),
        ),
    ]
