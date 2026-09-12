"""تمييز المسح الكامل عن التحليل المفرد."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0002_recommendation")]

    operations = [
        migrations.AddField(
            model_name="scanrun", name="kind",
            field=models.CharField(
                choices=[("scan", "مسح كامل"), ("adhoc", "تحليل مفرد")],
                db_index=True, default="scan", max_length=8, verbose_name="النوع"),
        ),
    ]
