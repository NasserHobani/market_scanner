"""حقول التوصية والتحليل التفصيلي."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0001_initial")]

    operations = [
        migrations.AddField(model_name="scanresult", name="action",
            field=models.CharField(db_index=True, default="none", max_length=12,
                                   verbose_name="نوع التوصية")),
        migrations.AddField(model_name="scanresult", name="headline",
            field=models.CharField(blank=True, max_length=32, verbose_name="التوصية")),
        migrations.AddField(model_name="scanresult", name="entry",
            field=models.FloatField(blank=True, null=True, verbose_name="الدخول")),
        migrations.AddField(model_name="scanresult", name="stop",
            field=models.FloatField(blank=True, null=True, verbose_name="الوقف")),
        migrations.AddField(model_name="scanresult", name="target1",
            field=models.FloatField(blank=True, null=True, verbose_name="الهدف الأول")),
        migrations.AddField(model_name="scanresult", name="rr",
            field=models.FloatField(blank=True, null=True, verbose_name="العائد/المخاطرة")),
        migrations.AddField(model_name="scanresult", name="trigger",
            field=models.CharField(blank=True, max_length=200, verbose_name="شرط التفعيل")),
        migrations.AddField(model_name="scanresult", name="candle_patterns",
            field=models.CharField(blank=True, max_length=160, verbose_name="نماذج الشموع")),
        migrations.AddField(model_name="scanresult", name="chart_pattern",
            field=models.CharField(blank=True, max_length=48, verbose_name="النموذج السعري")),
        migrations.AddField(model_name="scanresult", name="elliott",
            field=models.CharField(blank=True, max_length=48, verbose_name="موجة إليوت")),
        migrations.AddField(model_name="scanresult", name="confidence",
            field=models.FloatField(default=0.0, verbose_name="ثقة التوصية")),
    ]
