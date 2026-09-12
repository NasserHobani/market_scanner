"""الهجرة الأولى.

مكتوبة يدوياً لأن مجلد migrations كان فارغاً — و`migrate` وحده لا يُنشئ
أي جدول بلا ملف هجرة. لو تركناه لك لظهرت رسالة "no such table" عند أول
فتح للوحة. يمكنك دائماً توليد التعديلات اللاحقة بـ makemigrations.
"""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="ScanRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("market", models.CharField(db_index=True, max_length=32, verbose_name="السوق")),
                ("timeframe", models.CharField(max_length=8, verbose_name="الفريم")),
                ("started_at", models.DateTimeField(auto_now_add=True, db_index=True,
                                                    verbose_name="بدأ")),
                ("duration_seconds", models.FloatField(default=0.0, verbose_name="المدة")),
                ("symbols_scanned", models.IntegerField(default=0, verbose_name="رموز مفحوصة")),
                ("symbols_failed", models.IntegerField(default=0, verbose_name="رموز فاشلة")),
                ("ready_count", models.IntegerField(default=0, verbose_name="مكتمل الشروط")),
            ],
            options={
                "verbose_name": "دورة مسح",
                "verbose_name_plural": "دورات المسح",
                "ordering": ["-started_at"],
            },
        ),
        migrations.CreateModel(
            name="ScanResult",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32, verbose_name="الرمز")),
                ("market", models.CharField(db_index=True, max_length=32, verbose_name="السوق")),
                ("timeframe", models.CharField(max_length=8, verbose_name="الفريم")),
                ("candle_time", models.DateTimeField(db_index=True, verbose_name="وقت الشمعة")),
                ("close", models.FloatField(verbose_name="الإغلاق")),
                ("score", models.FloatField(db_index=True, verbose_name="النقاط")),
                ("decision", models.CharField(
                    choices=[("شراء قوي", "شراء قوي"), ("شراء", "شراء"), ("محايد", "محايد"),
                             ("بيع", "بيع"), ("بيع قوي", "بيع قوي")],
                    max_length=16, verbose_name="القرار")),
                ("confluence", models.IntegerField(default=0, verbose_name="عناصر الالتقاء")),
                ("reasons", models.CharField(blank=True, max_length=255, verbose_name="الأسباب")),
                ("htf", models.SmallIntegerField(default=0, verbose_name="الفريم الأعلى")),
                ("ready", models.BooleanField(db_index=True, default=False,
                                              verbose_name="مكتمل الشروط")),
                ("blocker", models.CharField(blank=True, max_length=64, verbose_name="المانع")),
                ("rsi", models.FloatField(blank=True, null=True, verbose_name="RSI")),
                ("rvol", models.FloatField(blank=True, null=True, verbose_name="RVOL")),
                ("atr_pct", models.FloatField(blank=True, null=True, verbose_name="ATR%")),
                ("chart_url", models.URLField(blank=True, max_length=400,
                                              verbose_name="رابط الشارت")),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                          related_name="results", to="dashboard.scanrun")),
            ],
            options={
                "verbose_name": "نتيجة",
                "verbose_name_plural": "النتائج",
                "ordering": ["-score"],
            },
        ),
        migrations.CreateModel(
            name="SignalAlert",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32, verbose_name="الرمز")),
                ("fired_at", models.DateTimeField(auto_now_add=True, db_index=True,
                                                  verbose_name="وقت الإشارة")),
                ("score", models.FloatField(verbose_name="النقاط")),
                ("reasons", models.CharField(blank=True, max_length=255, verbose_name="الأسباب")),
                ("notified", models.BooleanField(default=False, verbose_name="أُرسل تنبيه")),
                ("result", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                             related_name="alerts", to="dashboard.scanresult")),
            ],
            options={
                "verbose_name": "إشارة",
                "verbose_name_plural": "الإشارات",
                "ordering": ["-fired_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scanrun",
            index=models.Index(fields=["market", "timeframe", "-started_at"],
                               name="dash_run_mkt_tf_time_idx"),
        ),
        migrations.AddIndex(
            model_name="scanresult",
            index=models.Index(fields=["market", "symbol", "-candle_time"],
                               name="dash_res_mkt_sym_time_idx"),
        ),
        migrations.AddIndex(
            model_name="scanresult",
            index=models.Index(fields=["-candle_time", "-score"],
                               name="dash_res_time_score_idx"),
        ),
        migrations.AddConstraint(
            model_name="scanresult",
            constraint=models.UniqueConstraint(
                fields=("symbol", "market", "timeframe", "candle_time"),
                name="unique_symbol_candle"),
        ),
    ]
