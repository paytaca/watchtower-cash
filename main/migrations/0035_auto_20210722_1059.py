# Generated by Django 3.0.14 on 2021-07-22 10:59

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0034_auto_20210708_0121'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallethistory',
            name='recipients',
            field=django.contrib.postgres.fields.ArrayField(base_field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=70), size=None), blank=True, default=list, size=None),
        ),
        migrations.AddField(
            model_name='wallethistory',
            name='senders',
            field=django.contrib.postgres.fields.ArrayField(base_field=django.contrib.postgres.fields.ArrayField(base_field=models.CharField(max_length=70), size=None), blank=True, default=list, size=None),
        ),
        migrations.AddField(
            model_name='wallethistory',
            name='tx_fee',
            field=models.FloatField(default=0),
        ),
    ]
