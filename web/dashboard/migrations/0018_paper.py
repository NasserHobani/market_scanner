# -*- coding: utf-8 -*-
"""المحفظة الورقية وصفقاتها."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0017_blockedsymbol")]

    operations = [
        migrations.CreateModel(
            name="PaperAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(default="محفظة تجريبية",
                                          max_length=80, verbose_name="الاسم")),
                ("active", models.BooleanField(db_index=True, default=True,
                                               verbose_name="نشِطة")),
                ("initial_balance", models.FloatField(
                    default=10000.0, verbose_name="رأس المال")),
                ("balance", models.FloatField(default=10000.0,
                                              verbose_name="النقد المتاح")),
                ("settings", models.JSONField(blank=True, default=dict,
                                              verbose_name="الإعدادات")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "محفظة ورقية",
                     "verbose_name_plural": "المحافظ الورقية",
                     "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PaperTrade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("market", models.CharField(db_index=True, max_length=32,
                                            verbose_name="السوق")),
                ("timeframe", models.CharField(blank=True, max_length=8,
                                               verbose_name="الفريم")),
                ("side", models.CharField(default="buy", max_length=8,
                                          verbose_name="الاتجاه")),
                ("source", models.CharField(blank=True, max_length=32,
                                            verbose_name="المصدر")),
                ("entry", models.FloatField(verbose_name="سعر الدخول")),
                ("stop", models.FloatField(verbose_name="الوقف")),
                ("target", models.FloatField(blank=True, null=True,
                                             verbose_name="الهدف")),
                ("quantity", models.FloatField(default=0.0,
                                               verbose_name="الكمّية")),
                ("notional", models.FloatField(default=0.0,
                                               verbose_name="قيمة المركز")),
                ("risk_amount", models.FloatField(default=0.0,
                                                  verbose_name="المخاطرة")),
                ("exit_price", models.FloatField(blank=True, null=True,
                                                 verbose_name="سعر الخروج")),
                ("exit_reason", models.CharField(blank=True, max_length=40,
                                                 verbose_name="سبب الخروج")),
                ("fee_in", models.FloatField(default=0.0,
                                             verbose_name="رسوم الدخول")),
                ("fee_out", models.FloatField(default=0.0,
                                              verbose_name="رسوم الخروج")),
                ("pnl", models.FloatField(default=0.0,
                                          verbose_name="الربح الصافي")),
                ("r_multiple", models.FloatField(blank=True, null=True,
                                                 verbose_name="مضاعف R")),
                ("status", models.CharField(
                    choices=[("open", "مفتوحة"), ("won", "رابحة"),
                             ("lost", "خاسرة"), ("cancelled", "أُلغيت")],
                    db_index=True, default="open", max_length=10,
                    verbose_name="الحالة")),
                ("opened_at", models.DateTimeField(db_index=True,
                                                   verbose_name="وقت الفتح")),
                ("closed_at", models.DateTimeField(blank=True, null=True,
                                                   verbose_name="وقت الإغلاق")),
                ("last_price", models.FloatField(blank=True, null=True,
                                                 verbose_name="آخر سعر")),
                ("note", models.CharField(blank=True, max_length=200,
                                          verbose_name="ملاحظة")),
                ("account", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="trades", to="dashboard.paperaccount")),
            ],
            options={"verbose_name": "صفقة ورقية",
                     "verbose_name_plural": "الصفقات الورقية",
                     "ordering": ["-opened_at"]},
        ),
        migrations.AddIndex(
            model_name="papertrade",
            index=models.Index(fields=["account", "status"],
                               name="dashboard_p_account_9f3b21_idx"),
        ),
    ]
