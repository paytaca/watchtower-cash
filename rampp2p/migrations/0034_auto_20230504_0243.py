# Generated by Django 3.0.14 on 2023-05-04 02:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('rampp2p', '0033_auto_20230504_0041'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='crypto_amount',
            field=models.FloatField(editable=False, null=True),
        ),
        migrations.AlterField(
            model_name='order',
            name='locked_price',
            field=models.FloatField(editable=False, null=True),
        ),
    ]