"""الفرز الشرعي الأوّلي."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0005_watch")]

    operations = [
        migrations.AddField(
            model_name="scanresult", name="compliance",
            field=models.CharField(db_index=True, default="unknown", max_length=16,
                                   verbose_name="التوافق الشرعي")),
        migrations.AddField(
            model_name="scanresult", name="compliance_reason",
            field=models.CharField(blank=True, max_length=300,
                                   verbose_name="سبب التصنيف")),
    ]
