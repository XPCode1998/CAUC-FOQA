from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_qar_postprocess_task"),
    ]

    operations = [
        migrations.AlterField(
            model_name="qar",
            name="qar_id",
            field=models.CharField(db_index=True, max_length=60, null=True, verbose_name="QAR ID"),
        ),
    ]