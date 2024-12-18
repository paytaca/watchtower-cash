# Generated by Django 3.0.14 on 2024-11-25 09:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0212_init_order_trade_amount_20241122_0728'),
    ]

    operations = [
        migrations.AddField(
            model_name='adsnapshot',
            name='trade_amount_fiat',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='adsnapshot',
            name='trade_ceiling_fiat',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name='adsnapshot',
            name='trade_floor_fiat',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
    ]
