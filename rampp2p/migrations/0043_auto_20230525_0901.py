# Generated by Django 3.0.14 on 2023-05-25 09:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0042_auto_20230525_0846'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='crypto_amount',
            field=models.DecimalField(decimal_places=8, default=0, editable=False, max_digits=18),
        ),
        migrations.AlterField(
            model_name='order',
            name='locked_price',
            field=models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=18),
        ),
        migrations.AlterField(
            model_name='recipient',
            name='amount',
            field=models.DecimalField(decimal_places=8, default=0, editable=False, max_digits=18),
        ),
    ]
