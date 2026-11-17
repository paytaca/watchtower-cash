from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('rampp2p', '0243_ad_unavailable_reminders'),
    ]

    operations = [
        migrations.AlterField(
            model_name='featurecontrol',
            name='name',
            field=models.CharField(
                choices=[
                    ('P2P_MAINTENANCE', 'P2P maintenance (enabled = paused)'),
                    ('AD_SHARE_LINKS', 'Ad Share Links'),
                    ('ORDER_CREATE', 'Order Create'),
                    ('ORDER_ESCROW', 'Order Escrow'),
                    ('AD_CREATE', 'Ad Create'),
                    ('AD_UPDATE', 'Ad Update'),
                ],
                max_length=100,
                unique=True,
            ),
        ),
    ]
