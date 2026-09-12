# -*- coding: utf-8 -*-
"""الرموز المحظورة — قرار المستخدم لا حكم النظام."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0016_scheduledjob_jobrun"),
    ]

    operations = [
        migrations.CreateModel(
            name="BlockedSymbol",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("market", models.CharField(db_index=True, max_length=32,
                                            verbose_name="السوق")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("scope", models.CharField(
                    choices=[("exact", "هذا الرمز فقط"),
                             ("base", "الأصل وكل أزواجه")],
                    default="base", max_length=8, verbose_name="النطاق")),
                ("reason", models.CharField(blank=True, max_length=200,
                                            verbose_name="السبب")),
                ("source", models.CharField(blank=True, max_length=200,
                                            verbose_name="المصدر")),
                ("note", models.TextField(blank=True, verbose_name="ملاحظة")),
                ("active", models.BooleanField(db_index=True, default=True,
                                               verbose_name="مفعَّل")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "رمز محظور",
                "verbose_name_plural": "الرموز المحظورة",
                "ordering": ["market", "symbol"],
            },
        ),
        migrations.AddConstraint(
            model_name="blockedsymbol",
            constraint=models.UniqueConstraint(
                fields=("market", "symbol"),
                name="uniq_blocked_market_symbol"),
        ),
        migrations.AddIndex(
            model_name="blockedsymbol",
            index=models.Index(fields=["market", "active"],
                               name="dashboard_b_market_7c1f2a_idx"),
        ),
    ]
