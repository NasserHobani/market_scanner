"""تصنيف جودة التوصية."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("dashboard", "0003_run_kind")]

    operations = [
        migrations.AddField(
            model_name="scanresult", name="grade",
            field=models.CharField(default="—", max_length=2,
                                   verbose_name="تصنيف التوصية"),
        ),
    ]
