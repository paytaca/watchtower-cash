# Generated by Django 3.0.14 on 2023-11-07 06:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0093_auto_20231106_0453'),
    ]

    operations = [
        migrations.AddField(
            model_name='ad',
            name='trade_ceiling',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='adsnapshot',
            name='trade_ceiling',
            field=models.DecimalField(decimal_places=8, default=0, max_digits=18),
        ),
    ]
