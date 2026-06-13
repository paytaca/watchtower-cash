from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0238_report_model_and_peer_reported_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='report',
            name='reason',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('inactive', 'Inactive account'),
                    ('spammer', 'Spammer'),
                    ('scammer', 'Scammer'),
                ],
                default='inactive',
            ),
            preserve_default=False,
        ),
    ]
