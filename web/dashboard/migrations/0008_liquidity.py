# -*- coding: utf-8 -*-
"""حجم التداول وتصنيف السيولة."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0007_trade")]

    operations = [
        migrations.AddField(
            model_name="scanresult", name="quote_volume",
            field=models.FloatField(blank=True, db_index=True, null=True,
                                    verbose_name="حجم 24س")),
        migrations.AddField(
            model_name="scanresult", name="liquidity",
            field=models.CharField(db_index=True, default="unknown", max_length=8,
                                   verbose_name="السيولة")),
    ]
