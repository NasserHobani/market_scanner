# -*- coding: utf-8 -*-
"""قواعد الخروج على المراكز الحقيقية.

جدولٌ واحد، بلا مساسٍ بأيّ جدولٍ قائم: المحفظة الحقيقية شيءٌ
والمحفظة الورقية شيءٌ آخر، وخلطُهما يجعل «أداء النظام» يشمل
قراراتٍ لم يتّخذها.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0019_pesdetection"),
    ]

    operations = [
        migrations.CreateModel(
            name="WalletRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("asset", models.CharField(blank=True, max_length=16,
                                           verbose_name="الأصل")),
                ("kind", models.CharField(
                    choices=[("stop", "وقف"), ("target", "هدف"),
                             ("trail", "تراجع من القمّة"),
                             ("signal", "تحليل المنصّة")],
                    default="stop", max_length=8, verbose_name="النوع")),
                ("price", models.FloatField(blank=True, null=True,
                                            verbose_name="السعر")),
                ("pct", models.FloatField(blank=True, null=True,
                                          verbose_name="النسبة ٪")),
                ("active", models.BooleanField(default=True,
                                               verbose_name="فعّالة")),
                ("note", models.CharField(blank=True, max_length=160,
                                          verbose_name="ملاحظة")),
                ("peak", models.FloatField(blank=True, null=True,
                                           verbose_name="القمّة منذ التفعيل")),
                ("peak_at", models.DateTimeField(blank=True, null=True,
                                                 verbose_name="وقت القمّة")),
                ("fired_at", models.DateTimeField(blank=True, null=True,
                                                  verbose_name="آخر تنبيه")),
                ("fired_price", models.FloatField(blank=True, null=True,
                                                  verbose_name="سعر التنبيه")),
                ("fire_count", models.IntegerField(
                    default=0, verbose_name="عدد التنبيهات")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "قاعدة خروج",
                "verbose_name_plural": "قواعد الخروج",
                "ordering": ["symbol", "kind"],
            },
        ),
        migrations.AddConstraint(
            model_name="walletrule",
            constraint=models.UniqueConstraint(
                fields=("symbol", "kind"), name="one_rule_per_symbol_kind"),
        ),
    ]
