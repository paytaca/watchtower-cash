from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0239_report_reason_field'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='report',
            unique_together=set(),
        ),
        migrations.AddIndex(
            model_name='report',
            index=models.Index(
                fields=['reporter', 'reported_peer', '-created_at'],
                name='rampp2p_repo_report_55e1d5_idx',
            ),
        ),
    ]
