# -*- coding: utf-8 -*-
"""دليل الشركات — جدولٌ مستقلّ عن نتائج المسح."""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0014_scanrun_universe_source"),
    ]

    operations = [
        migrations.CreateModel(
            name="Company",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("market", models.CharField(db_index=True, max_length=16,
                                            verbose_name="السوق")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("name_ar", models.CharField(blank=True, max_length=160,
                                             verbose_name="الاسم")),
                ("name_en", models.CharField(blank=True, max_length=160,
                                             verbose_name="Name")),
                ("sector", models.CharField(blank=True, max_length=120,
                                            verbose_name="القطاع")),
                ("sub_market", models.CharField(blank=True, max_length=32,
                                                verbose_name="السوق الفرعي")),
                ("security_type", models.CharField(blank=True, max_length=32,
                                                   verbose_name="نوع الورقة")),
                ("price", models.FloatField(blank=True, null=True,
                                            verbose_name="السعر")),
                ("change_pct", models.FloatField(blank=True, null=True,
                                                 verbose_name="التغيّر ٪")),
                ("volume", models.FloatField(blank=True, null=True,
                                             verbose_name="الحجم")),
                ("quote_value", models.FloatField(blank=True, null=True,
                                                  verbose_name="قيمة التداول")),
                ("pe", models.FloatField(blank=True, null=True,
                                         verbose_name="مكرّر الربحية")),
                ("eps", models.FloatField(blank=True, null=True,
                                          verbose_name="ربحية السهم")),
                ("book_value", models.FloatField(blank=True, null=True,
                                                 verbose_name="القيمة الدفترية")),
                ("week52_high", models.FloatField(blank=True, null=True,
                                                  verbose_name="أعلى ٥٢ أسبوعاً")),
                ("week52_low", models.FloatField(blank=True, null=True,
                                                 verbose_name="أدنى ٥٢ أسبوعاً")),
                ("candles", models.IntegerField(default=0,
                                                verbose_name="عدد الشموع")),
                ("last_candle", models.DateTimeField(blank=True, null=True,
                                                     verbose_name="آخر شمعة")),
                ("info_updated_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="آخر تحديث للمعلومات")),
                ("updated_at", models.DateTimeField(auto_now=True,
                                                    verbose_name="آخر تعديل")),
            ],
            options={
                "verbose_name": "شركة",
                "verbose_name_plural": "الشركات",
                "ordering": ["market", "symbol"],
            },
        ),
        migrations.AddIndex(
            model_name="company",
            index=models.Index(fields=["market", "sector"],
                               name="dashboard_c_market_sector_idx"),
        ),
        migrations.AddConstraint(
            model_name="company",
            constraint=models.UniqueConstraint(fields=("market", "symbol"),
                                               name="uniq_company_market_symbol"),
        ),
    ]
