from django.db import migrations, models
from django.utils import timezone


def sync_timestamps(apps, schema_editor):
    QAROverview = apps.get_model('core', 'QAR_Overview')

    for summary in QAROverview.objects.all().only('id', 'created_time', 'updated_time'):
        synced_time = summary.updated_time or summary.created_time or timezone.now()
        if summary.created_time == synced_time and summary.updated_time == synced_time:
            continue
        summary.created_time = synced_time
        summary.updated_time = synced_time
        summary.save(update_fields=['created_time', 'updated_time'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_qar_overview_created_time_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='qar_overview',
            name='updated_time',
            field=models.DateTimeField(default=timezone.now, verbose_name='修改时间'),
        ),
        migrations.RunPython(sync_timestamps, migrations.RunPython.noop),
    ]