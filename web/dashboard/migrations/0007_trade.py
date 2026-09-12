# -*- coding: utf-8 -*-
"""سجلّ الصفقات المتتبَّعة."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0006_compliance")]

    operations = [
        migrations.CreateModel(
            name="Trade",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("source", models.CharField(
                    choices=[("auto", "آلية"), ("manual", "يدوية")],
                    db_index=True, default="auto", max_length=8,
                    verbose_name="المصدر")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("market", models.CharField(db_index=True, max_length=32,
                                            verbose_name="السوق")),
                ("timeframe", models.CharField(db_index=True, max_length=8,
                                               verbose_name="الفريم")),
                ("side", models.CharField(default="buy", max_length=8,
                                          verbose_name="الاتجاه")),
                ("entry", models.FloatField(verbose_name="الدخول المخطط")),
                ("stop", models.FloatField(verbose_name="الوقف")),
                ("target1", models.FloatField(verbose_name="الهدف الأول")),
                ("rr", models.FloatField(blank=True, null=True,
                                         verbose_name="العائد/المخاطرة")),
                ("grade", models.CharField(db_index=True, default="—", max_length=2,
                                           verbose_name="التصنيف")),
                ("score", models.FloatField(blank=True, null=True,
                                            verbose_name="الدرجة")),
                ("confidence", models.FloatField(default=0.0, verbose_name="الثقة")),
                ("action", models.CharField(default="none", max_length=12,
                                            verbose_name="نوع التوصية")),
                ("reasons", models.CharField(blank=True, max_length=255,
                                             verbose_name="الأسباب")),
                ("factors", models.JSONField(blank=True, default=list,
                                             verbose_name="العوامل")),
                ("status", models.CharField(
                    choices=[("pending", "تنتظر الدخول"), ("open", "مفتوحة"),
                             ("won", "رابحة"), ("lost", "خاسرة"),
                             ("expired", "لم تُفعَّل"), ("cancelled", "ملغاة")],
                    db_index=True, default="pending", max_length=10,
                    verbose_name="الحالة")),
                ("signal_at", models.DateTimeField(db_index=True,
                                                   verbose_name="وقت الإشارة")),
                ("candle_time", models.DateTimeField(verbose_name="شمعة الإشارة")),
                ("expires_at", models.DateTimeField(blank=True, null=True,
                                                    verbose_name="مهلة الدخول")),
                ("opened_at", models.DateTimeField(blank=True, null=True,
                                                   verbose_name="وقت التنفيذ")),
                ("closed_at", models.DateTimeField(blank=True, null=True,
                                                   verbose_name="وقت الخروج")),
                ("entry_price", models.FloatField(blank=True, null=True,
                                                  verbose_name="سعر التنفيذ")),
                ("exit_price", models.FloatField(blank=True, null=True,
                                                 verbose_name="سعر الخروج")),
                ("r_multiple", models.FloatField(blank=True, null=True,
                                                 verbose_name="مضاعف R")),
                ("best_r", models.FloatField(blank=True, null=True,
                                             verbose_name="أقصى ربح غير محقّق")),
                ("worst_r", models.FloatField(blank=True, null=True,
                                              verbose_name="أقصى تراجع")),
                ("bars_held", models.IntegerField(default=0,
                                                  verbose_name="شموع الاحتفاظ")),
                ("resolution_note", models.CharField(blank=True, max_length=120,
                                                     verbose_name="ملاحظة الحسم")),
                ("last_price", models.FloatField(blank=True, null=True,
                                                 verbose_name="آخر سعر")),
                ("checked_at", models.DateTimeField(blank=True, null=True,
                                                    verbose_name="آخر فحص")),
                ("note", models.CharField(blank=True, max_length=200,
                                          verbose_name="ملاحظة")),
            ],
            options={
                "verbose_name": "صفقة",
                "verbose_name_plural": "الصفقات",
                "ordering": ["-signal_at"],
            },
        ),
        migrations.AddIndex(
            model_name="trade",
            index=models.Index(fields=["source", "status", "-signal_at"],
                               name="dash_trade_src_stat_idx"),
        ),
        migrations.AddIndex(
            model_name="trade",
            index=models.Index(fields=["market", "timeframe", "status"],
                               name="dash_trade_mkt_tf_idx"),
        ),
        migrations.AddConstraint(
            model_name="trade",
            constraint=models.UniqueConstraint(
                fields=("source", "symbol", "market", "timeframe", "candle_time"),
                name="one_trade_per_signal_candle"),
        ),
    ]
