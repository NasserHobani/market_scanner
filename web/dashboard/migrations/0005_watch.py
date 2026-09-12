"""مراقبة الفرص المعلّقة."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0004_grade")]

    operations = [
        migrations.CreateModel(
            name="Watch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("symbol", models.CharField(db_index=True, max_length=32, verbose_name="الرمز")),
                ("market", models.CharField(db_index=True, max_length=32, verbose_name="السوق")),
                ("timeframe", models.CharField(max_length=8, verbose_name="الفريم")),
                ("side", models.CharField(default="buy", max_length=8, verbose_name="الاتجاه")),
                ("entry", models.FloatField(verbose_name="سعر الدخول")),
                ("stop", models.FloatField(verbose_name="الوقف")),
                ("target1", models.FloatField(blank=True, null=True, verbose_name="الهدف")),
                ("rr", models.FloatField(blank=True, null=True, verbose_name="العائد/المخاطرة")),
                ("grade", models.CharField(default="—", max_length=2, verbose_name="التصنيف")),
                ("reasons", models.CharField(blank=True, max_length=255, verbose_name="الأسباب")),
                ("trigger_text", models.CharField(blank=True, max_length=200,
                                                  verbose_name="شرط التفعيل")),
                ("status", models.CharField(
                    choices=[("armed", "مسلّحة"), ("triggered", "تحققت"),
                             ("expired", "منتهية"), ("cancelled", "ملغاة")],
                    db_index=True, default="armed", max_length=10, verbose_name="الحالة")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True,
                                                    verbose_name="أُنشئت")),
                ("expires_at", models.DateTimeField(blank=True, null=True, verbose_name="تنتهي")),
                ("triggered_at", models.DateTimeField(blank=True, null=True, verbose_name="تحققت")),
                ("trigger_price", models.FloatField(blank=True, null=True,
                                                    verbose_name="سعر التحقق")),
                ("notified", models.BooleanField(default=False, verbose_name="أُرسل تنبيه")),
                ("last_price", models.FloatField(blank=True, null=True, verbose_name="آخر سعر")),
                ("checked_at", models.DateTimeField(blank=True, null=True,
                                                    verbose_name="آخر فحص")),
            ],
            options={
                "verbose_name": "فرصة مراقَبة",
                "verbose_name_plural": "الفرص المراقَبة",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="watch",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="armed"),
                fields=("symbol", "market", "timeframe", "status"),
                name="one_armed_watch_per_symbol"),
        ),
    ]
