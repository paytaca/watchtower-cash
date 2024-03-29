# Generated by Django 3.0.14 on 2023-12-06 04:04

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0078_auto_20231206_0329'),
    ]

    operations = [
        migrations.AlterField(
            model_name='wallethistory',
            name='date_created',
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='wallethistory',
            name='tx_timestamp',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
