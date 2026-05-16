from django.db import migrations, models
from django.utils import timezone


def backfill_created_time(apps, schema_editor):
    QAROverview = apps.get_model('core', 'QAR_Overview')
    for summary in QAROverview.objects.all().only('id', 'created_time', 'updated_time'):
        if summary.created_time:
            continue
        summary.created_time = summary.updated_time or timezone.now()
        summary.save(update_fields=['created_time'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_qar_qar_id_db_index'),
    ]

    operations = [
        migrations.AlterField(
            model_name='qar_overview',
            name='created_time',
            field=models.DateTimeField(default=timezone.now, verbose_name='创建时间'),
        ),
        migrations.AlterField(
            model_name='qar_overview',
            name='updated_time',
            field=models.DateTimeField(auto_now=True, verbose_name='修改时间'),
        ),
        migrations.RunPython(backfill_created_time, migrations.RunPython.noop),
    ]