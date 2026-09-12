# -*- coding: utf-8 -*-
"""سجلّ رصد ‏PES ومساره — هل هذا يعمل؟

يُحفظ المسار لا الحكم: أقصى ارتفاع ومتى بلغه، وأقصى تراجع، وهل
عُبِرت المقاومة. والعتبة بعد ذلك مرشِّحٌ في الشاشة — فعتبةٌ مخبوزة
في العمود تعني أنّ تغيير رأيك يُبطل كل ما جُمع.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0018_paper"),
    ]

    operations = [
        migrations.CreateModel(
            name="PesDetection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32,
                                            verbose_name="الرمز")),
                ("market", models.CharField(db_index=True, max_length=32,
                                            verbose_name="السوق")),
                ("state", models.CharField(db_index=True, max_length=24,
                                           verbose_name="الحالة عند الرصد")),
                ("state_label", models.CharField(blank=True, max_length=40,
                                                 verbose_name="وصف الحالة")),
                ("detected_at", models.DateTimeField(db_index=True,
                                                     verbose_name="وقت الرصد")),
                ("candle_time", models.DateTimeField(
                    db_index=True, verbose_name="شمعة الرصد")),
                ("price", models.FloatField(verbose_name="السعر عند الرصد")),
                ("score", models.FloatField(default=0.0,
                                            verbose_name="نقاط PES")),
                ("confidence", models.FloatField(default=1.0,
                                                 verbose_name="الثقة")),
                ("family_count", models.IntegerField(
                    default=0, verbose_name="عدد العائلات")),
                ("momentum_score", models.FloatField(
                    default=0.0, verbose_name="التقاء الزخم")),
                ("momentum_label", models.CharField(
                    blank=True, max_length=80, verbose_name="مرتبة الزخم")),
                ("resistance", models.FloatField(blank=True, null=True,
                                                 verbose_name="المقاومة")),
                ("distance_pct", models.FloatField(
                    blank=True, null=True, verbose_name="بعد المقاومة ٪")),
                ("btc_label", models.CharField(blank=True, max_length=16,
                                               verbose_name="نظام BTC")),
                ("reasons", models.CharField(blank=True, max_length=300,
                                             verbose_name="السبب")),
                ("bars_seen", models.IntegerField(
                    default=0, verbose_name="شمعات متابَعة")),
                ("max_gain_pct", models.FloatField(
                    blank=True, null=True, verbose_name="أقصى ارتفاع ٪")),
                ("max_gain_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="وقت أقصى ارتفاع")),
                ("hours_to_max", models.FloatField(
                    blank=True, null=True, verbose_name="ساعات حتى القمّة")),
                ("max_drawdown_pct", models.FloatField(
                    blank=True, null=True, verbose_name="أقصى تراجع ٪")),
                ("broke_resistance", models.BooleanField(
                    default=False, verbose_name="اخترق المقاومة")),
                ("broke_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="وقت الاختراق")),
                ("volatility_expanded", models.BooleanField(
                    default=False, verbose_name="تمدّد التقلّب")),
                ("outcome", models.CharField(
                    choices=[("watching", "قيد المتابعة"),
                             ("settled", "اكتمل المدى"),
                             ("no_data", "تعذّرت المتابعة")],
                    db_index=True, default="watching", max_length=12,
                    verbose_name="حال المتابعة")),
                ("settled_at", models.DateTimeField(
                    blank=True, null=True, verbose_name="وقت الاكتمال")),
                ("note", models.CharField(blank=True, max_length=200,
                                          verbose_name="ملاحظة")),
            ],
            options={
                "verbose_name": "رصد PES",
                "verbose_name_plural": "سجلّ رصد PES",
                "ordering": ["-detected_at"],
            },
        ),
        # ═══ الحارس البنيوي ضدّ التكرار ═══
        #
        # المسح كل ربع ساعة، ورمزٌ يبقى ‏PRE_BREAKOUT ثلاثة أيّام
        # يُنتج ٢٨٨ صفّاً لو سُجّل في كل دورة. والمنطق يمنع ذلك،
        # لكنّ القيد يمنعه ولو عمل ماسحان معاً — وقد حدث.
        migrations.AddConstraint(
            model_name="pesdetection",
            constraint=models.UniqueConstraint(
                fields=("symbol", "market", "state", "candle_time"),
                name="uniq_pes_detection"),
        ),
        migrations.AddIndex(
            model_name="pesdetection",
            index=models.Index(fields=["market", "state", "-detected_at"],
                               name="dash_pesdet_mkt_state_idx"),
        ),
        migrations.AddIndex(
            model_name="pesdetection",
            index=models.Index(fields=["outcome", "-detected_at"],
                               name="dash_pesdet_outcome_idx"),
        ),
    ]
